from __future__ import annotations

import csv
from datetime import datetime, timedelta, timezone
from pathlib import Path


class BankrollManager:
    def __init__(self, path: str | Path = "data/bet_log.csv"):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            with self.path.open("w", newline="", encoding="utf-8") as file:
                csv.writer(file).writerow(["date", "race_key", "numero", "decision", "stake", "result", "profit", "capital"])

    def log(self, race_key: str, numero: int, decision: str, stake: float, result: str = "pending", profit: float = 0.0, capital: float = 0.0) -> None:
        with self.path.open("a", newline="", encoding="utf-8") as file:
            csv.writer(file).writerow([datetime.now(timezone.utc).isoformat(), race_key, numero, decision, stake, result, profit, capital])

    def pause_active(self) -> bool:
        if not self.path.exists():
            return False
        with self.path.open(newline="", encoding="utf-8") as file:
            rows = list(csv.DictReader(file))
        losses = 0
        for row in reversed(rows):
            if row.get("result") == "loss":
                losses += 1
            elif row.get("result") in {"win", "place"}:
                break
        if losses < 3 or not rows:
            return False
        try:
            return datetime.fromisoformat(rows[-1]["date"]) + timedelta(hours=24) > datetime.now(timezone.utc)
        except (KeyError, ValueError):
            return False
