"""Tests for the health endpoint."""

from fastapi.testclient import TestClient

from obsidian_palace.app import app


class TestHealth:
    def test_health_returns_ok(self) -> None:
        client = TestClient(app)
        resp = client.get("/health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "ok"
        assert "version" in body
