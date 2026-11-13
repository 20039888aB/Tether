from fastapi.testclient import TestClient

from app.main import app


def test_liveness_reports_running_process() -> None:
    response = TestClient(app).get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_readiness_fails_explicitly_without_database_configuration() -> None:
    response = TestClient(app).get("/api/v1/health/ready")

    assert response.status_code == 503
    assert response.json() == {"detail": "database_not_configured"}
