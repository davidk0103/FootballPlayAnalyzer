import random

import httpx
import pytest
from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy.exc import OperationalError

from app.ingest.service import IngestError
from app.jobs.errors import (
    JobCancelledError,
    PermanentJobError,
    TransientJobError,
    describe,
    is_transient,
)
from app.jobs.state import (
    ACTIVE,
    TERMINAL,
    TRANSITIONS,
    InvalidTransitionError,
    JobStatus,
    backoff_seconds,
    can_transition,
    check_transition,
    request_fingerprint,
    sources_for,
)

S = JobStatus


class TestStateMachine:
    def test_every_status_has_a_transition_entry(self) -> None:
        assert set(TRANSITIONS) == set(JobStatus)

    def test_terminal_states_have_no_exits(self) -> None:
        for status in TERMINAL:
            assert TRANSITIONS[status] == frozenset()
        assert set(JobStatus) == TERMINAL | ACTIVE
        assert not TERMINAL & ACTIVE

    @pytest.mark.parametrize(
        ("current", "target"),
        [
            (S.QUEUED, S.RUNNING),
            (S.QUEUED, S.CANCELLED),
            (S.RUNNING, S.SUCCEEDED),
            (S.RUNNING, S.FAILED),
            (S.RUNNING, S.RETRYING),
            (S.RUNNING, S.CANCEL_REQUESTED),
            (S.RUNNING, S.RUNNING),
            (S.RETRYING, S.RUNNING),
            (S.RETRYING, S.CANCELLED),
            (S.RETRYING, S.FAILED),
            (S.CANCEL_REQUESTED, S.CANCELLED),
            (S.CANCEL_REQUESTED, S.SUCCEEDED),
            (S.CANCEL_REQUESTED, S.FAILED),
        ],
    )
    def test_allowed(self, current: JobStatus, target: JobStatus) -> None:
        assert can_transition(current, target)
        check_transition(current, target)

    @pytest.mark.parametrize(
        ("current", "target"),
        [
            (S.QUEUED, S.SUCCEEDED),  # must run first
            (S.QUEUED, S.RETRYING),
            (S.QUEUED, S.CANCEL_REQUESTED),  # nothing running to ask; cancel directly
            (S.RETRYING, S.SUCCEEDED),
            (S.CANCEL_REQUESTED, S.RUNNING),  # a cancel request is never undone
            (S.CANCEL_REQUESTED, S.RETRYING),
            (S.SUCCEEDED, S.RUNNING),
            (S.FAILED, S.QUEUED),
            (S.CANCELLED, S.RUNNING),
        ],
    )
    def test_rejected(self, current: JobStatus, target: JobStatus) -> None:
        assert not can_transition(current, target)
        with pytest.raises(InvalidTransitionError, match=f"{current.value} to {target.value}"):
            check_transition(current, target)

    def test_sources_for(self) -> None:
        assert sources_for(S.CANCELLED) == {S.QUEUED, S.RETRYING, S.CANCEL_REQUESTED}
        assert sources_for(S.RUNNING) == {S.QUEUED, S.RETRYING, S.RUNNING}
        assert sources_for(S.QUEUED) == frozenset()

    def test_every_active_state_can_reach_a_terminal_state(self) -> None:
        for start in ACTIVE:
            seen, frontier = {start}, [start]
            while frontier:
                for nxt in TRANSITIONS[frontier.pop()]:
                    if nxt not in seen:
                        seen.add(nxt)
                        frontier.append(nxt)
            assert seen & TERMINAL, start


class TestBackoff:
    def test_grows_exponentially_within_jitter_bounds(self) -> None:
        rng = random.Random(7)
        for attempt, full in [(1, 2.0), (2, 4.0), (3, 8.0), (4, 16.0)]:
            for _ in range(200):
                delay = backoff_seconds(attempt, base=2.0, cap=60.0, rng=rng)
                assert full / 2 <= delay <= full

    def test_capped(self) -> None:
        rng = random.Random(1)
        delays = [backoff_seconds(20, base=2.0, cap=30.0, rng=rng) for _ in range(200)]
        assert all(15.0 <= d <= 30.0 for d in delays)

    def test_jitter_spreads_values(self) -> None:
        rng = random.Random(3)
        delays = {round(backoff_seconds(3, base=1.0, cap=60.0, rng=rng), 3) for _ in range(50)}
        assert len(delays) > 40

    def test_rejects_attempt_zero(self) -> None:
        with pytest.raises(ValueError):
            backoff_seconds(0, base=1, cap=10)


class TestIdempotencyFingerprint:
    def test_stable_and_order_independent(self) -> None:
        a = request_fingerprint("import_season", {"season": 2024, "force": False})
        b = request_fingerprint("import_season", {"force": False, "season": 2024})
        assert a == b
        assert len(a) == 64

    def test_differs_by_params_and_type(self) -> None:
        base = request_fingerprint("import_season", {"season": 2024, "force": False})
        assert base != request_fingerprint("import_season", {"season": 2024, "force": True})
        assert base != request_fingerprint("import_season", {"season": 2023, "force": False})
        assert base != request_fingerprint("other", {"season": 2024, "force": False})


class TestErrorClassification:
    def _status_error(self, code: int) -> httpx.HTTPStatusError:
        req = httpx.Request("GET", "https://example.test")
        return httpx.HTTPStatusError("x", request=req, response=httpx.Response(code, request=req))

    @pytest.mark.parametrize(
        "exc",
        [
            TransientJobError("blip"),
            TimeoutError(),
            ConnectionResetError(),
            SoftTimeLimitExceeded(),
            httpx.ConnectError("refused"),
            OperationalError("SELECT 1", {}, Exception("server closed the connection")),
        ],
    )
    def test_transient(self, exc: BaseException) -> None:
        assert is_transient(exc)

    def test_http_status(self) -> None:
        assert is_transient(self._status_error(503))
        assert is_transient(self._status_error(429))
        assert not is_transient(self._status_error(404))

    @pytest.mark.parametrize(
        "exc", [PermanentJobError("bad"), ValueError("bad"), KeyError("x"), JobCancelledError()]
    )
    def test_permanent(self, exc: BaseException) -> None:
        assert not is_transient(exc)

    def test_unwraps_ingest_error(self) -> None:
        try:
            try:
                raise TransientJobError("network")
            except TransientJobError as inner:
                raise IngestError("season 2024 import failed") from inner
        except IngestError as wrapped:
            assert is_transient(wrapped)
            assert describe(wrapped) == ("TransientJobError", "network")

    def test_describe_timeout(self) -> None:
        assert describe(SoftTimeLimitExceeded())[0] == "Timeout"

    def test_describe_http_status(self) -> None:
        assert describe(self._status_error(404)) == (
            "HTTPStatusError",
            "HTTP 404 from https://example.test (no file published for this season)",
        )
