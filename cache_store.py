from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any


class CacheStore:
    """Cache SQLite léger avec expiration pour les collectes publiques."""

    def __init__(self, path: str | Path = "data/hippique.sqlite3"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path) as db:
            db.execute("CREATE TABLE IF NOT EXISTS cache (key TEXT PRIMARY KEY, value TEXT NOT NULL, expires_at REAL NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS races (id TEXT PRIMARY KEY, payload TEXT NOT NULL, updated_at REAL NOT NULL)")
            db.commit()

    def get(self, key: str) -> Any | None:
        with sqlite3.connect(self.path) as db:
            row = db.execute("SELECT value, expires_at FROM cache WHERE key = ?", (key,)).fetchone()
        if not row or row[1] <= time.time():
            return None
        return json.loads(row[0])

    def set(self, key: str, value: Any, ttl: int = 900) -> None:
        with sqlite3.connect(self.path) as db:
            db.execute("INSERT OR REPLACE INTO cache VALUES (?, ?, ?)", (key, json.dumps(value, ensure_ascii=False), time.time() + ttl))
            db.commit()

    def save_races(self, races: list[dict[str, Any]]) -> None:
        with sqlite3.connect(self.path) as db:
            for race in races:
                race_id = str(race.get("id") or race.get("name"))
                db.execute("INSERT OR REPLACE INTO races VALUES (?, ?, ?)", (race_id, json.dumps(race, ensure_ascii=False), time.time()))
            db.commit()

    def list_races(self) -> list[dict[str, Any]]:
        with sqlite3.connect(self.path) as db:
            rows = db.execute("SELECT payload FROM races ORDER BY updated_at DESC").fetchall()
        return [json.loads(row[0]) for row in rows]
