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

app = FastAPI(title="Hippique AI", version="5.6.0")
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
# SCORES DE BASE
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
# v5.6 : FEATURES SPÉCIFIQUES PAR DISCIPLINE (Phase 1+2+3)
# ============================================================

def detect_discipline(discipline_str):
    d = (discipline_str or "").upper()
    if "TROT" in d:
        return "TROT"
    if any(x in d for x in ("HAIES", "STEEPLE", "CROSS", "OBSTACLE")):
        return "OBSTACLE"
    if "PLAT" in d:
        return "PLAT"
    return "AUTRE"


def normalize_terrain(terrain_str):
    t = (terrain_str or "").upper()
    if any(x in t for x in ("TRES LOURD", "TRÈS LOURD")):
        return "TRES_LOURD"
    if "LOURD" in t:
        return "LOURD"
    if any(x in t for x in ("SOUPLE", "COLLANT")):
        return "SOUPLE"
    if "BON" in t:
        return "BON"
    if "PSF" in t or "FIBRE" in t:
        return "PSF"
    return "INCONNU"


# ---------- 1. DÉFERRAGE (TROT) ----------

def score_deferrage(p):
    d = (p.get("deferrage") or "").upper()
    if "QUATRE" in d or "D4" in d:
        return 3.0
    if "ANTERIEURS" in d or "DA" in d:
        return 1.5
    if "POSTERIEURS" in d or "DP" in d:
        return 1.5
    return 0.0


# ---------- 2. POIDS RELATIF (PLAT, OBSTACLE) ----------

def poids_brut(p):
    for key in ("poidsConditionMonte", "poids", "handicapPoids"):
        v = p.get(key)
        if v is not None:
            try:
                return float(v)
            except Exception:
                pass
    return None


# ---------- 3. CORDE (PLAT) ----------

def corde_brute(p):
    c = p.get("corde")
    if c is None:
        return None
    try:
        return int(c)
    except Exception:
        return None


def hippodrome_a_virages(hippo):
    h = (hippo or "").upper()
    return any(x in h for x in (
        "VINCENNES", "LONGCHAMP", "CHANTILLY", "DEAUVILLE",
        "SAINT-CLOUD", "CAGNES", "MARSEILLE", "TOULOUSE",
        "BORDEAUX", "LYON", "NANTES", "ANGERS", "CAEN",
    ))


# ---------- 4. TERRAIN ----------

def bonus_terrain(terrain_norm, discipline):
    if terrain_norm in ("LOURD", "TRES_LOURD"):
        return 1.0
    if terrain_norm in ("BON", "PSF"):
        return 0.0
    return 0.5


# ---------- 5. EXPÉRIENCE OBSTACLE ----------

def score_experience_obstacle(musique, discipline):
    if discipline != "OBSTACLE":
        return 0.0
    count_h = sum(1 for m in musique if "h" in str(m).lower() and not str(m).lower().startswith("d"))
    count_s = sum(1 for m in musique if "s" in str(m).lower())
    count_c = sum(1 for m in musique if "c" in str(m).lower())
    total = count_h + count_s * 1.5 + count_c * 2.0
    return min(total, 6.0)


def score_incidents_obstacle(musique, discipline):
    if discipline != "OBSTACLE":
        return 0.0
    incidents = 0
    for m in musique[:5]:
        mm = str(m).lower()
        if mm.startswith("t"):
            incidents += 1.5
        elif mm.startswith("a"):
            incidents += 1.0
    return -incidents


# ---------- 6. AUTOSTART (TROT) ----------

def score_autostart(p, num, type_depart):
    """Bonus pour les cordes basses à l'autostart."""
    if "AUTOSTART" not in (type_depart or "").upper():
        return 0.0
    try:
        n = int(num)
    except Exception:
        return 0.0
    if n <= 4:
        return 2.0
    if n <= 6:
        return 1.0
    return 0.0


# ---------- 7. HANDICAP DE DISTANCE (TROT) ----------

def score_handicap_distance(p):
    for key in ("handicapDistance", "recul", "handicap"):
        v = p.get(key)
        if v:
            try:
                val = float(v)
                return -min(val / 25.0, 3.0)
            except Exception:
                pass
    return 0.0


# ---------- 8. DISTANCE OPTIMALE ----------

def extraire_distance_courses(musique_brute, discipline):
    """Extrait les distances des courses depuis la musique brute (peu fiable).
    Retourne None si non disponible."""
    return None


def score_distance_optimale(p, distance_course, discipline):
    """Si le cheval a un champ distance de prédilection, l'utiliser.
    Sinon neutre."""
    if not distance_course:
        return 0.0
    pref = p.get("distancePredilection") or p.get("distanceFavorite")
    if not pref:
        return 0.0
    try:
        ecart = abs(float(distance_course) - float(pref))
        if discipline == "PLAT":
            return -ecart / 400.0
        if discipline == "OBSTACLE":
            return -ecart / 600.0
        return -ecart / 500.0
    except Exception:
        return 0.0


# ---------- 9. RECORD / RK ----------

def score_record(p, discipline):
    """RK (réduction kilométrique) : plus c'est bas, mieux c'est."""
    for key in ("reductionKilometrique", "record", "rk"):
        v = p.get(key)
        if v:
            try:
                return 10.0 - float(v) / 10.0  # 60 sec/km → ~4
            except Exception:
                pass
    return 0.0


# ---------- 10. ŒILLÈRES ----------

def score_oeilleres(p):
    o = p.get("oeilleres")
    if o is True:
        return 1.0
    if o is False:
        return 0.0
    return 0.5


# ---------- 11. SURFACE (PLAT) ----------

def surface_normalisee(p, course_surface):
    s = (course_surface or "").upper()
    if "PSF" in s or "FIBRE" in s:
        return "PSF"
    if "GAZON" in s or "HERBE" in s:
        return "GAZON"
    return "INCONNU"


# ---------- 12. HAUTEUR OBSTACLES ----------

def score_hauteur(p, discipline):
    if discipline != "OBSTACLE":
        return 0.0
    h = p.get("hauteurObstacles")
    if h:
        try:
            return float(h) / 10.0
        except Exception:
            pass
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
# PRÉDIRE — v5.6
# ============================================================

def predire(participants, discipline="AUTRE", terrain="INCONNU",
            hippodrome="", type_depart="", distance_course=None, surface=""):
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
            # Phase 1
            "sdef": score_deferrage(p),
            "spoids": poids_brut(p),
            "scorde": corde_brute(p),
            "sobst": score_experience_obstacle(musique, discipline),
            "sincid": score_incidents_obstacle(musique, discipline),
            # Phase 2
            "sauto": score_autostart(p, num, type_depart),
            "shand": score_handicap_distance(p),
            "sdist": score_distance_optimale(p, distance_course, discipline),
            "srec": score_record(p, discipline),
            # Phase 3
            "soeil": score_oeilleres(p),
            "shauteur": score_hauteur(p, discipline),
        })

    use_z = len(raw) >= MIN_PARTANTS_ZSCORE

    poids_vals = [r["spoids"] for r in raw if r["spoids"] is not None]
    poids_moyen = statistics.mean(poids_vals) if len(poids_vals) >= 2 else None

    applique_corde = (discipline == "PLAT") and hippodrome_a_virages(hippodrome)

    scored = []
    for r in raw:
        if use_z:
            # Base
            zf = zscore([x["sf"] for x in raw], r["sf"])
            zd = zscore([x["sd"] for x in raw], r["sd"])
            zc = zscore([x["sc"] for x in raw], r["sc"])
            zg = zscore([x["sg"] for x in raw], r["sg"])
            zr = zscore([x["sr"] for x in raw], r["sr"])

            # Phase 1
            zdef = zpoids = zcorde = zobst = zincid = 0.0
            if discipline == "TROT":
                zdef = zscore([x["sdef"] for x in raw], r["sdef"])
            if discipline in ("PLAT", "OBSTACLE") and poids_moyen is not None and r["spoids"] is not None:
                if len(poids_vals) >= 2:
                    sp = statistics.pstdev(poids_vals) or 1.0
                    zpoids = -((r["spoids"] - poids_moyen) / sp)
            if applique_corde and r["scorde"] is not None:
                cv = [x["scorde"] for x in raw if x["scorde"] is not None]
                if len(cv) >= 2:
                    zcorde = -zscore(cv, r["scorde"])
            if discipline == "OBSTACLE":
                zobst = zscore([x["sobst"] for x in raw], r["sobst"])
                zincid = zscore([x["sincid"] for x in raw], r["sincid"])

            # Phase 2
            zauto = zhand = zdist = zrec = 0.0
            if discipline == "TROT":
                zauto = zscore([x["sauto"] for x in raw], r["sauto"])
                zhand = zscore([x["shand"] for x in raw], r["shand"])
                zrec = zscore([x["srec"] for x in raw], r["srec"])
            if discipline == "OBSTACLE":
                zrec = zscore([x["srec"] for x in raw], r["srec"])
            if any(x["sdist"] != 0 for x in raw):
                zdist = zscore([x["sdist"] for x in raw], r["sdist"])

            # Phase 3
            zo = zhauteur = 0.0
            zo = zscore([x["soeil"] for x in raw], r["soeil"])
            if discipline == "OBSTACLE":
                zhauteur = zscore([x["shauteur"] for x in raw], r["shauteur"])

            # ---- Combinaison finale par discipline (v5.6) ----
            if discipline == "TROT":
                forecast = (zf * 0.12 + zd * 0.18 + zc * 0.25
                            + zg * 0.10 + zr * 0.08 + zdef * 0.10
                            + zauto * 0.07 + zhand * 0.05 + zrec * 0.05)
            elif discipline == "PLAT":
                forecast = (zf * 0.18 + zd * 0.13 + zc * 0.28
                            + zg * 0.12 + zpoids * 0.10 + zcorde * 0.08
                            + zdist * 0.06 + zo * 0.05)
            elif discipline == "OBSTACLE":
                forecast = (zf * 0.13 + zd * 0.13 + zc * 0.22
                            + zg * 0.08 + zobst * 0.18 + zincid * 0.12
                            + zpoids * 0.08 + zrec * 0.04 + zhauteur * 0.02)
            else:
                forecast = (zf * 0.20 + zd * 0.15 + zc * 0.35
                            + zg * 0.20 + zr * 0.10)
        else:
            forecast = (r["sf"] * 0.15 + r["sd"] * 0.15 + r["sc"] * 0.45
                        + r["sg"] * 0.15 + r["sr"] * 0.10)

        scored.append({
            "num": r["num"],
            "form": r["sf"], "driver": r["sd"], "market": r["sc"],
            "class": r["sg"], "risk": r["sr"],
            "forecast": forecast,
        })

    preds = {k: [] for k in STATS["agents"].keys()}
    for agent in preds:
        key = agent.replace("Agent", "").lower()
        if key == "forecast":
            key = "forecast"
        s = sorted(scored, key=lambda x: x.get(key, 0), reverse=True)
        preds[agent] = [x["num"] for x in s[:5]]
    return preds


def evaluer(participants, arrivee, hippodrome, discipline="AUTRE",
            terrain="INCONNU", type_depart="", distance_course=None, surface=""):
    if not participants or not arrivee:
        return {}
    preds = predire(participants, discipline=discipline, terrain=terrain,
                    hippodrome=hippodrome, type_depart=type_depart,
                    distance_course=distance_course, surface=surface)
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
            discipline_raw = c.get("discipline") or ""
            discipline = detect_discipline(discipline_raw)
            terrain_raw = c.get("terrain") or c.get("conditionPiste") or ""
            terrain = normalize_terrain(terrain_raw)
            type_depart = c.get("depart") or ""
            distance_course = c.get("distance") or None
            surface_raw = c.get("surface") or c.get("piste") or ""
            ev = evaluer(parts, arr, hippo, discipline=discipline,
                         terrain=terrain, type_depart=type_depart,
                         distance_course=distance_course, surface=surface_raw)
            if ev:
                eval_ += 1
            item = {"key": key, "date": ds, "reunion": nr, "num_course": nc,
                    "course": c.get("libelle", "Course"), "hippodrome": hippo,
                    "discipline": discipline_raw,
                    "discipline_norm": discipline,
                    "terrain": terrain,
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


@app.get("/api/cron/run")
async def cron_run(background_tasks: BackgroundTasks):
    background_tasks.add_task(agent_collect, offset=0)
    return {"ok": True, "queued": True}