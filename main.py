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
import re
from datetime import datetime, timedelta

app = FastAPI(title="Hippique AI", version="2.3.0")
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

COLLECTED_RESULTS = []
LEARNING_STATS = {
    "evaluated": 0,
    "agents": {
        "FormAgent":     {"hits_top1": 0, "hits_top5": 0, "total": 0, "score": 50},
        "DriverAgent":   {"hits_top1": 0, "hits_top5": 0, "total": 0, "score": 50},
        "MarketAgent":   {"hits_top1": 0, "hits_top5": 0, "total": 0, "score": 50},
        "ClassAgent":    {"hits_top1": 0, "hits_top5": 0, "total": 0, "score": 50},
        "RiskAgent":     {"hits_top1": 0, "hits_top5": 0, "total": 0, "score": 50},
        "TrackAgent":    {"hits_top1": 0, "hits_top5": 0, "total": 0, "score": 50},
        "ForecastAgent": {"hits_top1": 0, "hits_top5": 0, "total": 0, "score": 50},
    }
}

HORSES = {
    "Asteria du Clos": {"age": 5, "form": 82, "surface": "gazon", "distance": "2000m"},
    "Vortex d'Or": {"age": 4, "form": 76, "surface": "piste lourde", "distance": "1600m"},
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
    h = HORSES.get(name, {"form": 0, "surface": "inconnue", "distance": "inconnue"})
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
        "evaluated": LEARNING_STATS["evaluated"],
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
    base = prediction_store.metrics()
    evaluated = LEARNING_STATS["evaluated"]
    agents_scores = {}

    for name, s in LEARNING_STATS["agents"].items():
        if s["total"] > 0:
            top1_rate = s["hits_top1"] / s["total"]
            top5_rate = s["hits_top5"] / (s["total"] * 5)
            # Score entre 0 et 100
            score = round((top1_rate * 60 + top5_rate * 40) * 100, 1)
            # Sécurité : on plafonne à 100
            score = min(100.0, score)
        else:
            score = 50.0
        agents_scores[name] = {
            "score": score,
            "total": s["total"],
            "top1": s["hits_top1"],
            "top5": s["hits_top5"],
            "top1_rate": round(s["hits_top1"] / s["total"], 3) if s["total"] > 0 else None,
            "top5_rate": round(s["hits_top5"] / (s["total"] * 5), 3) if s["total"] > 0 else None,
        }

    if evaluated > 0:
        nb = len(LEARNING_STATS["agents"])
        total_top1 = sum(s["hits_top1"] for s in LEARNING_STATS["agents"].values())
        total_top5 = sum(s["hits_top5"] for s in LEARNING_STATS["agents"].values())
        avg_top1 = total_top1 / (evaluated * nb)
        avg_top5 = total_top5 / (evaluated * nb * 5)
    else:
        avg_top1 = 0
        avg_top5 = 0

    return {
        **base,
        "evaluated_predictions": evaluated,
        "top1_hit_rate": round(avg_top1, 3),
        "top5_hit_rate": round(avg_top5, 3),
        "agents": agents_scores,
    }


@app.post("/api/learning/reset")
async def learning_reset():
    COLLECTED_RESULTS.clear()
    LEARNING_STATS["evaluated"] = 0
    for name in LEARNING_STATS["agents"]:
        LEARNING_STATS["agents"][name] = {"hits_top1": 0, "hits_top5": 0, "total": 0, "score": 50}
    return {"ok": True}


@app.post("/api/agents/analyse")
async def agents_analyse(payload: dict):
    if not AGENTS_MODULE_OK:
        return {"error": "Module agents non disponible", "resultats": []}
    runners = payload.get("runners", [])
    try:
        return {"resultats": analyse_course(runners)}
    except Exception as e:
        return {"error": str(e), "resultats": []}


# ============ MOTEUR ============

def _parse_musique(musique_str: str) -> list:
    if not musique_str:
        return []
    return [m.strip() for m in re.split(r"\s+", musique_str) if m.strip()]


def _score_musique(musique: list) -> float:
    total = 0.0
    for i, m in enumerate(musique[:5]):
        num = re.sub(r"[^0-9]", "", str(m))
        if num:
            p = int(num)
            if 1 <= p <= 9:
                total += max(0, 11 - p) * (1 / (i + 1))
    return min(total / 8, 10)


def _score_driver(driver: str) -> float:
    tops = {
        "E. Raffin": 2.0, "M. Abrivard": 1.8, "F. Nivard": 2.0,
        "D. Thomain": 1.6, "B. Rochard": 1.5, "A. Barrier": 1.5,
        "P.ph. Ploquin": 1.4, "N. Bazire": 1.8, "J.m. Bazire": 1.8,
        "Y. Lebourgeois": 1.5, "A. Abrivard": 1.4, "T. Le Beller": 1.2,
        "C. Demuro": 2.0, "M. Guyon": 1.9, "C. Soumillon": 2.0,
        "S. Pasquier": 1.9, "Pc. Boudot": 1.8, "M. Barzalona": 1.7,
    }
    for k, v in tops.items():
        if driver and k.lower() in driver.lower():
            return v
    return 0.5


def _score_cote(cote) -> float:
    try:
        c = float(cote)
        if c > 0:
            return min(10 / c, 10)
    except (ValueError, TypeError):
        pass
    return 0.5


def _score_gains(gains) -> float:
    try:
        g = float(gains)
        return min(g / 300000, 1.0) * 3
    except (ValueError, TypeError):
        return 0.0


def _score_risk(musique: list) -> float:
    da = sum(1 for m in musique[:5] if str(m).lower().startswith("d"))
    return max(0, 2 - da * 0.5)


def _predire_avec_agents(participants: list) -> dict:
    predictions = {k: [] for k in LEARNING_STATS["agents"].keys()}
    scored = []

    for p in participants:
        if not isinstance(p, dict):
            continue
        num = p.get("numPmu")
        if not num:
            continue
        musique = _parse_musique(p.get("musique", ""))
        driver = p.get("driver") or p.get("jockey") or ""
        cote = (p.get("dernierRapportDirect") or {}).get("rapport")
        gains = (p.get("gainsParticipant") or {}).get("gainsCarriere", 0)

        sf = _score_musique(musique)
        sd = _score_driver(driver)
        sc = _score_cote(cote)
        sg = _score_gains(gains)
        sr = _score_risk(musique)
        forecast = sf * 0.35 + sd * 0.25 + sc * 0.20 + sg * 0.15 + sr * 0.05

        scored.append({
            "num": num, "form": sf, "driver": sd, "market": sc,
            "class": sg, "risk": sr, "forecast": forecast,
        })

    for agent in predictions:
        key = agent.replace("Agent", "").lower()
        if key == "forecast":
            key = "forecast"
        sorted_items = sorted(scored, key=lambda x: x.get(key, 0), reverse=True)
        predictions[agent] = [x["num"] for x in sorted_items[:5]]

    return predictions


def _evaluer_arrivee(participants: list, arrivee_reelle: list) -> dict:
    if not participants or not arrivee_reelle:
        return {}

    predictions = _predire_avec_agents(participants)
    vrai_top1 = arrivee_reelle[0] if arrivee_reelle else None
    vrai_top5 = set(arrivee_reelle[:5])

    resultats = {}
    for agent_name, pred in predictions.items():
        hit_top1 = 1 if pred and pred[0] == vrai_top1 else 0
        hit_top5 = len(set(pred) & vrai_top5) if pred else 0

        s = LEARNING_STATS["agents"][agent_name]
        s["total"] += 1
        s["hits_top1"] += hit_top1
        s["hits_top5"] += hit_top5

        resultats[agent_name] = {
            "top1": hit_top1,
            "top5": hit_top5,
            "prediction": pred,
        }

    LEARNING_STATS["evaluated"] += 1
    return resultats


# ============ COLLECTE ============

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


async def _get_participants(date_str: str, reunion: int, course: int) -> list:
    url = f"{PMU_BASE}/programme/{date_str}/R{reunion}/C{course}/participants"
    data = await _pmu_get(url)
    if not data or not isinstance(data, dict):
        return []
    return data.get("participants") or []


async def _get_arrivee_participants(participants: list) -> list:
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
        return {"ok": False, "nouvelles": 0, "evaluees": 0, "total": len(COLLECTED_RESULTS)}

    reunions = []
    if isinstance(programme, dict):
        reunions = (programme.get("programme") or {}).get("reunions") or []

    nouvelles = 0
    evaluees = 0

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

            participants = await _get_participants(date_str, nr, num_course)
            if not participants:
                continue

            arrivee = await _get_arrivee_participants(participants)
            if not arrivee:
                continue

            eval_result = _evaluer_arrivee(participants, arrivee)
            if eval_result:
                evaluees += 1

            COLLECTED_RESULTS.append({
                "key": key, "date": date_str, "reunion": nr, "num_course": num_course,
                "course": c.get("libelle", "Course"), "hippodrome": hippo,
                "discipline": c.get("discipline", "?"), "distance": c.get("distance", 0),
                "partants": c.get("nombreDeclaresPartants", 0),
                "arrivee": arrivee[:5], "evaluations": eval_result,
            })
            nouvelles += 1

    return {
        "ok": True, "nouvelles": nouvelles, "evaluees": evaluees,
        "total": len(COLLECTED_RESULTS), "total_evaluees": LEARNING_STATS["evaluated"],
    }


@app.get("/api/results")
async def list_results(limit: int = 50):
    return {"count": len(COLLECTED_RESULTS), "results": COLLECTED_RESULTS[-limit:]}


@app.get("/api/pmu/proxy/{path:path}")
async def proxy_pmu(path: str):
    url = f"{PMU_BASE}/{path}"
    data = await _pmu_get(url)
    if data is None:
        return {"error": "PMU indisponible", "path": path}
    return data