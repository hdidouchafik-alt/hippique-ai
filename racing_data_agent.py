from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from cache_store import CacheStore
from source_agents import PublicSourceAgent

TRACKS = {
    "Chantilly": {"latitude": 49.187, "longitude": 2.471, "surface": "gazon", "state": "gazon ferme"},
    "Longchamp": {"latitude": 48.862, "longitude": 2.237, "surface": "gazon", "state": "terrain équilibré"},
    "Deauville": {"latitude": 49.356, "longitude": 0.071, "surface": "gazon", "state": "variable"},
    "Vincennes": {"latitude": 48.821, "longitude": 2.449, "surface": "cendrée", "state": "piste spécialisée"},
}


class RacingDataAgent:
    """Façade de données : cache, météo et catalogue de courses importables."""

    def __init__(self, cache: CacheStore | None = None):
        self.cache = cache or CacheStore()
        self.public = PublicSourceAgent()

    async def track_weather(self, track: str) -> dict[str, Any]:
        if track not in TRACKS:
            return {"status": "error", "error": "Hippodrome inconnu"}
        key = f"weather:{track}"
        cached = self.cache.get(key)
        if cached:
            cached["cached"] = True
            return cached
        info = TRACKS[track]
        result = await self.public.weather(info["latitude"], info["longitude"])
        result.update({"track": track, "surface": info["surface"], "track_state_reference": info["state"]})
        self.cache.set(key, result, ttl=600)
        return result

    def tracks(self) -> list[dict[str, Any]]:
        return [{"name": name, **data} for name, data in TRACKS.items()]

    def races(self) -> list[dict[str, Any]]:
        return self.cache.list_races()

    def status(self) -> dict[str, Any]:
        return {"service": "RacingDataAgent", "updated_at": datetime.now(timezone.utc).isoformat(), "tracks": len(TRACKS), "races_in_cache": len(self.races())}
