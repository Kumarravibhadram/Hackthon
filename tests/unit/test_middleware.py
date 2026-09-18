from fastapi.testclient import TestClient

from backend.app.main import app


client = TestClient(app, raise_server_exceptions=False)


def test_health_response_contains_request_context_headers() -> None:
    response = client.get("/health", headers={"X-Request-ID": "test-request-1"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"] == "test-request-1"
    assert float(response.headers["X-Process-Time-MS"]) >= 0


def test_root_route_returns_api_metadata() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json()["message"] == "Bank Employee AI Workspace API"


def test_unknown_route_includes_cors_headers() -> None:
    response = client.get("/unknown", headers={"Origin": "http://localhost:3000"})

    assert response.status_code == 404
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_knowledge_search_returns_approved_results() -> None:
    response = client.post(
        "/api/v1/knowledge/search",
        json={"query": "What are the identity checks for customer verification?"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["query"].startswith("What are")
    assert payload["results"]
    assert "customer-verification-policy.md" in payload["results"][0]["citation"]