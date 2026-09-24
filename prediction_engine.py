from __future__ import annotations

import re
from typing import Any

from prediction_store import PredictionStore


RUN_RE = re.compile(r"(?<!\d)([0-9])p")
RUNNER_RE = re.compile(r"(?m)^\s*(1[0-6]|[1-9])\s*\n\s*([A-ZÀ-Ý][A-ZÀ-Ý' -]{2,})\s*$")
ODDS_RE = re.compile(r"(?m)^\s*(\d{1,3}(?:[.,]\d)?)\s*$")


class PredictionEngine:
    """Moteur déterministe et explicable. Il est calibré par l'historique, pas magique."""

    def __init__(self, store: PredictionStore | None = None):
        self.store = store or PredictionStore()

    def parse_text(self, text: str) -> list[dict[str, Any]]:
        normalized = text.replace("\r", "")
        runners: list[dict[str, Any]] = []
        matches = list(RUNNER_RE.finditer(normalized))
        for index, match in enumerate(matches):
            number, name = int(match.group(1)), " ".join(match.group(2).split()).title()
            block = normalized[match.end(): matches[index + 1].start() if index + 1 < len(matches) else len(normalized)]
            if re.search(r"Non Partant|\bNP\b", block, re.I):
                continue
            form = [int(value) for value in RUN_RE.findall(block)][:10]
            weight_match = re.search(r"Poids\s*:\s*[\d.,]+\s*/\s*([\d.,]+)kg", block, re.I)
            corde_match = re.search(r"Corde\s*:\s*(\d+)", block, re.I)
            odds = [float(value.replace(',', '.')) for value in ODDS_RE.findall(block) if float(value.replace(',', '.')) >= 1]
            runners.append({"number": number, "name": name, "form": form, "weight": float(weight_match.group(1).replace(',', '.')) if weight_match else None, "corde": int(corde_match.group(1)) if corde_match else None, "odds": odds[-1] if odds else None, "status": "active"})
        return runners

    def rank(self, runners: list[dict[str, Any]], race_key: str, race_name: str = "Course importée", race_date: str | None = None, limit: int = 5) -> dict[str, Any]:
        if not runners:
            raise ValueError("Aucun partant actif reconnu")
        weights = self.store.weights()
        scored = []
        for runner in runners:
            form = runner.get("form") or []
            form_score = sum(max(0, 11 - place) * (1 / (index + 1)) for index, place in enumerate(form)) / 10
            odds = runner.get("odds")
            market_score = 1 / odds if odds and odds > 0 else 0.1
            weight_score = 1 / max(float(runner.get("weight") or 60), 1)
            corde = runner.get("corde") or 8
            corde_score = 1 - abs(corde - 8) / 16
            raw = weights["form"] * form_score + weights["odds"] * market_score + weights["weight"] * weight_score + weights["corde"] * corde_score + weights["market"] * market_score
            scored.append({**runner, "score": round(raw, 5), "reasons": {"form": round(form_score, 3), "market": round(market_score, 3), "weight": round(weight_score, 3), "corde": round(corde_score, 3)}})
        scored.sort(key=lambda item: item["score"], reverse=True)
        ranking = [{"rank": index + 1, **runner} for index, runner in enumerate(scored[:limit])]
        prediction_id = self.store.save_prediction(race_key, race_name, race_date, runners, ranking, {"weights": weights})
        return {"prediction_id": prediction_id, "race_key": race_key, "ranking": ranking, "non_runners": [], "method": "score explicable + calibration historique", "disclaimer": "Estimation probabiliste, sans garantie de résultat ni conseil de pari."}
