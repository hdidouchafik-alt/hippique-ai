from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any

from racing_data_agent import RacingDataAgent
from source_agents import PublicSourceAgent


class MultiTaskAgent:
    SOURCES = {
        "web": {"label": "Pages web publiques", "status": "available", "auth": False},
        "rss": {"label": "Flux RSS hippiques", "status": "available", "auth": False},
        "weather": {"label": "Météo Open-Meteo", "status": "available", "auth": False},
        "official": {"label": "Sources officielles de courses", "status": "connector_required", "auth": True},
    }

    def __init__(self, horses: dict[str, Any], agents: dict[str, str]):
        self.horses, self.agents = horses, agents
        self.data = RacingDataAgent()
        self.public = PublicSourceAgent()

    @classmethod
    def catalog(cls):
        return {"name": "MultiTaskAgent", "description": "Planifie, collecte, met en cache et orchestre les agents spécialisés.", "sources": cls.SOURCES}

    def health(self):
        return {"agent": "MultiTaskAgent", "checked_at": datetime.now(timezone.utc).isoformat(), "sources": self.SOURCES, "data": self.data.status()}

    def plan(self, task: str) -> list[str]:
        text = task.lower()
        selected = ["CourseAgent", "HorseAgent"]
        if any(x in text for x in ("jockey", "cavalier")): selected.append("JockeyAgent")
        if any(x in text for x in ("entraîneur", "entraineur", "écurie", "ecurie")): selected.append("TrainerAgent")
        if any(x in text for x in ("piste", "terrain", "météo", "meteo", "hippodrome")): selected.append("TrackAgent")
        if any(x in text for x in ("date", "calendrier", "prochaine", "course")): selected.append("CalendarAgent")
        selected.append("ForecastAgent")
        return list(dict.fromkeys(selected))

    async def collect(self, task: str, sources: list[str] | None = None):
        requested = sources or ["rss"]
        jobs, labels = [], []
        if "rss" in requested:
            jobs.append(self.public.rss()); labels.append("rss")
        if "weather" in requested:
            track = next((name for name in self.data.tracks() if name["name"].lower() in task.lower()), "Chantilly")
            jobs.append(self.data.track_weather(track)); labels.append("weather")
        results = await asyncio.gather(*jobs) if jobs else []
        return {"requested": requested, "results": dict(zip(labels, results))}

    async def run(self, task: str, horse: str | None = None, sources: list[str] | None = None):
        chosen = horse or next((n for n in self.horses if n.lower() in task.lower()), next(iter(self.horses)))
        collection = await self.collect(task, sources)
        plan = self.plan(task)
        results = await asyncio.gather(*(self.delegate(name, chosen, collection) for name in plan))
        return {"agent": "MultiTaskAgent", "task": task, "horse": chosen, "plan": plan, "collection": collection, "results": results, "summary": "Mission exécutée avec collecte publique et cache lorsque disponible.", "disclaimer": "Les sources peuvent être indisponibles ou incomplètes. Vérifiez les données officielles; aucune performance n'est garantie."}

    async def delegate(self, name: str, horse: str, collection: dict[str, Any]):
        await asyncio.sleep(0)
        score = self.horses[horse].get("form", 0) if name in ("HorseAgent", "ForecastAgent") else 80
        return {"agent": name, "score": score, "finding": f"{name} a traité la demande concernant {horse}.", "data_used": ["profil local", *collection["results"].keys()]}
