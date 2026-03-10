"""Test API endpoints."""
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from api.main import app
    return TestClient(app)


def test_health(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "running"
    assert data["version"] == "2.0.0"
    assert data["agents_available"] >= 5
    assert data["features_count"] >= 50


def test_agents(client):
    resp = client.get("/api/agents")
    assert resp.status_code == 200
    data = resp.json()
    assert isinstance(data, list)
    assert len(data) >= 5
    for agent in data:
        assert "agent_id" in agent
        assert "agent_name" in agent
        assert "weight" in agent


def test_risk(client):
    resp = client.get("/api/risk")
    assert resp.status_code == 200
    data = resp.json()
    assert "balance" in data
    assert "daily_pnl" in data
    assert data["balance"] == 50000.0


def test_overview(client):
    resp = client.get("/api/overview")
    assert resp.status_code == 200
    data = resp.json()
    assert "account_balance" in data
    assert "mode" in data
    assert data["mode"] == "sandbox"
