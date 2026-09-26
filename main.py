import os
import re
import statistics
import httpx
from pathlib import Path
from datetime import datetime, timedelta
from fastapi import FastAPI, Request, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

try:
    from multitask_agent import MultiTaskAgent
    from prediction_engine import PredictionEngine
    from prediction_store import PredictionStore
    from racing_data_agent import RacingDataAgent
    data_agent = RacingDataAgent()
    prediction_store = PredictionStore()
    prediction_engine = PredictionEngine(prediction_store)
    IMPORTS_OK = True
except Exception:
    IMPORTS_OK = False

try:
    import db
    DB_OK = db.DB_OK
except Exception:
    DB_OK = False

app = FastAPI(title="Hippique AI", version="5.3.0")
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

MISE = 10
PMU_BASE = "https://online.turfinfo.api.pmu.fr/rest/client/61"
HEADERS = {"User-Agent": "Mozilla/5.0"}

MIN_PARTANTS_ZSCORE = 5

COLLECTED = []
STATS = {
    "evaluated": 0,
    "agents": {
        "FormAgent": {"h1": 0, "h5": 0, "tot": 0},
        "DriverAgent": {"h1": 0, "h5": 0, "tot": 0},
        "MarketAgent": {"h1": 0, "h5": 0, "tot": 0},
        "ClassAgent": {"h1": 0, "h5": 0, "tot": 0},
        "RiskAgent": {"h1": 0, "h5": 0, "tot": 0},
        "TrackAgent": {"h1": 0, "h5": 0, "tot": 0},
        "ForecastAgent": {"h1": 0, "h5": 0, "tot": 0},
    }
}

if DB_OK:
    try:
        db.init()
        COLLECTED = db.load_results()
        agents_db = db.load_agents()
        for name, s in agents_db.items():
            if name in STATS["agents"]:
                STATS["agents"][name]["h1"] = s.get("hits_top1", 0)
                STATS["agents"][name]["h5"] = s.get("hits_top5", 0)
                STATS["agents"][name]["tot"] = s.get("total", 0)
        ev = db.load_meta("evaluated")
        if ev:
            STATS["evaluated"] = int(ev)
    except Exception as e:
        print("DB load error: " + str(e))


class ChatIn(BaseModel):
    message: str


class PredIn(BaseModel):
    race_key: str = "race"
    race_name: str = "Course"
    race_date: str = None
    text: str = ""


@app.get("/", response_class=HTMLResponse)
async def root(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/pronostics", response_class=HTMLResponse)
async def pronostics_page(request: Request):
    return templates.TemplateResponse(request, "pronostics.html")


@app.get("/learning", response_class=HTMLResponse)
async def learning_page(request: Request):
    return templates.TemplateResponse(request, "learning.html")


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "version": app.version,
        "database": DB_OK,
        "results_collected": len(COLLECTED),
        "evaluated": STATS["evaluated"],
    }


@app.get("/api/drivers/top")
async def drivers_top():
    if not DB_OK:
        return {"drivers": []}
    return {"drivers": db.get_all_driver_stats()}


async def rebuild_drivers_task(offset: int = 0):
    if not DB_OK:
        return
    ds = date_str(offset)
    prog = await pmu_get(PMU_BASE + "/programme/" + ds)
    if not prog:
        return
    reunions = (prog.get("programme") or {}).get("reunions") or []
    for r in reunions:
        if not isinstance(r, dict):
            continue
        nr = r.get("numOfficiel")
        hippo_obj = r.get("hippodrome") or {}
        hippo = hippo_obj.get("libelleLong", "?")
        if not hippodrome_ok(hippo_obj, hippo):
            continue
        for c in (r.get("courses") or []):
            if not isinstance(c, dict):
                continue
            st = (c.get("statut") or "").upper()
            if "FIN" not in st and "ARRIVE" not in st:
                continue
            nc = c.get("numOrdre")
            parts = await get_participants(ds, nr, nc)
            if not parts:
                continue
            arr = await get_arrivee(parts)
            if not arr:
                continue
            v1 = arr[0]
            v5 = set(arr[:5])
            for p in parts:
                if not isinstance(p, dict):
                    continue
                num = p.get("numPmu")
                driver = p.get("driver") or p.get("jockey") or ""
                if not num or not driver:
                    continue
                try:
                    num_int = int(num)
                except Exception:
                    continue
                if num_int == v1:
                    db.update_driver(driver, 1)
                elif num_int in v5:
                    db.update_driver(driver, 2)
                else:
                    db.update_driver(driver, None)
            db.update_hippodrome(hippo)


@app.get("/api/admin/rebuild-drivers")
@app.post("/api/admin/rebuild-drivers")
async def admin_rebuild_drivers(background_tasks: BackgroundTasks, offset: int = 0):
    background_tasks.add_task(rebuild_drivers_task, offset=offset)
    return {"ok": True, "queued": True, "message": "Rebuild en cours (2-5 min)"}


@app.post("/api/chat")
async def chat(payload: ChatIn):
    return {"reply": "Chat cote navigateur."}


@app.post("/api/predictions")
async def create_prediction(payload: PredIn):
    if not IMPORTS_OK:
        return {"error": "Moteur indisponible"}
    runners = prediction_engine.parse_text(payload.text)
    result = prediction_engine.rank(runners, payload.race_key, payload.race_name, payload.race_date)
    return result


def compute_roi():
    roi = {}
    for name in STATS["agents"].keys():
        roi[name] = {"mise": 0.0, "gain": 0.0, "pari": 0, "gagne": 0}
    for course in COLLECTED:
        ev = course.get("evaluations") or {}
        for agent_name, data in ev.items():
            if agent_name not in roi:
                continue
            cote = data.get("cote_top1")
            if not cote:
                continue
            roi[agent_name]["mise"] += MISE
            roi[agent_name]["pari"] += 1
            if data.get("top1") == 1:
                roi[agent_name]["gain"] += MISE * float(cote)
                roi[agent_name]["gagne"] += 1
    for name in roi:
        mise = roi[name]["mise"]
        gain = roi[name]["gain"]
        roi[name]["pnl"] = round(gain - mise, 2)
        roi[name]["roi_pct"] = round((gain - mise) / mise * 100, 2) if mise > 0 else 0
        roi[name]["mise"] = round(mise, 2)
        roi[name]["gain"] = round(gain, 2)
    return roi


@app.get("/api/learning/metrics")
async def learning_metrics():
    evaluated = STATS["evaluated"]
    roi = compute_roi()
    agents_scores = {}
    for name, s in STATS["agents"].items():
        if s["tot"] > 0:
            t1r = s["h1"] / s["tot"]
            t5r = s["h5"] / (s["tot"] * 5)
            score = round(t1r * 60 + t5r * 40, 1)
            score = min(100.0, max(0.0, score))
        else:
            score = 50.0
        r = roi.get(name, {})
        agents_scores[name] = {
            "score": score,
            "total": s["tot"],
            "top1": s["h1"],
            "top5": s["h5"],
            "roi_pct": r.get("roi_pct", 0),
            "roi_pnl": r.get("pnl", 0),
            "roi_mise": r.get("mise", 0),
            "roi_gain": r.get("gain", 0),
            "roi_pari": r.get("pari", 0),
            "roi_gagne": r.get("gagne", 0),
        }
    if evaluated > 0:
        nb = len(STATS["agents"])
        t1 = sum(s["h1"] for s in STATS["agents"].values())
        t5 = sum(s["h5"] for s in STATS["agents"].values())
        avg1 = t1 / (evaluated * nb)
        avg5 = t5 / (evaluated * nb * 5)
    else:
        avg1 = 0
        avg5 = 0
    return {
        "evaluated_predictions": evaluated,
        "top1_hit_rate": round(avg1, 3),
        "top5_hit_rate": round(avg5, 3),
        "agents": agents_scores,
        "database": DB_OK,
    }


@app.get("/api/learning/reset")
async def learning_reset():
    COLLECTED.clear()
    STATS["evaluated"] = 0
    for name in STATS["agents"]:
        STATS["agents"][name] = {"h1": 0, "h5": 0, "tot": 0}
    if DB_OK:
        db.reset_all()
    return {"ok": True}


@app.get("/api/admin/purge")
async def admin_purge(confirm: str = ""):
    if confirm != "yes":
        return {"error": "Ajoute ?confirm=yes"}
    COLLECTED.clear()
    STATS["evaluated"] = 0
    for name in STATS["agents"]:
        STATS["agents"][name] = {"h1": 0, "h5": 0, "tot": 0}
    if DB_OK:
        db.reset_all()
    return {"ok": True, "message": "Base purge"}


# ============================================================
# SCORES DE BASE (identiques pour toutes disciplines)
# ============================================================

def parse_musique(s):
    return [m.strip() for m in re.split(r"\s+", s or "") if m.strip()]


def score_musique(musique):
    t = 0.0
    for i, m in enumerate(musique[:5]):
        n = re.sub(r"[^0-9]", "", str(m))
        if n:
            p = int(n)
            if 1 <= p <= 9:
                t += max(0, 11 - p) * (1.0 / (i + 1))
    return min(t / 8.0, 10)


def score_driver(driver):
    if DB_OK and driver:
        dyn = db.get_driver_score(driver)
        if dyn is not None:
            return dyn
    return 0.5


def score_cote(cote):
    try:
        c = float(cote)
        if c > 0:
            return min(10.0 / c, 10)
        return 0.5
    except Exception:
        return 0.5


def score_gains(gains):
    try:
        return min(float(gains) / 300000.0, 1.0) * 3
    except Exception:
        return 0.0


def score_risk(musique):
    da = sum(1 for m in musique[:5] if str(m).lower().startswith("d"))
    return max(0, 2 - da * 0.5)


# ============================================================
# SCORES SPÉCIFIQUES PAR DISCIPLINE
# ============================================================

def detect_discipline(discipline_str):
    """Détecte la discipline d'une course à partir du libellé PMU."""
    d = (discipline_str or "").upper()
    if "TROT" in d:
        return "TROT"
    if any(x in d for x in ("HAIES", "STEEPLE", "CROSS", "OBSTACLE")):
        return "OBSTACLE"
    if "PLAT" in d:
        return "PLAT"
    return "AUTRE"


def score_deferrage(p):
    """Bonus si le cheval est déferré (trot uniquement)."""
    d = (p.get("deferrage") or "").upper()
    if "QUATRE" in d or "D4" in d:
        return 2.0
    if "ANTERIEURS" in d or "POSTERIEURS" in d:
        return 1.0
    return 0.0


def score_poids_brut(p):
    """Retourne le poids monté (utile pour z-score)."""
    for key in ("poidsConditionMonte", "poids", "handicapPoids"):
        v = p.get(key)
        if v:
            try:
                return float(v)
            except Exception:
                pass
    return None


def score_corde(p):
    """Corde : plus le numéro est bas, meilleur c'est (au plat)."""
    c = p.get("corde")
    if c is None:
        return 0.0
    try:
        c = int(c)
        return max(0.0, 10.0 - c)
    except Exception:
        return 0.0


def score_experience(p):
    """Nombre de courses courues (utile en obstacle)."""
    n = p.get("nombreCourses")
    if n is None:
        return 0.0
    try:
        return min(float(n) / 20.0, 1.0) * 3.0
    except Exception:
        return 0.0


def score_handicap_distance(p):
    """Recul au trot (handicap de distance) — pénalité."""
    h = p.get("handicapDistance")
    if not h:
        return 0.0
    try:
        return -min(float(h) / 25.0, 2.0)
    except Exception:
        return 0.0


# ============================================================
# Z-SCORE
# ============================================================

def zscore(values, v):
    if len(values) < 2:
        return 0.0
    m = statistics.mean(values)
    try:
        s = statistics.pstdev(values)
    except Exception:
        return 0.0
    if s == 0:
        return 0.0
    return (v - m) / s


# ============================================================
# PRÉDIRE — adapté par discipline
# ============================================================

def predire(participants, discipline="AUTRE"):
    # ---- ÉTAPE 1 : valeurs brutes ----
    raw = []
    for p in participants:
        if not isinstance(p, dict):
            continue
        num = p.get("numPmu")
        if not num:
            continue
        musique = parse_musique(p.get("musique", ""))
        driver = p.get("driver") or p.get("jockey") or ""
        cote = (p.get("dernierRapportDirect") or {}).get("rapport")
        gains = (p.get("gainsParticipant") or {}).get("gainsCarriere", 0)
        raw.append({
            "num": num,
            "sf": score_musique(musique),
            "sd": score_driver(driver),
            "sc": score_cote(cote),
            "sg": score_gains(gains),
            "sr": score_risk(musique),
            "sdef": score_deferrage(p),
            "spoids": score_poids_brut(p),
            "scorde": score_corde(p),
            "sexp": score_experience(p),
            "shand": score_handicap_distance(p),
        })

    use_z = len(raw) >= MIN_PARTANTS_ZSCORE

    # ---- ÉTAPE 2 : z-scores par feature ----
    scored = []
    for r in raw:
        if use_z:
            # Features de base
            zf = zscore([x["sf"] for x in raw], r["sf"])
            zd = zscore([x["sd"] for x in raw], r["sd"])
            zc = zscore([x["sc"] for x in raw], r["sc"])
            zg = zscore([x["sg"] for x in raw], r["sg"])
            zr = zscore([x["sr"] for x in raw], r["sr"])

            # Features discipline-spécifiques (calculées seulement si applicables)
            zdef = 0.0
            zpoids = 0.0
            zcorde = 0.0
            zexp = 0.0
            zhand = 0.0

            if discipline == "TROT":
                zdef = zscore([x["sdef"] for x in raw], r["sdef"])
                zhand = zscore([x["shand"] for x in raw], r["shand"])

            if discipline in ("PLAT", "OBSTACLE"):
                poids_vals = [x["spoids"] for x in raw if x["spoids"] is not None]
                if len(poids_vals) >= 2 and r["spoids"] is not None:
                    # Pour le poids, MOINS = MIEUX → on inverse le signe
                    zpoids = -zscore(poids_vals, r["spoids"])

            if discipline == "PLAT":
                zcorde = zscore([x["scorde"] for x in raw], r["scorde"])

            if discipline == "OBSTACLE":
                zexp = zscore([x["sexp"] for x in raw], r["sexp"])

            # ---- Combinaison finale selon discipline ----
            if discipline == "TROT":
                forecast = (zf * 0.15 + zd * 0.20 + zc * 0.30
                            + zg * 0.15 + zr * 0.15 + zdef * 0.05 + zhand * 0.05)
            elif discipline == "PLAT":
                forecast = (zf * 0.20 + zd * 0.15 + zc * 0.35
                            + zg * 0.15 + zpoids * 0.10 + zcorde * 0.05)
            elif discipline == "OBSTACLE":
                forecast = (zf * 0.20 + zd * 0.15 + zc * 0.30
                            + zg * 0.15 + zpoids * 0.10 + zexp * 0.10)
            else:
                # Fallback : config v5.2
                forecast = (zf * 0.20 + zd * 0.15 + zc * 0.35
                            + zg * 0.20 + zr * 0.10)
        else:
            # Moins de 5 partants : on garde les scores absolus
            forecast = (r["sf"] * 0.15 + r["sd"] * 0.15 + r["sc"] * 0.45
                        + r["sg"] * 0.15 + r["sr"] * 0.10)

        scored.append({
            "num": r["num"],
            "form": r["sf"],
            "driver": r["sd"],
            "market": r["sc"],
            "class": r["sg"],
            "risk": r["sr"],
            "deferrage": r["sdef"],
            "forecast": forecast,
        })

    # ---- ÉTAPE 3 : prédictions par agent ----
    preds = {k: [] for k in STATS["agents"].keys()}
    for agent in preds:
        key = agent.replace("Agent", "").lower()
        if key == "forecast":
            key = "forecast"
        s = sorted(scored, key=lambda x: x.get(key, 0), reverse=True)
        preds[agent] = [x["num"] for x in s[:5]]
    return preds


def evaluer(participants, arrivee, hippodrome, discipline="AUTRE"):
    if not participants or not arrivee:
        return {}
    preds = predire(participants, discipline=discipline)
    v1 = arrivee[0]
    v5 = set(arrivee[:5])
    if DB_OK:
        for p in participants:
            if not isinstance(p, dict):
                continue
            num = p.get("numPmu")
            driver = p.get("driver") or p.get("jockey") or ""
            if not num or not driver:
                continue
            try:
                num_int = int(num)
            except Exception:
                continue
            if num_int in v5:
                if num_int == v1:
                    db.update_driver(driver, 1)
                else:
                    db.update_driver(driver, 2)
            else:
                db.update_driver(driver, None)
        db.update_hippodrome(hippodrome)
    cotes = {}
    for p in participants:
        if not isinstance(p, dict):
            continue
        num = p.get("numPmu")
        cote = (p.get("dernierRapportDirect") or {}).get("rapport")
        if num and cote:
            try:
                cotes[int(num)] = float(cote)
            except Exception:
                pass
    res = {}
    for name, pred in preds.items():
        h1 = 1 if pred and pred[0] == v1 else 0
        h5 = len(set(pred) & v5) if pred else 0
        cote_top1 = cotes.get(pred[0]) if pred else None
        s = STATS["agents"][name]
        s["tot"] += 1
        s["h1"] += h1
        s["h5"] += h5
        if DB_OK:
            db.save_agent(name, s["h1"], s["h5"], s["tot"])
        res[name] = {"top1": h1, "top5": h5, "prediction": pred, "cote_top1": cote_top1}
    STATS["evaluated"] += 1
    if DB_OK:
        db.save_meta("evaluated", str(STATS["evaluated"]))
    return res


BLACKLIST = [
    "CHILI", "CHILE", "VALPARAISO",
    "SAN ISIDRO", "PALERMO", "LA PLATA", "ARGENTINE",
    "SUEDE", "SWEDEN", "SOLVALLA",
    "URUGUAY", "MONTEVIDEO",
    "BRESIL", "BRAZIL", "SAO PAULO",
    "USA", "UNITED STATES",
    "AUSTRALIA", "AUSTRALIE",
    "JAPON", "JAPAN", "TOKYO",
    "HONG KONG",
    "SINGAPOUR", "SINGAPORE",
    "INDE", "INDIA",
    "MAURICE",
    "AFRIQUE DU SUD",
    "PEROU", "PERU",
    "MEXIQUE", "MEXICO",
    "CANADA", "TORONTO",
    "NORVEGE", "OSLO",
    "DANEMARK",
    "FINLANDE",
    "RUSSIE", "MOSCOU",
    "TURQUIE", "ISTANBUL",
    "EMIRATS", "DUBAI",
    "QATAR", "ARABIE",
    "COREE", "SEOUL",
    "CHINE", "SHANGHAI",
    "THAILANDE",
    "MALAISIE",
    "INDONESIE",
    "NOUVELLE-ZELANDE", "NEW ZEALAND",
    "VENEZUELA",
    "COLOMBIE",
    "EQUATEUR",
    "BOLIVIE",
    "PARAGUAY",
]


def hippodrome_ok(hippo_obj, nom):
    if not nom:
        return False
    nom_up = nom.upper()
    for mot in BLACKLIST:
        if mot.upper() in nom_up:
            return False
    if isinstance(hippo_obj, dict):
        pays = hippo_obj.get("pays") or {}
        if isinstance(pays, dict):
            nom_pays = (pays.get("libelle") or "").upper()
            for mot in BLACKLIST:
                if mot.upper() in nom_pays:
                    return False
    return True


def date_str(offset=0):
    d = datetime.now() + timedelta(days=offset)
    return d.strftime("%d%m%Y")


async def pmu_get(url):
    try:
        async with httpx.AsyncClient(timeout=20.0, headers=HEADERS) as c:
            r = await c.get(url)
            if r.status_code == 200:
                return r.json()
            return None
    except Exception:
        return None


async def get_participants(ds, r, c):
    url = PMU_BASE + "/programme/" + ds + "/R" + str(r) + "/C" + str(c) + "/participants"
    data = await pmu_get(url)
    if data:
        return data.get("participants", [])
    return []


async def get_arrivee(parts):
    cls = []
    for p in parts:
        if not isinstance(p, dict):
            continue
        place = p.get("place") or p.get("ordreArrivee") or p.get("position")
        num = p.get("numPmu")
        if place and num:
            try:
                cls.append((int(place), int(num)))
            except Exception:
                continue
    cls.sort(key=lambda x: x[0])
    return [n for _, n in cls[:5]]


@app.get("/api/agent/collect")
@app.post("/api/agent/collect")
async def agent_collect(offset: int = 0):
    ds = date_str(offset)
    prog = await pmu_get(PMU_BASE + "/programme/" + ds)
    if not prog:
        return {"ok": False, "nouvelles": 0, "evaluees": 0, "total": len(COLLECTED)}
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
        if not hippodrome_ok(hippo_obj, hippo):
            ignorees += 1
            continue
        for c in (r.get("courses") or []):
            if not isinstance(c, dict):
                continue
            st = (c.get("statut") or "").upper()
            if "FIN" not in st and "ARRIVE" not in st:
                continue
            nc = c.get("numOrdre")
            key = ds + "-R" + str(nr) + "C" + str(nc)
            if any(x.get("key") == key for x in COLLECTED):
                continue
            parts = await get_participants(ds, nr, nc)
            if not parts:
                continue
            arr = await get_arrivee(parts)
            if not arr:
                continue
            # DÉTECTION DISCIPLINE
            discipline_raw = c.get("discipline") or ""
            discipline = detect_discipline(discipline_raw)
            ev = evaluer(parts, arr, hippo, discipline=discipline)
            if ev:
                eval_ += 1
            item = {"key": key, "date": ds, "reunion": nr, "num_course": nc,
                    "course": c.get("libelle", "Course"), "hippodrome": hippo,
                    "discipline": discipline_raw,
                    "discipline_norm": discipline,
                    "distance": c.get("distance", 0),
                    "partants": c.get("nombreDeclaresPartants", 0),
                    "arrivee": arr[:5], "evaluations": ev}
            COLLECTED.append(item)
            if DB_OK:
                db.save_result(item)
            nouv += 1
    return {"ok": True, "nouvelles": nouv, "evaluees": eval_, "ignorees": ignorees,
            "total": len(COLLECTED), "total_evaluees": STATS["evaluated"]}


@app.get("/api/results")
async def list_results(limit: int = 50):
    return {"count": len(COLLECTED), "results": COLLECTED[-limit:]}


@app.get("/api/pmu/proxy/{path:path}")
async def proxy_pmu(path: str):
    data = await pmu_get(PMU_BASE + "/" + path)
    if data:
        return data
    return {"error": "PMU indisponible"}


# ============================================================
# ROUTE CRON
# ============================================================
@app.get("/api/cron/run")
async def cron_run(background_tasks: BackgroundTasks):
    background_tasks.add_task(agent_collect, offset=0)
    return {"ok": True, "queued": True}