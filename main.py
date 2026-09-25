from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from multitask_agent import MultiTaskAgent
from prediction_engine import PredictionEngine
from prediction_store import PredictionStore
from racing_data_agent import RacingDataAgent

try:
    from agents import analyse_course
    AGENTS_MODULE_OK = True
except ImportError:
    AGENTS_MODULE_OK = False

import httpx
from datetime import datetime, timedelta

app = FastAPI(title="Hippique AI", version="1.5.0")
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

COLLECTED_RESULTS = []

HORSES = {
    "Asteria du Clos": {"age": 5, "form": 82, "surface": "gazon", "distance": "2000m", "speed": 88, "stamina": 84, "traction": 80, "last_runs": ["1er", "2e", "1er"]},
    "Vortex d'Or": {"age": 4, "form": 76, "surface": "piste lourde", "distance": "1600m", "speed": 84, "stamina": 79, "traction": 86, "last_runs": ["2e", "3e", "1er"]},
}

AGENTS = {
    "CourseAgent": "Analyse le rythme et la distance.",
    "HorseAgent": "Analyse la forme et les aptitudes.",
    "JockeyAgent": "Évalue la stratégie du jockey.",
    "TrainerAgent": "Évalue la préparation de l'écurie.",
    "TrackAgent": "Analyse piste, terrain et météo.",
    "CalendarAgent": "Organise les prochaines échéances.",
    "ForecastAgent": "Consolide les signaux sans garantie.",
}

data_agent = RacingDataAgent()
prediction_store = PredictionStore()
prediction_engine = PredictionEngine(prediction_store)


class ChatMessage(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class MultiTaskRequest(BaseModel):
    task: str = Field(min_length=1, max_length=4000)
    horse: str | None = None
    sources: list[str] = Field(default_factory=list)


class PredictionRequest(BaseModel):
    race_key: str = Field(min_length=1, max_length=150)
    race_name: str = Field(default="Course importée", max_length=200)
    race_date: str | None = None
    text: str = Field(min_length=20, max_length=100000)


class OutcomeRequest(BaseModel):
    arrival: list[int] = Field(min_length=1, max_length=50)


def analysis(name: str):
    h = HORSES.get(name, {"form": 0, "surface": "inconnue", "distance": "inconnue", "last_runs": []})
    return {
        "horse": {"name": name, **h},
        "summary": f"{name} présente une forme de {h['form']}/100.",
        "agents": [{"name": n, "specialty": d, "score": 80} for n, d in AGENTS.items()],
    }


# ============ PAGES ============

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/pronostics", response_class=HTMLResponse)
async def pronostics_page(request: Request):
    return templates.TemplateResponse(request, "pronostics.html")


@app.get("/learning", response_class=HTMLResponse)
async def learning_page(request: Request):
    return templates.TemplateResponse(request, "learning.html")


# ============ API ============

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "service": "Hippique AI",
        "version": app.version,
        "agents_module": AGENTS_MODULE_OK,
        "results_collected": len(COLLECTED_RESULTS),
    }


@app.get("/api/agents")
async def agents():
    return {"agents": AGENTS, "multitask": MultiTaskAgent.catalog()}


@app.get("/api/tracks")
async def tracks():
    return {"tracks": data_agent.tracks()}


@app.get("/api/races")
async def races():
    return {"races": data_agent.races()}


@app.get("/api/analysis")
async def get_analysis(horse: str = "Asteria du Clos"):
    return analysis(horse)


@app.post("/api/chat")
async def chat(payload: ChatMessage):
    return {"reply": "Chat côté navigateur."}


@app.post("/api/predictions")
async def create_prediction(payload: PredictionRequest):
    runners = prediction_engine.parse_text(payload.text)
    result = prediction_engine.rank(runners, payload.race_key, payload.race_name, payload.race_date)
    result["runners_count"] = len(runners)
    return result


@app.get("/api/predictions")
async def prediction_history(limit: int = 20):
    return {"predictions": prediction_store.history(limit)}


@app.get("/api/learning/metrics")
async def learning_metrics():
    return prediction_store.metrics()


@app.post("/api/agents/analyse")
async def agents_analyse(payload: dict):
    if not AGENTS_MODULE_OK:
        return {"error": "Module agents non disponible", "resultats": []}
    runners = payload.get("runners", [])
    try:
        return {"resultats": analyse_course(runners)}
    except Exception as e:
        return {"error": str(e), "resultats": []}


# ============ AGENT COLLECTE ARRIVÉES ============

PMU_BASE = "https://online.turfinfo.api.pmu.fr/rest/client/61"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; HippiqueAI/1.0)"}


def _date_str(offset: int = 0) -> str:
    d = datetime.now() + timedelta(days=offset)
    return d.strftime("%d%m%Y")


async def _pmu_get(url: str):
    try:
        async with httpx.AsyncClient(timeout=20.0, headers=HEADERS) as client:
            r = await client.get(url)
            if r.status_code != 200:
                return None
            return r.json()
    except Exception:
        return None


async def _get_arrivee_participants(date_str: str, reunion: int, course: int) -> list:
    url = f"{PMU_BASE}/programme/{date_str}/R{reunion}/C{course}/participants"
    data = await _pmu_get(url)
    if not data or not isinstance(data, dict):
        return []

    participants = data.get("participants") or []
    classes = []

    for p in participants:
        if not isinstance(p, dict):
            continue
        place = p.get("place") or p.get("ordreArrivee") or p.get("position")
        num = p.get("numPmu")
        if place and num:
            try:
                classes.append((int(place), int(num)))
            except (ValueError, TypeError):
                continue

    classes.sort(key=lambda x: x[0])
    return [num for _, num in classes[:5]]


@app.get("/api/agent/collect")
@app.post("/api/agent/collect")
async def agent_collect(offset: int = 0):
    date_str = _date_str(offset)
    programme = await _pmu_get(f"{PMU_BASE}/programme/{date_str}")
    if not programme:
        return {"ok": False, "nouvelles": 0, "total": len(COLLECTED_RESULTS)}

    reunions = []
    if isinstance(programme, dict):
        reunions = (programme.get("programme") or {}).get("reunions") or []

    nouvelles = 0

    for r in reunions:
        if not isinstance(r, dict):
            continue
        nr = r.get("numOfficiel")
        hippo = (r.get("hippodrome") or {}).get("libelleLong", "?")
        for c in (r.get("courses") or []):
            if not isinstance(c, dict):
                continue
            statut = (c.get("statut") or "").upper()
            if "FIN" not in statut and "ARRIVE" not in statut:
                continue

            num_course = c.get("numOrdre")
            key = f"{date_str}-R{nr}C{num_course}"
            if any(x.get("key") == key for x in COLLECTED_RESULTS):
                continue

            arrivee = await _get_arrivee_participants(date_str, nr, num_course)

            if arrivee:
                COLLECTED_RESULTS.append({
                    "key": key,
                    "date": date_str,
                    "reunion": nr,
                    "num_course": num_course,
                    "course": c.get("libelle", "Course"),
                    "hippodrome": hippo,
                    "discipline": c.get("discipline", "?"),
                    "distance": c.get("distance", 0),
                    "partants": c.get("nombreDeclaresPartants", 0),
                    "arrivee": arrivee[:5],
                })
                nouvelles += 1

    return {"ok": True, "nouvelles": nouvelles, "total": len(COLLECTED_RESULTS)}


@app.get("/api/results")
async def list_results(limit: int = 50):
    return {"count": len(COLLECTED_RESULTS), "results": COLLECTED_RESULTS[-limit:]}


# ============ PROXY PMU ============

@app.get("/api/pmu/proxy/{path:path}")
async def proxy_pmu(path: str):
    url = f"{PMU_BASE}/{path}"
    data = await _pmu_get(url)
    if data is None:
        return {"error": "PMU indisponible", "path": path}
    return data