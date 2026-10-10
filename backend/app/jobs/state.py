"""Job lifecycle state machine, retry policy, and idempotency helpers. Pure Python.

See docs/architecture.md ("Job lifecycle") for the diagram and the reasoning
behind each transition.
"""

import enum
import hashlib
import json
import random
from collections.abc import Mapping
from typing import Any


class JobStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    RETRYING = "retrying"
    CANCEL_REQUESTED = "cancel_requested"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AttemptStatus(enum.StrEnum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    # The worker died (or lost its lease) without recording an outcome.
    LOST = "lost"


TERMINAL = frozenset({JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.CANCELLED})
ACTIVE = frozenset(JobStatus) - TERMINAL

TRANSITIONS: Mapping[JobStatus, frozenset[JobStatus]] = {
    # Picked up by a worker, or cancelled before any worker started it.
    JobStatus.QUEUED: frozenset({JobStatus.RUNNING, JobStatus.CANCELLED}),
    JobStatus.RUNNING: frozenset(
        {
            JobStatus.SUCCEEDED,
            JobStatus.FAILED,  # permanent error, or attempts exhausted
            JobStatus.RETRYING,  # transient error / lost worker with attempts left
            JobStatus.CANCEL_REQUESTED,  # user asked; the worker stops at its next checkpoint
            # A redelivered message for a job whose previous attempt was lost.
            JobStatus.RUNNING,
        }
    ),
    JobStatus.RETRYING: frozenset({JobStatus.RUNNING, JobStatus.CANCELLED, JobStatus.FAILED}),
    JobStatus.CANCEL_REQUESTED: frozenset(
        {
            JobStatus.CANCELLED,
            # The work finished (or failed) before the worker reached a checkpoint.
            JobStatus.SUCCEEDED,
            JobStatus.FAILED,
        }
    ),
    JobStatus.SUCCEEDED: frozenset(),
    JobStatus.FAILED: frozenset(),
    JobStatus.CANCELLED: frozenset(),
}


class InvalidTransitionError(ValueError):
    def __init__(self, current: JobStatus, target: JobStatus) -> None:
        super().__init__(f"cannot move job from {current.value} to {target.value}")
        self.current = current
        self.target = target


def can_transition(current: JobStatus, target: JobStatus) -> bool:
    return target in TRANSITIONS[current]


def check_transition(current: JobStatus, target: JobStatus) -> None:
    if not can_transition(current, target):
        raise InvalidTransitionError(current, target)


def sources_for(target: JobStatus) -> frozenset[JobStatus]:
    """All states from which ``target`` is reachable (used for compare-and-set updates)."""
    return frozenset(s for s, targets in TRANSITIONS.items() if target in targets)


def backoff_seconds(
    attempt: int, *, base: float, cap: float, rng: random.Random | None = None
) -> float:
    """Exponential backoff with "equal jitter" for retry number ``attempt`` (1-based).

    The un-jittered delay is ``min(cap, base * 2**(attempt-1))``; the result is uniformly
    distributed in [delay/2, delay], so retries never fire immediately but concurrent
    failures still spread out instead of retrying in lockstep.
    """
    if attempt < 1:
        raise ValueError("attempt must be >= 1")
    delay = min(cap, base * 2.0 ** (attempt - 1))
    jitter = (rng or random.Random()).uniform(0, delay / 2)
    return delay / 2 + jitter


def request_fingerprint(task_type: str, params: Mapping[str, Any]) -> str:
    """Stable hash of a job request, used to detect idempotency-key reuse with new params."""
    canonical = json.dumps({"task_type": task_type, "params": params}, sort_keys=True)
    return hashlib.sha256(canonical.encode()).hexdigest()
