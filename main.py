from __future__ import annotations
from pathlib import Path
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

try:
    import db
    DB_OK = db.DB_OK
except ImportError:
    DB_OK = False

import httpx
import re
from datetime import datetime, timedelta

app = FastAPI(title="Hippique AI", version="3.3.0")
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

if DB_OK:
    try:
        db.init()
        COLLECTED_RESULTS = db.load_results()
        agents_db = db.load_agents()
        for name, s in agents_db.items():
            if name in LEARNING_STATS["agents"]:
                LEARNING_STATS["agents"][name].update(s)
        ev = db.load_meta("evaluated")
        if ev:
            LEARNING_STATS["evaluated"] = int(ev)
    except Exception as e:
        print(f"DB load error: {e}")

data_agent = RacingDataAgent()
prediction_store = PredictionStore()
prediction_engine = PredictionEngine(prediction_store)


class ChatMessage(BaseModel):
    message: str = Field(min_length=1, max_length=2000)


class PredictionRequest(BaseModel):
    race_key: str = Field(min_length=1, max_length=150)
    race_name: str = Field(default="Course importée", max_length=200)
    race_date: str | None = None
    text: str = Field(min_length=20, max_length=100000)


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
        "version": app.version,
        "agents_module": AGENTS_MODULE_OK,
        "database": DB_OK,
        "results_collected": len(COLLECTED_RESULTS),
        "evaluated": LEARNING_STATS["evaluated"],
    }


@app.get("/api/agents")
async def agents():
    return {"agents": {}, "multitask": MultiTaskAgent.catalog()}


@app.get("/api/tracks")
async def tracks():
    return {"tracks": data_agent.tracks()}


@app.get("/api/races")
async def races():
    return {"races": data_agent.races()}


@app.post("/api/chat")
async def chat(payload: ChatMessage):
    return {"reply": "Chat côté navigateur."}


@app.post("/api/predictions")
async def create_prediction(payload: PredictionRequest):
    runners = prediction_engine.parse_text(payload.text)
    result = prediction_engine.rank(runners, payload.race_key, payload.race_name, payload.race_date)
    return result


@app.get("/api/predictions")
async def prediction_history(limit: int = 20):
    return {"predictions": prediction_store.history(limit)}


@app.get("/api/learning/metrics")
async def learning_metrics():
    evaluated = LEARNING_STATS["evaluated"]
    agents_scores = {}
    for name, s in LEARNING_STATS["agents"].items():
        if s["total"] > 0:
            t1r = s["hits_top1"] / s["total"]
            t5r = s["hits_top5"] / (s["total"] * 5)
            score = round(t1r * 60 + t5r * 40, 1)
            score = min(100.0, max(0.0, score))
        else:
            score = 50.0
        agents_scores[name] = {
            "score": score, "total": s["total"],
            "top1": s["hits_top1"], "top5": s["hits_top5"],
        }
    if evaluated > 0:
        nb = len(LEARNING_STATS["agents"])
        t1 = sum(s["hits_top1"] for s in LEARNING_STATS["agents"].values())
        t5 = sum(s["hits_top5"] for s in LEARNING_STATS["agents"].values())
        avg1 = t1 / (evaluated * nb)
        avg5 = t5 / (evaluated * nb * 5)
    else:
        avg1 = avg5 = 0
    return {
        "evaluated_predictions": evaluated,
        "top1_hit_rate": round(avg1, 3),
        "top5_hit_rate": round(avg5, 3),
        "agents": agents_scores,
        "database": DB_OK,
    }


@app.post("/api/learning/reset")
async def learning_reset():
    COLLECTED_RESULTS.clear()
    LEARNING_STATS["evaluated"] = 0
    for name in LEARNING_STATS["agents"]:
        LEARNING_STATS["agents"][name] = {"hits_top1": 0, "hits_top5": 0, "total": 0, "score": 50}
    if DB_OK:
        db.reset_all()
    return {"ok": True}


@app.post("/api/agents/analyse")
async def agents_analyse(payload: dict):
    if not AGENTS_MODULE_OK:
        return {"error": "Non dispo", "resultats": []}
    try:
        return {"resultats": analyse_course(payload.get("runners", []))}
    except Exception as e:
        return {"error": str(e), "resultats": []}


# ============ MOTEUR ============

def _parse_musique(s):
    return [m.strip() for m in re.split(r"\s+", s or "") if m.strip()]


def _score_musique(musique):
    t = 0.0
    for i, m in enumerate(musique[:5]):
        n = re.sub(r"[^0-9]", "", str(m))
        if n:
            p = int(n)
            if 1 <= p <= 9:
                t += max(0, 11 - p) * (1 / (i + 1))
    return min(t / 8, 10)


def _score_driver(driver):
    tops = {"E. Raffin": 2.0, "M. Abrivard": 1.8, "F. Nivard": 2.0, "D. Thomain": 1.6,
            "B. Rochard": 1.5, "A. Barrier": 1.5, "P.ph. Ploquin": 1.4, "N. Bazire": 1.8,
            "J.m. Bazire": 1.8, "Y. Lebourgeois": 1.5, "C. Demuro": 2.0, "M. Guyon": 1.9,
            "C. Soumillon": 2.0, "S. Pasquier": 1.9}
    for k, v in tops.items():
        if driver and k.lower() in driver.lower():
            return v
    return 0.5


def _score_cote(cote):
    try:
        c = float(cote)
        return min(10 / c, 10) if c > 0 else 0.5
    except (ValueError, TypeError):
        return 0.5


def _score_gains(gains):
    try:
        return min(float(gains) / 300000, 1.0) * 3
    except (ValueError, TypeError):
        return 0.0


def _score_risk(musique):
    da = sum(1 for m in musique[:5] if str(m).lower().startswith("d"))
    return max(0, 2 - da * 0.5)


def _predire(participants):
    preds = {k: [] for k in LEARNING_STATS["agents"].keys()}
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
        forecast = sf*0.35 + sd*0.25 + sc*0.20 + sg*0.15 + sr*0.05
        scored.append({"num": num, "form": sf, "driver": sd, "market": sc,
                       "class": sg, "risk": sr, "forecast": forecast})
    for agent in preds:
        key = agent.replace("Agent", "").lower()
        if key == "forecast":
            key = "forecast"
        s = sorted(scored, key=lambda x: x.get(key, 0), reverse=True)
        preds[agent] = [x["num"] for x in s[:5]]
    return preds


def _evaluer(participants, arrivee):
    if not participants or not arrivee:
        return {}
    preds = _predire(participants)
    v1 = arrivee[0] if arrivee else None
    v5 = set(arrivee[:5])
    res = {}
    for name, pred in preds.items():
        h1 = 1 if pred and pred[0] == v1 else 0
        h5 = len(set(pred) & v5) if pred else 0
        s = LEARNING_STATS["agents"][name]
        s["total"] += 1
        s["hits_top1"] += h1
        s["hits_top5"] += h5
        if DB_OK:
            db.save_agent(name, s["hits_top1"], s["hits_top5"], s["total"])
        res[name] = {"top1": h1, "top5": h5, "prediction": pred}
    LEARNING_STATS["evaluated"] += 1
    if DB_OK:
        db.save_meta("evaluated", str(LEARNING_STATS["evaluated"]))
    return res


# ============ COLLECTE ============

PMU_BASE = "https://online.turfinfo.api.pmu.fr/rest/client/61"
HEADERS = {"User-Agent": "Mozilla/5.0"}


def _date_str(offset=0):
    d = datetime.now() + timedelta(days=offset)
    return d.strftime("%d%m%Y")


async def _pmu_get(url):
    try:
        async with httpx.AsyncClient(timeout=20.0, headers=HEADERS) as c:
            r = await c.get(url)
            return r.json() if r.status_code == 200 else None
    except Exception:
        return None


async def _get_participants(ds, r, c):
    url = f"{PMU_BASE}/programme/{ds}/R{r}/C{c}/participants"
    data = await _pmu_get(url)
    return data.get("participants", []) if data else []


async def _get_arrivee(parts):
    cls = []
    for p in parts:
        if not isinstance(p, dict):
            continue
        place = p.get("place") or p.get("ordreArrivee") or p.get("position")
        num = p.get("numPmu")
        if place and num:
            try:
                cls.append((int(place), int(num)))
            except (ValueError, TypeError):
                continue
    cls.sort(key=lambda x: x[0])
    return [n for _, n in cls[:5]]


PAYS_OK = [
    "FRANCE",
    "UNITED KINGDOM",
    "IRELAND",
    "MOROCCO", "MAROC", "MARRAKECH", "CASABLANCA",
    "SPAIN", "ESPAGNE", "ESPANA", "ESPAÑA",
    "BELGIUM", "BELGIQUE", "BELGIQUE",
]


def _pays_ok(hippodrome_obj, nom_hippo):
    """Retourne True si le pays de l'hippodrome est dans la liste acceptée."""
    if isinstance(hippodrome_obj, dict):
        pays = hippodrome_obj.get("pays") or {}
        if isinstance(pays, dict):
            nom_pays = (pays.get("libelle") or "").upper()
            if nom_pays:
                return any(p in nom_pays for p in PAYS_OK)
        elif isinstance(pays, str):
            if any(p in pays.upper() for p in PAYS_OK):
                return True
    if nom_hippo:
        nom_up = nom_hippo.upper()
        for p in PAYS_OK:
            if p in nom_up:
                return True
    return False


@app.get("/api/agent/collect")
@app.post("/api/agent/collect")
async def agent_collect(offset: int = 0):
    ds = _date_str(offset)
    prog = await _pmu_get(f"{PMU_BASE}/programme/{ds}")
    if not prog:
        return {"ok": False, "nouvelles": 0, "evaluees": 0, "total": len(COLLECTED_RESULTS)}
    reunions = (prog.get("programme") or {}).get("reunions") or []
    nouv = 0
    eval_ = 0
    ignorees = 0
    for r in reunions:
        if not isinstance(r, dict):
            continue
        nr = r.get("numOfficiel")
        hippo_obj = r.get("hippodrome") or {}
        hippo = hippo_obj.get("libelleLong", "?")
        if not _pays_ok(hippo_obj, hippo):
            ignorees += 1
            continue
        for c in (r.get("courses") or []):
            if not isinstance(c, dict):
                continue
            st = (c.get("statut") or "").upper()
            if "FIN" not in st and "ARRIVE" not in st:
                continue
            nc = c.get("numOrdre")
            key = f"{ds}-R{nr}C{nc}"
            if any(x.get("key") == key for x in COLLECTED_RESULTS):
                continue
            parts = await _get_participants(ds, nr, nc)
            if not parts:
                continue
            arr = await _get_arrivee(parts)
            if not arr:
                continue
            ev = _evaluer(parts, arr)
            if ev:
                eval_ += 1
            item = {"key": key, "date": ds, "reunion": nr, "num_course": nc,
                    "course": c.get("libelle", "Course"), "hippodrome": hippo,
                    "discipline": c.get("discipline", "?"), "distance": c.get("distance", 0),
                    "partants": c.get("nombreDeclaresPartants", 0),
                    "arrivee": arr[:5], "evaluations": ev}
            COLLECTED_RESULTS.append(item)
            if DB_OK:
                db.save_result(item)
            nouv += 1
    return {"ok": True, "nouvelles": nouv, "evaluees": eval_, "ignorees": ignorees,
            "total": len(COLLECTED_RESULTS), "total_evaluees": LEARNING_STATS["evaluated"]}


@app.get("/api/results")
async def list_results(limit: int = 50):
    return {"count": len(COLLECTED_RESULTS), "results": COLLECTED_RESULTS[-limit:]}


@app.get("/api/pmu/proxy/{path:path}")
async def proxy_pmu(path: str):
    data = await _pmu_get(f"{PMU_BASE}/{path}")
    return data if data else {"error": "PMU indisponible"}