from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree


class PublicSourceAgent:
    """Collecte des données publiques sans contourner les protections des sites."""

    DEFAULT_RSS = [
        "https://www.france-galop.com/fr/actualites/rss",
        "https://www.equidia.fr/articles/rss",
    ]

    @staticmethod
    def _get(url: str, timeout: int = 10) -> str:
        request = Request(url, headers={"User-Agent": "HippiqueAI/0.3 (+public-data-reader)"})
        with urlopen(request, timeout=timeout) as response:
            return response.read().decode("utf-8", errors="replace")

    async def web(self, url: str) -> dict[str, Any]:
        if urlparse(url).scheme not in {"http", "https"}:
            return {"source": url, "status": "error", "error": "URL HTTP(S) requise"}
        try:
            html = await asyncio.to_thread(self._get, url)
            text = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", " ", html, flags=re.I)
            text = re.sub(r"<[^>]+>", " ", text)
            text = re.sub(r"\s+", " ", text).strip()
            return {"source": url, "status": "ok", "collected_at": self.now(), "content": text[:12000]}
        except Exception as exc:
            return {"source": url, "status": "error", "error": str(exc)}

    async def rss(self, urls: list[str] | None = None) -> dict[str, Any]:
        feeds = urls or self.DEFAULT_RSS
        async def read(url: str):
            try:
                raw = await asyncio.to_thread(self._get, url)
                root = ElementTree.fromstring(raw)
                items = []
                for item in root.findall(".//item")[:10]:
                    items.append({
                        "title": self.node(item, "title"),
                        "link": self.node(item, "link"),
                        "date": self.node(item, "pubDate"),
                        "description": self.node(item, "description")[:500],
                    })
                return {"source": url, "status": "ok", "collected_at": self.now(), "items": items}
            except Exception as exc:
                return {"source": url, "status": "error", "error": str(exc), "items": []}
        return {"type": "rss", "feeds": await asyncio.gather(*(read(url) for url in feeds))}

    async def weather(self, latitude: float, longitude: float) -> dict[str, Any]:
        url = f"https://api.open-meteo.com/v1/forecast?latitude={latitude}&longitude={longitude}&current=temperature_2m,precipitation,wind_speed_10m&timezone=auto"
        try:
            payload = json.loads(await asyncio.to_thread(self._get, url))
            return {"source": "Open-Meteo", "status": "ok", "collected_at": self.now(), "data": payload.get("current", {}), "coordinates": {"latitude": latitude, "longitude": longitude}}
        except Exception as exc:
            return {"source": "Open-Meteo", "status": "error", "error": str(exc)}

    @staticmethod
    def node(parent: ElementTree.Element, name: str) -> str:
        value = parent.findtext(name)
        return (value or "").strip()

    @staticmethod
    def now() -> str:
        return datetime.now(timezone.utc).isoformat()
