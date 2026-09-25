"""Agents actifs - analyse réelle des courses."""
from __future__ import annotations

import re
from typing import Any


def _points_musique(musique: list[str]) -> float:
    total = 0.0
    for i, m in enumerate(musique[:5]):
        num = re.sub(r"[^0-9]", "", str(m))
        if num:
            p = int(num)
            if 1 <= p <= 9:
                total += max(0, 11 - p) * (1 / (i + 1))
    return min(total / 8, 10)


def _driver_bonus(driver: str) -> float:
    tops = {
        "E. Raffin": 2.0, "M. Abrivard": 1.8, "F. Nivard": 2.0,
        "D. Thomain": 1.6, "B. Rochard": 1.5, "A. Barrier": 1.5,
        "P.ph. Ploquin": 1.4, "N. Bazire": 1.8, "J.m. Bazire": 1.8,
        "Y. Lebourgeois": 1.5, "A. Abrivard": 1.4, "T. Le Beller": 1.2,
        "C. Demuro": 2.0, "M. Guyon": 1.9, "C. Soumillon": 2.0,
        "S. Pasquier": 1.9, "Pc. Boudot": 1.8, "M. Barzalona": 1.7,
        "A. Hamelin": 1.5, "E. Hardouin": 1.4, "T. Bachelot": 1.3,
    }
    for k, v in tops.items():
        if driver and k.lower() in driver.lower():
            return v
    return 0.5


def _gains_score(gains: int) -> float:
    if not gains:
        return 0.0
    return min(gains / 300000, 1.0) * 3


def form_agent(runner: dict) -> dict:
    musique = runner.get("musique", []) or []
    score = _points_musique(musique)
    detail = "Musique: " + " ".join(musique[:5]) if musique else "Pas de musique"
    return {"agent": "FormAgent", "score": round(score, 2), "detail": detail}


def driver_agent(runner: dict) -> dict:
    driver = runner.get("driver") or runner.get("jockey") or ""
    score = _driver_bonus(driver)
    return {"agent": "DriverAgent", "score": round(score, 2), "detail": "Driver: " + (driver or "—")}


def market_agent(runner: dict) -> dict:
    cote = runner.get("cote") or runner.get("cote_finale") or 0
    if cote and cote > 0:
        score = min(10 / cote, 10)
        detail = "Cote: " + str(cote)
    else:
        score = 0.5
        detail = "Cote inconnue"
    return {"agent": "MarketAgent", "score": round(score, 2), "detail": detail}


def class_agent(runner: dict) -> dict:
    gains = runner.get("gains", 0) or 0
    score = _gains_score(gains)
    detail = "Gains: " + str(gains) + " EUR" if gains else "Gains: 0"
    return {"agent": "ClassAgent", "score": round(score, 2), "detail": detail}


def track_agent(runner: dict, terrain: str = "") -> dict:
    score = 1.0
    detail = "Terrain: " + (terrain or "inconnu")
    return {"agent": "TrackAgent", "score": score, "detail": detail}


def risk_agent(runner: dict) -> dict:
    musique = runner.get("musique", []) or []
    da_count = sum(1 for m in musique[:5] if str(m).lower().startswith("d"))
    score = max(0, 2 - da_count * 0.5)
    return {"agent": "RiskAgent", "score": round(score, 2), "detail": str(da_count) + " disqualification(s)"}


def analyse_runner(runner: dict) -> dict:
    analyses = [
        form_agent(runner),
        driver_agent(runner),
        market_agent(runner),
        class_agent(runner),
        risk_agent(runner),
    ]
    total = sum(a["score"] for a in analyses)
    return {
        "num": runner.get("num"),
        "nom": runner.get("nom") or runner.get("name"),
        "score_total": round(total, 2),
        "analyses": analyses,
    }


def analyse_course(runners: list[dict]) -> list[dict]:
    resultats = [analyse_runner(r) for r in runners]
    resultats.sort(key=lambda x: x["score_total"], reverse=True)
    for i, r in enumerate(resultats):
        r["rank"] = i + 1
    return resultats