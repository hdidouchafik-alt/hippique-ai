from __future__ import annotations

import math
from typing import Any


class ValueEngine:
    """Value betting expérimental: scores, softmax, filtres et Kelly prudent."""

    def __init__(self, temperature: float = 10.0):
        if temperature <= 0:
            raise ValueError("La température doit être positive")
        self.temperature = temperature

    @staticmethod
    def implied_probability(odds: float | None) -> float | None:
        return None if not odds or odds <= 1 else 1.0 / odds

    @staticmethod
    def score(runner: dict[str, Any]) -> float:
        form = runner.get("form") or []
        form_score = sum(max(0, 11 - p) / (i + 1) for i, p in enumerate(form))
        form_score = min(100.0, form_score * 4.0) if form else 0.0
        entourage = runner.get("score_entourage")
        market_odds = runner.get("cote_pmu") or runner.get("odds")
        market = (100.0 / market_odds) if market_odds and market_odds > 1 else 0.0
        external_odds = runner.get("cote_betfair_near") or runner.get("cote_betfair_far")
        external = (100.0 / external_odds) if external_odds and external_odds > 1 else market
        entourage_score = float(entourage) if entourage is not None else 50.0
        return round(0.25 * form_score + 0.25 * entourage_score + 0.30 * market + 0.20 * external, 4)

    def softmax(self, scores: list[float]) -> list[float]:
        scaled = [s / self.temperature for s in scores]
        maximum = max(scaled)
        values = [math.exp(s - maximum) for s in scaled]
        total = sum(values) or 1.0
        return [v / total for v in values]

    @staticmethod
    def filters(runner: dict[str, Any], race: dict[str, Any]) -> dict[str, str]:
        filters = {"terrain": "inconnu", "distance": "inconnu", "corde": "inconnu", "poids": "inconnu", "absence": "inconnu", "categorie": "inconnu"}
        if runner.get("terrain_compatible") is not None:
            filters["terrain"] = "ok" if runner["terrain_compatible"] else "eliminatoire"
        if runner.get("distance_compatible") is not None:
            filters["distance"] = "ok" if runner["distance_compatible"] else "eliminatoire"
        if runner.get("corde_compatible") is not None:
            filters["corde"] = "ok" if runner["corde_compatible"] else "eliminatoire"
        if runner.get("long_absence") is not None:
            filters["absence"] = "eliminatoire" if runner["long_absence"] and not runner.get("prep_race") else "ok"
        if runner.get("heavy_weight") is not None:
            filters["poids"] = "eliminatoire" if runner["heavy_weight"] else "ok"
        return filters

    def analyse(self, runners: list[dict[str, Any]], race: dict[str, Any] | None = None, capital: float = 0.0) -> dict[str, Any]:
        race = race or {}
        active = [r for r in runners if str(r.get("status", "active")).lower() not in {"np", "non_partant", "inactive"}]
        scored = [{**r, "score_brut": self.score(r)} for r in active]
        probabilities = self.softmax([r["score_brut"] for r in scored]) if scored else []
        output = []
        for runner, probability in zip(scored, probabilities):
            pmu = runner.get("cote_pmu") or runner.get("odds")
            betfair = [v for v in (runner.get("cote_betfair_near"), runner.get("cote_betfair_far")) if v and v > 1]
            reference_odds = min([pmu, *betfair]) if pmu and betfair else (pmu or (min(betfair) if betfair else None))
            market_probability = self.implied_probability(reference_odds)
            value = probability - market_probability if market_probability is not None else None
            filters = self.filters(runner, race)
            blocked = any(v == "eliminatoire" for v in filters.values())
            uncertainty = float(runner.get("uncertainty_penalty", 0.65 if market_probability is None else 1.0))
            edge = max(0.0, value or 0.0)
            b = (reference_odds - 1) if reference_odds else 0
            kelly = max(0.0, (b * probability - (1 - probability)) / b) if b > 0 else 0.0
            final_fraction = kelly * 0.25 * max(0.0, min(1.0, uncertainty))
            stake = min(capital * 0.05, capital * 0.02 * final_fraction) if capital > 0 else 0.0
            decision = "VALUE" if edge >= 0.05 and not blocked and market_probability is not None else "PASSER"
            if decision == "PASSER":
                stake = 0.0
            output.append({**runner, "probabilite_modele": round(probability, 5), "probabilite_marche": round(market_probability, 5) if market_probability is not None else None, "value": round(value, 5) if value is not None else None, "kelly_brut": round(kelly, 5), "f_final": round(final_fraction, 5), "mise_recommandee": round(stake, 2), "filtres": filters, "decision": decision})
        output.sort(key=lambda r: r["probabilite_modele"], reverse=True)
        for index, item in enumerate(output, 1):
            item["rang"] = index
        return {"temperature": self.temperature, "partants": output, "top5": [r["numero"] for r in output[:5]], "disclaimer": "Test probabiliste, sans garantie de résultat ni conseil de pari."}
