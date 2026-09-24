from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


class PredictionStore:
    """Persistance durable des pronostics, arrivées et métriques d'évaluation."""

    def __init__(self, path: str | Path = "data/hippique.sqlite3"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.executescript(
                """
                CREATE TABLE IF NOT EXISTS predictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    race_key TEXT NOT NULL,
                    race_name TEXT NOT NULL,
                    race_date TEXT,
                    runners TEXT NOT NULL,
                    ranking TEXT NOT NULL,
                    features TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    UNIQUE(race_key)
                );
                CREATE TABLE IF NOT EXISTS outcomes (
                    prediction_id INTEGER PRIMARY KEY,
                    arrival TEXT NOT NULL,
                    scored_at REAL NOT NULL,
                    FOREIGN KEY(prediction_id) REFERENCES predictions(id)
                );
                CREATE TABLE IF NOT EXISTS model_weights (
                    name TEXT PRIMARY KEY,
                    value REAL NOT NULL,
                    updated_at REAL NOT NULL
                );
                """
            )
            defaults = {"form": 0.42, "odds": 0.22, "weight": 0.12, "corde": 0.10, "market": 0.14}
            for name, value in defaults.items():
                db.execute("INSERT OR IGNORE INTO model_weights VALUES (?, ?, ?)", (name, value, time.time()))
            db.commit()

    def save_prediction(self, race_key: str, race_name: str, race_date: str | None, runners: list[dict[str, Any]], ranking: list[dict[str, Any]], features: dict[str, Any]) -> int:
        with sqlite3.connect(self.path) as db:
            db.execute(
                "INSERT OR REPLACE INTO predictions(race_key,race_name,race_date,runners,ranking,features,created_at) VALUES(?,?,?,?,?,?,?)",
                (race_key, race_name, race_date, json.dumps(runners, ensure_ascii=False), json.dumps(ranking, ensure_ascii=False), json.dumps(features, ensure_ascii=False), time.time()),
            )
            prediction_id = db.execute("SELECT id FROM predictions WHERE race_key = ?", (race_key,)).fetchone()[0]
            db.commit()
        return int(prediction_id)

    def save_outcome(self, prediction_id: int, arrival: list[int]) -> dict[str, Any]:
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT ranking FROM predictions WHERE id = ?", (prediction_id,)).fetchone()
            if not row:
                raise KeyError("Pronostic introuvable")
            ranking = json.loads(row[0])
            predicted = [int(item["number"]) for item in ranking]
            actual = [int(number) for number in arrival]
            hits = [number for number in predicted if number in actual[:5]]
            top1 = predicted[0] == actual[0] if actual else False
            db.execute("INSERT OR REPLACE INTO outcomes VALUES (?, ?, ?)", (prediction_id, json.dumps(actual), time.time()))
            self._learn(db, ranking, actual)
            db.commit()
        return {"prediction_id": prediction_id, "predicted": predicted, "arrival": actual, "hits_top5": hits, "hits_count": len(hits), "top1": top1, "evaluated_at": time.time()}

    def _learn(self, db: sqlite3.Connection, ranking: list[dict[str, Any]], arrival: list[int]) -> None:
        """Calibration en ligne prudente : ajuste les poids, sans prétendre à un entraînement ML."""
        if not arrival:
            return
        predicted = [int(item["number"]) for item in ranking]
        success = len(set(predicted[:5]) & set(arrival[:5])) / 5
        direction = (success - 0.4) * 0.02
        rows = db.execute("SELECT name, value FROM model_weights").fetchall()
        for name, value in rows:
            adjustment = direction if name in {"form", "market"} else -direction / 3
            db.execute("UPDATE model_weights SET value = ?, updated_at = ? WHERE name = ?", (max(0.02, min(0.8, value + adjustment)), time.time(), name))
        total = db.execute("SELECT SUM(value) FROM model_weights").fetchone()[0] or 1
        for name, value in db.execute("SELECT name, value FROM model_weights").fetchall():
            db.execute("UPDATE model_weights SET value = ? WHERE name = ?", (value / total, name))

    def weights(self) -> dict[str, float]:
        with sqlite3.connect(self.path) as db:
            return {name: value for name, value in db.execute("SELECT name, value FROM model_weights ORDER BY name")}

    def history(self, limit: int = 20) -> list[dict[str, Any]]:
        with sqlite3.connect(self.path) as db:
            rows = db.execute("SELECT id,race_key,race_name,race_date,ranking,created_at FROM predictions ORDER BY id DESC LIMIT ?", (min(limit, 100),)).fetchall()
        return [{"id": row[0], "race_key": row[1], "race_name": row[2], "race_date": row[3], "ranking": json.loads(row[4]), "created_at": row[5]} for row in rows]

    def metrics(self) -> dict[str, Any]:
        with sqlite3.connect(self.path) as db:
            rows = db.execute("SELECT p.ranking,o.arrival FROM predictions p JOIN outcomes o ON o.prediction_id=p.id").fetchall()
        if not rows:
            return {"evaluated_predictions": 0, "top5_hit_rate": None, "top1_hit_rate": None, "average_hits": None, "weights": self.weights()}
        scores = []
        top1 = 0
        for ranking, arrival in rows:
            predicted = [int(item["number"]) for item in json.loads(ranking)]
            actual = json.loads(arrival)
            scores.append(len(set(predicted[:5]) & set(actual[:5])))
            top1 += bool(predicted and actual and predicted[0] == actual[0])
        return {"evaluated_predictions": len(rows), "top5_hit_rate": round(sum(score > 0 for score in scores) / len(scores), 3), "top1_hit_rate": round(top1 / len(rows), 3), "average_hits": round(sum(scores) / len(scores), 2), "weights": self.weights()}
