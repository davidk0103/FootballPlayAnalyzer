import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.mark.integration
def test_metrics_endpoint_exposes_http_counters() -> None:
    client = TestClient(app)
    client.get("/health/live")
    metrics = client.get("/metrics")
    assert metrics.status_code == 200
    body = metrics.text
    assert "piq_http_requests_total" in body
    assert "piq_db_queries_total" in body
