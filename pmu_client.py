"""Client The Racing API - Programme, partants, résultats."""
from __future__ import annotations

import os
import httpx
from datetime import datetime, timedelta
from typing import Any

RACING_API_USER = os.environ.get("RACING_API_USER", "")
RACING_API_PASS = os.environ.get("RACING_API_PASS", "")
BASE = "https://api.theracingapi.com/v1"
TIMEOUT = 20.0


def _auth() -> tuple[str, str] | None:
    if not RACING_API_USER or not RACING_API_PASS:
        return None
    return (RACING_API_USER, RACING_API_PASS)


async def _get(path: str, params: dict | None = None) -> dict[str, Any] | None:
    auth = _auth()
    if not auth:
        return None
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            r = await client.get(f"{BASE}{path}", params=params, auth=auth)
            r.raise_for_status()
            return r.json()
    except Exception as e:
        return {"_error": str(e)}


def _date_str(offset: int = 0) -> str:
    d = datetime.now() + timedelta(days=offset)
    return d.strftime("%Y-%m-%d")


async def programme(date_offset: int = 0) -> list[dict[str, Any]]:
    """Liste des courses pour une date."""
    date_str = _date_str(date_offset)
    data = await _get("/racecards/free", {"date": date_str})
    if not data or "_error" in data:
        return []

    courses = []
    for item in data.get("racecards", []):
        courses.append({
            "id": f"{date_str}-{item.get('race_id', '')}",
            "date": date_str,
            "reunion": 1,
            "course": item.get("race_no", 0),
            "hippodrome": item.get("course", "?"),
            "nom": item.get("race_name", "Course"),
            "discipline": item.get("type", "?"),
            "distance": item.get("distance_f", "?"),
            "partants": item.get("field_size", 0),
            "heure": item.get("off_time", ""),
            "statut": "En attente",
            "specialite": item.get("type", ""),
            "race_id": item.get("race_id"),
        })
    return courses


async def partants(date_str: str, reunion: int, course: int, race_id: str = "") -> list[dict[str, Any]]:
    """Partants d'une course."""
    data = await _get("/racecards/free", {"date": date_str})
    if not data or "_error" in data:
        return []

    target = None
    for item in data.get("racecards", []):
        if item.get("race_no") == course:
            target = item
            break
    if not target:
        return []

    runners = []
    for r in target.get("runners", []):
        runners.append({
            "num": r.get("number"),
            "nom": r.get("horse", "?"),
            "driver": r.get("jockey", "") or r.get("trainer", ""),
            "entraineur": r.get("trainer", ""),
            "age": r.get("age"),
            "sexe": "",
            "gains": 0,
            "musique": [],
            "cote": None,
            "cote_probable": None,
            "deferre": "",
            "np": False,
        })
    return runners


async def arrivee(date_str: str, reunion: int, course: int, race_id: str = "") -> list[dict[str, Any]]:
    """Résultats d'une course."""
    data = await _get("/results", {"date": date_str})
    if not data or "_error" in data:
        return []

    for item in data.get("results", []):
        if item.get("race_no") == course:
            return [r.get("position") for r in item.get("runners", []) if r.get("position")]
    return []