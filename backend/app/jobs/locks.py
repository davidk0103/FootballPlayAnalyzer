"""Per-job execution lease using PostgreSQL session-level advisory locks.

The lock is held on a dedicated connection for as long as a worker runs a job. If the
worker process dies, PostgreSQL closes its connection and releases the lock, which is
how the reaper tells a crashed job (lock free) from a slow one (lock held), and how a
duplicate delivery of the same message is detected and dropped.
"""

import uuid
from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import Engine, text


def lock_key(job_id: uuid.UUID) -> int:
    return int.from_bytes(job_id.bytes[:8], "big", signed=True)


@contextmanager
def job_lease(engine: Engine, job_id: uuid.UUID) -> Iterator[bool]:
    """Try to take the job's lease without blocking. Yields whether it was acquired."""
    key = lock_key(job_id)
    with engine.connect() as conn:
        acquired = bool(conn.scalar(text("SELECT pg_try_advisory_lock(:k)"), {"k": key}))
        conn.commit()
        try:
            yield acquired
        finally:
            if acquired:
                conn.execute(text("SELECT pg_advisory_unlock(:k)"), {"k": key})
                conn.commit()
