from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any


class MultiTaskAgent:
    """Orchestrateur local : décompose une demande et délègue aux agents hippiques.

    Il ne collecte pas de données externes automatiquement. Les connecteurs sont
    déclarés comme capacités et peuvent être remplacés par des API autorisées.
    """

    SOURCES = {
        "web": {"label": "Pages web publiques", "status": "available", "auth": False},
        "rss": {"label": "Flux RSS hippiques", "status": "available", "auth": False},
        "official": {"label": "Sources officielles de courses", "status": "connector_required", "auth": True},
        "weather": {"label": "Météo et état de piste", "status": "connector_required", "auth": True},
    }

    def __init__(self, horses: dict[str, Any], agents: dict[str, str]):
        self.horses = horses
        self.agents = agents

    @classmethod
    def catalog(cls):
        return {"name": "MultiTaskAgent", "description": "Décompose une demande, consulte les capacités disponibles et orchestre les agents spécialisés.", "sources": cls.SOURCES}

    def health(self):
        return {"agent": "MultiTaskAgent", "checked_at": datetime.now(timezone.utc).isoformat(), "sources": self.SOURCES, "note": "Les connecteurs externes nécessitent une configuration explicite."}

    def plan(self, task: str) -> list[str]:
        text = task.lower()
        selected = ["CourseAgent", "HorseAgent"]
        if any(word in text for word in ("jockey", "cavalier")): selected.append("JockeyAgent")
        if any(word in text for word in ("entraîneur", "entraineur", "écurie", "ecurie")): selected.append("TrainerAgent")
        if any(word in text for word in ("piste", "terrain", "météo", "meteo", "hippodrome")): selected.append("TrackAgent")
        if any(word in text for word in ("date", "calendrier", "prochaine")): selected.append("CalendarAgent")
        selected.append("ForecastAgent")
        return list(dict.fromkeys(selected))

    async def run(self, task: str, horse: str | None = None, sources: list[str] | None = None):
        chosen_horse = horse or next((name for name in self.horses if name.lower() in task.lower()), next(iter(self.horses)))
        plan = self.plan(task)
        requested_sources = sources or ["official", "weather"]
        source_report = [{"name": name, **self.SOURCES.get(name, {"label": "Inconnue", "status": "unknown", "auth": False})} for name in requested_sources]
        jobs = [self._delegate(name, chosen_horse, task) for name in plan]
        results = await asyncio.gather(*jobs)
        return {"agent": "MultiTaskAgent", "task": task, "plan": plan, "horse": chosen_horse, "source_report": source_report, "results": results, "summary": "La demande a été décomposée et traitée par les agents disponibles.", "disclaimer": "Les résultats sont indicatifs. Aucune donnée externe n'est inventée et aucune performance n'est garantie."}

    async def _delegate(self, name: str, horse: str, task: str):
        data = self.horses[horse]
        await asyncio.sleep(0)
        score = data.get("form", 0) if name in ("HorseAgent", "ForecastAgent") else 80
        return {"agent": name, "score": score, "finding": f"{name} a traité la demande concernant {horse}.", "data_used": ["profil de démonstration", "demande utilisateur"]}
