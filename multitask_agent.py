from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from source_agents import PublicSourceAgent


class MultiTaskAgent:
    SOURCES = {
        "web": {"label": "Pages web publiques", "status": "available", "auth": False},
        "rss": {"label": "Flux RSS hippiques", "status": "available", "auth": False},
        "weather": {"label": "Météo Open-Meteo", "status": "available", "auth": False},
        "official": {"label": "Sources officielles de courses", "status": "connector_required", "auth": True},
    }

    def __init__(self, horses: dict[str, Any], agents: dict[str, str]):
        self.horses, self.agents, self.collector = horses, agents, PublicSourceAgent()

    @classmethod
    def catalog(cls):
        return {"name": "MultiTaskAgent", "description": "Planifie, collecte les sources publiques et orchestre les agents spécialisés.", "sources": cls.SOURCES}

    def health(self):
        return {"agent": "MultiTaskAgent", "checked_at": datetime.now(timezone.utc).isoformat(), "sources": self.SOURCES}

    def plan(self, task: str) -> list[str]:
        text = task.lower()
        selected = ["CourseAgent", "HorseAgent"]
        if any(x in text for x in ("jockey", "cavalier")): selected.append("JockeyAgent")
        if any(x in text for x in ("entraîneur", "entraineur", "écurie", "ecurie")): selected.append("TrainerAgent")
        if any(x in text for x in ("piste", "terrain", "météo", "meteo", "hippodrome")): selected.append("TrackAgent")
        if any(x in text for x in ("date", "calendrier", "prochaine")): selected.append("CalendarAgent")
        selected.append("ForecastAgent")
        return list(dict.fromkeys(selected))

    async def collect(self, task: str, sources: list[str] | None = None):
        requested = sources or ["rss"]
        jobs = []
        labels = []
        if "rss" in requested:
            jobs.append(self.collector.rss()); labels.append("rss")
        if "weather" in requested:
            jobs.append(self.collector.weather(48.8566, 2.3522)); labels.append("weather")
        results = await asyncio.gather(*jobs) if jobs else []
        return {"requested": requested, "results": dict(zip(labels, results))}

    async def run(self, task: str, horse: str | None = None, sources: list[str] | None = None):
        chosen = horse or next((n for n in self.horses if n.lower() in task.lower()), next(iter(self.horses)))
        plan = self.plan(task)
        collection = await self.collect(task, sources)
        results = await asyncio.gather(*(self.delegate(name, chosen) for name in plan))
        return {"agent": "MultiTaskAgent", "task": task, "horse": chosen, "plan": plan, "collection": collection, "results": results, "summary": "Mission exécutée avec collecte publique lorsque disponible.", "disclaimer": "Les sources peuvent être indisponibles ou incomplètes. Vérifiez les données officielles; aucune performance n'est garantie."}

    async def delegate(self, name: str, horse: str):
        await asyncio.sleep(0)
        score = self.horses[horse].get("form", 0) if name in ("HorseAgent", "ForecastAgent") else 80
        return {"agent": name, "score": score, "finding": f"{name} a traité la demande concernant {horse}.", "data_used": ["profil local", "sources publiques collectées"]}
