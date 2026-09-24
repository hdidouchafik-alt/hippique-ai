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

app = FastAPI(title="Hippique AI", version="0.7.0")
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

HORSES = {
    "Asteria du Clos": {"age": 5, "form": 82, "surface": "gazon", "distance": "2000m", "speed": 88, "stamina": 84, "traction": 80, "last_runs": ["1er", "2e", "1er"]},
    "Vortex d'Or": {"age": 4, "form": 76, "surface": "piste lourde", "distance": "1600m", "speed": 84, "stamina": 79, "traction": 86, "last_runs": ["2e", "3e", "1er"]},
    "Mistral de Noir": {"age": 6, "form": 71, "surface": "gazon", "distance": "2400m", "speed": 78, "stamina": 90, "traction": 74, "last_runs": ["3e", "2e", "4e"]},
    "Luna de la Mer": {"age": 3, "form": 88, "surface": "gazon", "distance": "1800m", "speed": 91, "stamina": 82, "traction": 79, "last_runs": ["1er", "1er", "2e"]},
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
        "summary": f"{name} présente une forme de {h['form']}/100 et préfère {h['surface']} sur {h['distance']}.",
        "agents": [
            {
                "name": n,
                "specialty": d,
                "score": h["form"] if n in ("HorseAgent", "ForecastAgent") else 80,
                "insight": f"{n} a analysé {name}.",
            }
            for n, d in AGENTS.items()
        ],
    }


# ============ PAGES HTML ============

@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/pronostics", response_class=HTMLResponse)
async def pronostics_page(request: Request):
    return templates.TemplateResponse("pronostics.html", {"request": request})


# ============ API ============

@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "service": "Hippique AI",
        "version": app.version,
        "learning": prediction_store.metrics(),
    }


@app.get("/api/agents")
async def agents():
    return {"agents": AGENTS, "multitask": MultiTaskAgent.catalog()}


@app.get("/api/capabilities")
async def capabilities():
    return MultiTaskAgent(HORSES, AGENTS).health()


@app.get("/api/tracks")
async def tracks():
    return {"tracks": data_agent.tracks()}


@app.get("/api/races")
async def races():
    return {"races": data_agent.races()}


@app.get("/api/analysis")
async def get_analysis(horse: str = "Asteria du Clos"):
    return analysis(horse)


@app.post("/api/multitask")
async def multitask(payload: MultiTaskRequest):
    return await MultiTaskAgent(HORSES, AGENTS).run(payload.task, payload.horse, payload.sources)


@app.post("/api/chat")
async def chat(payload: ChatMessage):
    return {"reply": analysis(next((n for n in HORSES if n.lower() in payload.message.lower()), "Asteria du Clos"))["summary"]}


@app.post("/api/predictions")
async def create_prediction(payload: PredictionRequest):
    runners = prediction_engine.parse_text(payload.text)
    result = prediction_engine.rank(runners, payload.race_key, payload.race_name, payload.race_date)
    result["runners_count"] = len(runners)
    return result


@app.post("/api/predictions/{prediction_id}/outcome")
async def record_outcome(prediction_id: int, payload: OutcomeRequest):
    try:
        return prediction_store.save_outcome(prediction_id, payload.arrival)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/predictions")
async def prediction_history(limit: int = 20):
    return {"predictions": prediction_store.history(limit)}


@app.get("/api/learning/metrics")
async def learning_metrics():
    return prediction_store.metrics()