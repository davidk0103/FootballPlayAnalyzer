import json
import logging

from app.observability.context import bind_job_id, bind_request_id
from app.observability.logging_config import JsonLogFormatter
from app.observability.metrics import status_class


def test_json_log_redacts_password_field() -> None:
    bind_request_id("req-1")
    bind_job_id("job-9")
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="",
        lineno=0,
        msg="login for user@example.com",
        args=(),
        exc_info=None,
    )
    record.password = "super-secret"
    line = JsonLogFormatter().format(record)
    payload = json.loads(line)
    assert payload["request_id"] == "req-1"
    assert payload["job_id"] == "job-9"
    assert payload["password"] == "[REDACTED]"


def test_status_class_buckets() -> None:
    assert status_class(200) == "2xx"
    assert status_class(404) == "4xx"
    assert status_class(500) == "5xx"

