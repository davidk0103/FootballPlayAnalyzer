"""The contract between the job runner and task-type handlers."""

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.models import Job

Checkpoint = Callable[[str, int, int], None]


@dataclass(frozen=True)
class HandlerResult:
    result: dict[str, Any]
    # Runs after the job is committed as SUCCEEDED (e.g. cache invalidation).
    after_success: list[Callable[[], object]] = field(default_factory=list)


Handler = Callable[[Job, Checkpoint], HandlerResult]
