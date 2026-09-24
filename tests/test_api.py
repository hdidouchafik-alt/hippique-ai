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


def test_prediction_lifecycle():
    text = """1\nCHEVAL UN\nH / 3 ans\nCorde : 3\nVal. Hand. / Poids : 35 / 58kg\n1p\n2p\n\n2\nCHEVAL DEUX\nF / 3 ans\nCorde : 8\nVal. Hand. / Poids : 34 / 57kg\n3p\n4p"""
    response = client.post("/api/predictions", json={"race_key": "test-lifecycle", "race_name": "Test", "text": text})
    assert response.status_code == 200
    prediction_id = response.json()["prediction_id"]
    result = client.post(f"/api/predictions/{prediction_id}/outcome", json={"arrival": [1, 2]})
    assert result.status_code == 200
    assert result.json()["hits_count"] >= 1
