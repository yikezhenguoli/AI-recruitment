from fastapi.testclient import TestClient

from ttc.main import app


def test_live_probe_returns_ok_and_request_id() -> None:
    with TestClient(app) as client:
        response = client.get("/api/v1/health/live", headers={"X-Request-Id": "test-req-1"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-Id"] == "test-req-1"
