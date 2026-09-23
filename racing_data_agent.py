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

JOCKEYS = {
    "jck-001": {"id": "jck-001", "name": "Clément Sorel", "nationality": "France", "wins": 38, "rating": 88},
    "jck-002": {"id": "jck-002", "name": "A. Delaunay", "nationality": "France", "wins": 26, "rating": 84},
    "jck-003": {"id": "jck-003", "name": "L. Bernard", "nationality": "France", "wins": 31, "rating": 86},
    "jck-004": {"id": "jck-004", "name": "S. Martin", "nationality": "France", "wins": 41, "rating": 91},
}

TRAINERS = {
    "trn-001": {"id": "trn-001", "name": "M. Dupont", "nationality": "France", "wins": 52, "rating": 90},
    "trn-002": {"id": "trn-002", "name": "A. Laurent", "nationality": "France", "wins": 44, "rating": 88},
    "trn-003": {"id": "trn-003", "name": "P. Morel", "nationality": "France", "wins": 47, "rating": 89},
}

STABLES = {
    "sta-001": {"id": "sta-001", "name": "Ecurie du Clos", "country": "France"},
    "sta-002": {"id": "sta-002", "name": "Stable Vortex", "country": "France"},
    "sta-003": {"id": "sta-003", "name": "Haras du Nord", "country": "France"},
}

HORSES = {
    "horse-001": {"id": "horse-001", "name": "Asteria du Clos", "age": 5, "sex": "f", "weight": 57.5, "handicap": 22, "distance_pref": "2000m", "surface_pref": "gazon", "stable_id": "sta-001", "rating": 88, "recent_form": ["1er", "2e", "1er"], "musique": "Très rapide fin de course"},
    "horse-002": {"id": "horse-002", "name": "Vortex d'Or", "age": 4, "sex": "m", "weight": 58.0, "handicap": 18, "distance_pref": "2200m", "surface_pref": "gazon", "stable_id": "sta-002", "rating": 86, "recent_form": ["2e", "1er", "3e"], "musique": "S'accroche bien au terrain"},
    "horse-003": {"id": "horse-003", "name": "Velours Royal", "age": 6, "sex": "m", "weight": 59.0, "handicap": 24, "distance_pref": "1600m", "surface_pref": "gazon", "stable_id": "sta-001", "rating": 83, "recent_form": ["3e", "1er", "2e"], "musique": "Bonne accélération"},
    "horse-004": {"id": "horse-004", "name": "Ciel d'Argent", "age": 5, "sex": "f", "weight": 55.5, "handicap": 12, "distance_pref": "1800m", "surface_pref": "gazon", "stable_id": "sta-003", "rating": 81, "recent_form": ["4e", "2e", "1er"], "musique": "Très régulier"},
    "horse-005": {"id": "horse-005", "name": "Sirocco Bleu", "age": 4, "sex": "m", "weight": 58.5, "handicap": 16, "distance_pref": "2100m", "surface_pref": "cendre", "stable_id": "sta-003", "rating": 82, "recent_form": ["2e", "3e", "1er"], "musique": "Bonne tenue"},
    "horse-006": {"id": "horse-006", "name": "Lune de Sable", "age": 7, "sex": "f", "weight": 57.0, "handicap": 20, "distance_pref": "2400m", "surface_pref": "gazon", "stable_id": "sta-002", "rating": 85, "recent_form": ["1er", "2e", "4e"], "musique": "Excellente fin"},
}

MEETINGS = [
    {
        "id": "meeting-chantilly-2026-09-24",
        "name": "Meeting de Chantilly",
        "track": "Chantilly",
        "city": "Chantilly",
        "date": "2026-09-24",
        "country": "France",
        "weather": {"temp_c": 18, "condition": "ensoleillé", "wind_kmh": 15, "state": "piste rapide"},
        "summary": "Rencontre de qualité avec plusieurs favori pour les 2000m sur gazon",
    },
    {
        "id": "meeting-longchamp-2026-09-24",
        "name": "Meeting de Longchamp",
        "track": "Longchamp",
        "city": "Paris",
        "date": "2026-09-24",
        "country": "France",
        "weather": {"temp_c": 19, "condition": "nuageux", "wind_kmh": 12, "state": "terrain équilibré"},
        "summary": "Programme mixte sur une piste de qualité avec partants professionnels",
    },
]

RACES = [
    {
        "id": "race-cht-1",
        "meeting_id": "meeting-chantilly-2026-09-24",
        "number": 1,
        "name": "Prix du Château",
        "start_time": "13:40",
        "discipline": "plat",
        "distance": "1600m",
        "surface": "gazon",
        "class_level": "classe 3",
        "currency": "€",
        "prize": 16000,
        "weather_state": "bon",
        "runners": ["runner-001", "runner-002", "runner-003"],
    },
    {
        "id": "race-cht-2",
        "meeting_id": "meeting-chantilly-2026-09-24",
        "number": 2,
        "name": "Prix de l'Allée",
        "start_time": "14:20",
        "discipline": "plat",
        "distance": "2000m",
        "surface": "gazon",
        "class_level": "classe 2",
        "currency": "€",
        "prize": 22000,
        "weather_state": "très bon",
        "runners": ["runner-004", "runner-005", "runner-006"],
    },
    {
        "id": "race-lch-1",
        "meeting_id": "meeting-longchamp-2026-09-24",
        "number": 1,
        "name": "Prix de la Seine",
        "start_time": "14:05",
        "discipline": "plat",
        "distance": "1800m",
        "surface": "gazon",
        "class_level": "classe 1",
        "currency": "€",
        "prize": 25000,
        "weather_state": "correct",
        "runners": ["runner-007", "runner-008", "runner-009"],
    },
]

RUNNERS = [
    {"id": "runner-001", "race_id": "race-cht-1", "horse_id": "horse-001", "number": 1, "jockey_id": "jck-001", "trainer_id": "trn-001", "stable_id": "sta-001", "recent_rank": "1er", "rating": 88, "weight": 57.5, "draw": 4, "status": "actif"},
    {"id": "runner-002", "race_id": "race-cht-1", "horse_id": "horse-003", "number": 2, "jockey_id": "jck-002", "trainer_id": "trn-002", "stable_id": "sta-001", "recent_rank": "2e", "rating": 83, "weight": 59.0, "draw": 5, "status": "actif"},
    {"id": "runner-003", "race_id": "race-cht-1", "horse_id": "horse-004", "number": 3, "jockey_id": "jck-003", "trainer_id": "trn-003", "stable_id": "sta-003", "recent_rank": "3e", "rating": 81, "weight": 55.5, "draw": 2, "status": "actif"},
    {"id": "runner-004", "race_id": "race-cht-2", "horse_id": "horse-002", "number": 1, "jockey_id": "jck-004", "trainer_id": "trn-001", "stable_id": "sta-002", "recent_rank": "1er", "rating": 86, "weight": 58.0, "draw": 1, "status": "actif"},
    {"id": "runner-005", "race_id": "race-cht-2", "horse_id": "horse-005", "number": 2, "jockey_id": "jck-001", "trainer_id": "trn-002", "stable_id": "sta-003", "recent_rank": "2e", "rating": 82, "weight": 58.5, "draw": 3, "status": "actif"},
    {"id": "runner-006", "race_id": "race-cht-2", "horse_id": "horse-006", "number": 3, "jockey_id": "jck-002", "trainer_id": "trn-003", "stable_id": "sta-002", "recent_rank": "4e", "rating": 85, "weight": 57.0, "draw": 6, "status": "actif"},
    {"id": "runner-007", "race_id": "race-lch-1", "horse_id": "horse-001", "number": 1, "jockey_id": "jck-003", "trainer_id": "trn-001", "stable_id": "sta-001", "recent_rank": "1er", "rating": 88, "weight": 57.5, "draw": 2, "status": "actif"},
    {"id": "runner-008", "race_id": "race-lch-1", "horse_id": "horse-003", "number": 2, "jockey_id": "jck-004", "trainer_id": "trn-002", "stable_id": "sta-001", "recent_rank": "2e", "rating": 83, "weight": 59.0, "draw": 5, "status": "actif"},
    {"id": "runner-009", "race_id": "race-lch-1", "horse_id": "horse-006", "number": 3, "jockey_id": "jck-001", "trainer_id": "trn-003", "stable_id": "sta-002", "recent_rank": "4e", "rating": 85, "weight": 57.0, "draw": 7, "status": "actif"},
]


class RacingDataAgent:
    """Façade de données : cache, météo et catalogue de meetings / races / chevaux.

    Les données sont volontairement réalistes et structurées pour permettre une interface
    moderne et des analyses multi-agents sans dépendre d’un fournisseur externe.
    """

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

    def meetings(self) -> list[dict[str, Any]]:
        return [dict(meeting) for meeting in MEETINGS]

    def meeting(self, meeting_id: str) -> dict[str, Any] | None:
        for meeting in MEETINGS:
            if meeting["id"] == meeting_id:
                return dict(meeting)
        return None

    def races_for_meeting(self, meeting_id: str) -> list[dict[str, Any]]:
        return [dict(race) for race in RACES if race["meeting_id"] == meeting_id]

    def race(self, race_id: str) -> dict[str, Any] | None:
        for race in RACES:
            if race["id"] == race_id:
                return dict(race)
        return None

    def runners_for_race(self, race_id: str) -> list[dict[str, Any]]:
        return [dict(runner) for runner in RUNNERS if runner["race_id"] == race_id]

    def runner(self, runner_id: str) -> dict[str, Any] | None:
        for runner in RUNNERS:
            if runner["id"] == runner_id:
                return dict(runner)
        return None

    def horse(self, horse_id: str) -> dict[str, Any] | None:
        return dict(HORSES.get(horse_id, {})) if horse_id in HORSES else None

    def trainer(self, trainer_id: str) -> dict[str, Any] | None:
        return dict(TRAINERS.get(trainer_id, {})) if trainer_id in TRAINERS else None

    def jockey(self, jockey_id: str) -> dict[str, Any] | None:
        return dict(JOCKEYS.get(jockey_id, {})) if jockey_id in JOCKEYS else None

    def stable(self, stable_id: str) -> dict[str, Any] | None:
        return dict(STABLES.get(stable_id, {})) if stable_id in STABLES else None

    def tracks(self) -> list[dict[str, Any]]:
        return [{"name": name, **data} for name, data in TRACKS.items()]

    def races(self) -> list[dict[str, Any]]:
        return [dict(race) for race in RACES]

    def status(self) -> dict[str, Any]:
        return {
            "service": "RacingDataAgent",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "tracks": len(TRACKS),
            "meetings": len(MEETINGS),
            "races": len(RACES),
            "runners": len(RUNNERS),
            "races_in_cache": len(self.cache.list_races()),
        }

    def meeting_analysis(self, meeting_id: str) -> dict[str, Any]:
        meeting = self.meeting(meeting_id)
        if not meeting:
            return {"meeting_id": meeting_id, "status": "error", "error": "Meeting introuvable"}
        races = self.races_for_meeting(meeting_id)
        summary = f"{meeting['name']} propose {len(races)} courses avec un terrain {meeting['weather']['state']} et une météo {meeting['weather']['condition']}."
        return {"meeting_id": meeting_id, "name": meeting["name"], "summary": summary, "races": races, "weather": meeting["weather"]}

    def race_analysis(self, race_id: str) -> dict[str, Any]:
        race = self.race(race_id)
        if not race:
            return {"race_id": race_id, "status": "error", "error": "Course introuvable"}
        runners = self.runners_for_race(race_id)
        detailed = []
        for runner in runners:
            horse = self.horse(runner["horse_id"]) or {}
            jockey = self.jockey(runner["jockey_id"]) or {}
            trainer = self.trainer(runner["trainer_id"]) or {}
            detailed.append({
                "runner_id": runner["id"],
                "horse": horse.get("name"),
                "rating": runner.get("rating"),
                "jockey": jockey.get("name"),
                "trainer": trainer.get("name"),
                "recent_rank": runner.get("recent_rank"),
                "weight": runner.get("weight"),
                "draw": runner.get("draw"),
            })
        return {"race_id": race_id, "name": race["name"], "summary": f"{race['name']} sur {race['distance']} mérite une attention sur les partants les mieux classés et les couplages les plus stables.", "runners": detailed}
