from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from multitask_agent import MultiTaskAgent

app = FastAPI(title="Hippique AI", version="0.2.0")
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
    "CourseAgent": "Analyse le rythme, la distance et le profil de course.",
    "HorseAgent": "Analyse la forme, les aptitudes et la régularité du cheval.",
    "JockeyAgent": "Évalue la stratégie et la compatibilité avec le jockey.",
    "TrainerAgent": "Évalue la préparation et la dynamique de l’écurie.",
    "TrackAgent": "Analyse la piste, le terrain et la météo fournie.",
    "CalendarAgent": "Organise les échéances et prochaines courses.",
    "ForecastAgent": "Consolide les signaux en score indicatif, sans garantie.",
}

class ChatMessage(BaseModel):
    message: str = Field(min_length=1, max_length=2000)

class MultiTaskRequest(BaseModel):
    task: str = Field(min_length=1, max_length=4000)
    horse: str | None = None
    sources: list[str] = []


def analysis(horse_name: str) -> dict[str, Any]:
    horse = HORSES.get(horse_name, {"form": 0, "surface": "inconnue", "distance": "inconnue", "speed": 0, "stamina": 0, "traction": 0, "last_runs": []})
    scores = {"CourseAgent": 86, "HorseAgent": horse["form"], "JockeyAgent": 81, "TrainerAgent": 83, "TrackAgent": 82, "CalendarAgent": 77, "ForecastAgent": horse["form"]}
    agents = [{"name": name, "specialty": description, "score": scores[name], "insight": f"{name} a analysé le profil de {horse_name}."} for name, description in AGENTS.items()]
    return {"horse": {"name": horse_name, **horse}, "summary": f"{horse_name} présente une forme de {horse['form']}/100 et préfère {horse['surface']} sur {horse['distance']}.", "recommendation": "Analyse indicative uniquement : vérifiez les données officielles avant toute décision.", "agents": agents}


def answer(message: str) -> dict[str, Any]:
    horse = next((name for name in HORSES if name.lower() in message.lower()), "Asteria du Clos")
    result = analysis(horse)
    if "piste" in message.lower() or "terrain" in message.lower():
        reply = "La piste et l’état du terrain peuvent modifier fortement l’analyse. Comparez toujours l’aptitude du cheval aux conditions officielles."
    elif "jockey" in message.lower():
        reply = "Le jockey doit adapter le rythme et préserver l’effort final ; les statistiques officielles du jour restent nécessaires."
    else:
        reply = result["summary"] + " " + result["recommendation"]
    return {"reply": reply, "horse": horse, "agents": result["agents"]}


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "Hippique AI", "version": app.version}

@app.get("/api/agents")
async def agents():
    return {"agents": AGENTS, "multitask": MultiTaskAgent.catalog()}

@app.get("/api/analysis")
async def get_analysis(horse: str = "Asteria du Clos"):
    return analysis(horse)

@app.post("/api/chat")
async def chat(payload: ChatMessage):
    return answer(payload.message)

@app.post("/api/multitask")
async def multitask(payload: MultiTaskRequest):
    agent = MultiTaskAgent(HORSES, AGENTS)
    return await agent.run(payload.task, horse=payload.horse, sources=payload.sources)

@app.get("/api/capabilities")
async def capabilities():
    return MultiTaskAgent(HORSES, AGENTS).health()
