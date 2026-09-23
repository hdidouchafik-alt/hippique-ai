from __future__ import annotations

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)


def test_health():
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_analysis():
    response = client.get("/api/analysis?horse=Asteria%20du%20Clos")
    assert response.status_code == 200
    assert response.json()["horse"]["name"] == "Asteria du Clos"


def test_tracks_and_capabilities():
    assert client.get("/api/tracks").status_code == 200
    assert client.get("/api/capabilities").json()["agent"] == "MultiTaskAgent"


def test_multitask():
    response = client.post("/api/multitask", json={"task": "Analyse la météo à Chantilly"})
    assert response.status_code == 200
    assert "TrackAgent" in response.json()["plan"]
