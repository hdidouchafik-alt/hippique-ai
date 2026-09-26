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

app = FastAPI(title="Hippique AI", version="5.7.0")
BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")

MISE = 10
PMU_BASE = "https://online.turfinfo.api.pmu.fr/rest/client/61"
HEADERS = {"User-Agent": "Mozilla/5.0"}

MIN_PARTANTS_ZSCORE = 5

MISES_PMU = {
    "simple_gagnant": 2.0,
    "simple_place": 2.0,
    "couple_gagnant": 2.0,
    "couple_place": 2.0,
    "trio": 2.0,
    "2sur4": 3.0,
    "quinte_ordre": 2.0,
    "quinte_desordre": 2.0,
    "quinte_bonus4": 2.0,
    "quinte_bonus3": 2.0,
    "top5": 2.0,
    "top4": 2.0,
}

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

PARIS_STATS = {
    "simple_gagnant": {"gagne": 0, "total": 0, "mise": 0.0, "gain": 0.0},
    "simple_place": {"gagne": 0, "total": 0, "mise": 0.0, "gain": 0.0},
    "couple_gagnant": {"gagne": 0, "total": 0},
    "couple_place": {"gagne": 0, "total": 0},
    "trio": {"gagne": 0, "total": 0},
    "quinte_ordre": {"gagne": 0, "total": 0},
    "quinte_desordre": {"gagne": 0, "total": 0},
    "quinte_bonus4": {"gagne": 0, "total": 0},
    "quinte_bonus3": {"gagne": 0, "total": 0},
    "top5": {"gagne": 0, "total": 0},
    "top4": {"gagne": 0, "total": 0},
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


@app.get("/paris", response_class=HTMLResponse)
async def paris_page(request: Request):
    try:
        return templates.TemplateResponse(request, "paris.html")
    except Exception:
        return HTMLResponse(
            "<h1>Page /paris</h1>"
            "<p>Template manquant.</p>"
            "<p>Donnees : <a href='/api/paris/stats'>/api/paris/stats</a></p>"
        )


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
        "paris": PARIS_STATS,
        "database": DB_OK,
    }


@app.get("/api/paris/stats")
async def paris_stats():
    stats = {}
    for pari, s in PARIS_STATS.items():
        total = s.get("total", 0)
        gagne = s.get("gagne", 0)
        bloc = {
            "total": total,
            "gagne": gagne,
            "taux_reussite": round(gagne / total * 100, 2) if total > 0 else 0,
        }
        if pari in ("simple_gagnant", "simple_place"):
            mise = s.get("mise", 0.0)
            gain = s.get("gain", 0.0)
            bloc["mise"] = round(mise, 2)
            bloc["gain"] = round(gain, 2)
            bloc["roi_euros"] = round(gain - mise, 2)
            bloc["roi_pct"] = round((gain - mise) / mise * 100, 2) if mise > 0 else 0
        stats[pari] = bloc
    return {
        "stats": stats,
        "mises_reference": MISES_PMU,
        "evaluated": STATS["evaluated"],
    }


@app.get("/api/learning/reset")
async def learning_reset():
    COLLECTED.clear()
    STATS["evaluated"] = 0
    for name in STATS["agents"]:
        STATS["agents"][name] = {"h1": 0, "h5": 0, "tot": 0}
    for pari in PARIS_STATS:
        for k in PARIS_STATS[pari]:
            PARIS_STATS[pari][k] = 0
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
    for pari in PARIS_STATS:
        for k in PARIS_STATS[pari]:
            PARIS_STATS[pari][k] = 0
    if DB_OK:
        db.reset_all()
    return {"ok": True, "message": "Base purge"}


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
    if any(x in t for x in ("TRES LOURD", "TRES LOURD")):
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


def score_deferrage(p):
    d = (p.get("deferrage") or "").upper()
    if "QUATRE" in d or "D4" in d:
        return 3.0
    if "ANTERIEURS" in d or "DA" in d:
        return 1.5
    if "POSTERIEURS" in d or "DP" in d:
        return 1.5
    return 0.0


def poids_brut(p):
    for key in ("poidsConditionMonte", "poids", "handicapPoids"):
        v = p.get(key)
        if v is not None:
            try:
                return float(v)
            except Exception:
                pass
    return None


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


def score_autostart(p, num, type_depart):
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


def score_distance_optimale(p, distance_course, discipline):
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


def score_record(p, discipline):
    for key in ("reductionKilometrique", "record", "rk"):
        v = p.get(key)
        if v:
            try:
                return 10.0 - float(v) / 10.0
            except Exception:
                pass
    return 0.0


def score_oeilleres(p):
    o = p.get("oeilleres")
    if o is True:
        return 1.0
    if o is False:
        return 0.0
    return 0.5


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


def detecter_quinte(course, reunion):
    if not isinstance(course, dict):
        return False
    for key in ("categorieParticuliere", "paris", "typePari", "specialite",
                "libelle", "libelleCourt", "conditions", "categorie"):
        val = str(course.get(key) or "").upper()
        if "QUINTE" in val or "Q5" in val or "Q+" in val:
            return True
    if course.get("quinte"):
        return True
    if isinstance(reunion, dict):
        for key in ("quinte", "quintePlus", "courseQuinte", "numeroQuinte"):
            if reunion.get(key):
                return True
    return False


def calculer_roi_pmu(predictions, arrivee, cotes, est_quinte=False):
    resultats = {}
    if not arrivee:
        return resultats

    v1 = arrivee[0] if len(arrivee) >= 1 else None
    v3 = set(arrivee[:3]) if len(arrivee) >= 3 else set(arrivee)
    v4 = set(arrivee[:4]) if len(arrivee) >= 4 else set(arrivee)
    v5 = set(arrivee[:5]) if len(arrivee) >= 5 else set(arrivee)

    pred = predictions.get("ForecastAgent", []) or []
    pred_top2 = pred[:2] if len(pred) >= 2 else pred
    pred_top3 = pred[:3] if len(pred) >= 3 else pred
    pred_top4 = pred[:4] if len(pred) >= 4 else pred
    pred_top5 = pred[:5] if len(pred) >= 5 else pred

    gagne = bool(pred_top5) and pred_top5[0] == v1
    mise = MISES_PMU["simple_gagnant"]
    cote = cotes.get(v1, 0) if v1 else 0
    gain = mise * cote * 0.85 if gagne and cote > 0 else 0
    resultats["simple_gagnant"] = {
        "gagne": gagne, "mise": mise,
        "gain": round(gain, 2),
        "roi_euros": round(gain - mise, 2),
    }

    gagne = bool(pred_top5) and pred_top5[0] in v3
    mise = MISES_PMU["simple_place"]
    cote = cotes.get(pred_top5[0], 0) if pred_top5 else 0
    gain = mise * cote * 0.30 if gagne and cote > 0 else 0
    resultats["simple_place"] = {
        "gagne": gagne, "mise": mise,
        "gain": round(gain, 2),
        "roi_euros": round(gain - mise, 2),
    }

    gagne = len(set(pred_top2) & set(arrivee[:2])) == 2 if len(arrivee) >= 2 else False
    resultats["couple_gagnant"] = {"gagne": gagne}

    gagne = len(set(pred_top2) & v3) == 2 if v3 else False
    resultats["couple_place"] = {"gagne": gagne}

    gagne = set(pred_top3) == v3 if v3 else False
    resultats["trio"] = {"gagne": gagne}

    if est_quinte and len(arrivee) >= 5:
        resultats["quinte_ordre"] = {"gagne": pred_top5 == arrivee[:5]}
        resultats["quinte_desordre"] = {"gagne": set(pred_top5) == v5}
        resultats["quinte_bonus4"] = {"gagne": len(set(pred_top5) & v5) == 4}
        resultats["quinte_bonus3"] = {"gagne": len(set(pred_top5) & v5) == 3}

    resultats["top5"] = {"gagne": len(set(pred_top5) & v5) == 5 if v5 else False}
    resultats["top4"] = {"gagne": set(pred_top4) == v4 if v4 else False}

    return resultats


def maj_paris_stats(roi_pmu):
    for pari, data in roi_pmu.items():
        if pari not in PARIS_STATS:
            continue
        PARIS_STATS[pari]["total"] = PARIS_STATS[pari].get("total", 0) + 1
        if data.get("gagne"):
            PARIS_STATS[pari]["gagne"] = PARIS_STATS[pari].get("gagne", 0) + 1
        if "mise" in data:
            PARIS_STATS[pari]["mise"] = PARIS_STATS[pari].get("mise", 0.0) + data["mise"]
            PARIS_STATS[pari]["gain"] = PARIS_STATS[pari].get("gain", 0.0) + data.get("gain", 0)
            

def predire(participants, discipline="AUTRE", terrain="INCONNU",
            hippodrome="", type_depart="", distance_course=None, surface=""):
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
            "spoids": poids_brut(p),
            "scorde": corde_brute(p),
            "sobst": score_experience_obstacle(musique, discipline),
            "sincid": score_incidents_obstacle(musique, discipline),
            "sauto": score_autostart(p, num, type_depart),
            "shand": score_handicap_distance(p),
            "sdist": score_distance_optimale(p, distance_course, discipline),
            "srec": score_record(p, discipline),
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
            zf = zscore([x["sf"] for x in raw], r["sf"])
            zd = zscore([x["sd"] for x in raw], r["sd"])
            zc = zscore([x["sc"] for x in raw], r["sc"])
            zg = zscore([x["sg"] for x in raw], r["sg"])
            zr = zscore([x["sr"] for x in raw], r["sr"])

            zdef = 0.0
            zpoids = 0.0
            zcorde = 0.0
            zobst = 0.0
            zincid = 0.0

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

            zauto = 0.0
            zhand = 0.0
            zdist = 0.0
            zrec = 0.0

            if discipline == "TROT":
                zauto = zscore([x["sauto"] for x in raw], r["sauto"])
                zhand = zscore([x["shand"] for x in raw], r["shand"])
                zrec = zscore([x["srec"] for x in raw], r["srec"])
            if discipline == "OBSTACLE":
                zrec = zscore([x["srec"] for x in raw], r["srec"])
            if any(x["sdist"] != 0 for x in raw):
                zdist = zscore([x["sdist"] for x in raw], r["sdist"])

            zo = zscore([x["soeil"] for x in raw], r["soeil"])
            zhauteur = 0.0
            if discipline == "OBSTACLE":
                zhauteur = zscore([x["shauteur"] for x in raw], r["shauteur"])

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
            "form": r["sf"],
            "driver": r["sd"],
            "market": r["sc"],
            "class": r["sg"],
            "risk": r["sr"],
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
            terrain="INCONNU", type_depart="", distance_course=None,
            surface="", est_quinte=False):
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

    roi_pmu = calculer_roi_pmu(preds, arrivee, cotes, est_quinte=est_quinte)
    maj_paris_stats(roi_pmu)

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
        if name == "ForecastAgent":
            res[name]["roi_pmu"] = roi_pmu

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
            est_quinte = detecter_quinte(c, r)
            ev = evaluer(parts, arr, hippo, discipline=discipline,
                         terrain=terrain, type_depart=type_depart,
                         distance_course=distance_course, surface=surface_raw,
                         est_quinte=est_quinte)
            if ev:
                eval_ += 1
            item = {"key": key, "date": ds, "reunion": nr, "num_course": nc,
                    "course": c.get("libelle", "Course"), "hippodrome": hippo,
                    "discipline": discipline_raw,
                    "discipline_norm": discipline,
                    "terrain": terrain,
                    "distance": c.get("distance", 0),
                    "partants": c.get("nombreDeclaresPartants", 0),
                    "est_quinte": est_quinte,
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
# v5.8 : ROUTES COURSES (arrivée + partants)
# ============================================================

@app.get("/api/courses/passees")
async def courses_passees(limit: int = 30):
    """Liste des courses terminées (avec arrivée)."""
    courses = [c for c in COLLECTED if c.get("arrivee")]
    courses = courses[-limit:]
    return {"count": len(courses), "courses": courses}


@app.get("/api/courses/a_venir")
async def courses_a_venir(offset: int = 0):
    """Liste des courses du jour non terminées."""
    ds = date_str(offset)
    prog = await pmu_get(PMU_BASE + "/programme/" + ds)
    if not prog:
        return {"ok": False, "courses": [], "error": "PMU indisponible"}
    reunions = (prog.get("programme") or {}).get("reunions") or []
    courses = []
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
            if "FIN" in st or "ARRIVE" in st:
                continue
            nc = c.get("numOrdre")
            key = ds + "-R" + str(nr) + "C" + str(nc)
            heure = c.get("heureDepart") or ""
            try:
                h = datetime.fromtimestamp(int(heure) / 1000).strftime("%H:%M")
            except Exception:
                h = str(heure)[:5] if heure else "?"
            courses.append({
                "key": key,
                "reunion": nr,
                "num_course": nc,
                "hippodrome": hippo,
                "course": c.get("libelle", "Course"),
                "discipline": c.get("discipline", "?"),
                "distance": c.get("distance", 0),
                "partants": c.get("nombreDeclaresPartants", 0),
                "heure": h,
                "statut": st,
            })
    return {"ok": True, "count": len(courses), "courses": courses, "date": ds}


@app.get("/api/course/{key}")
async def course_detail(key: str):
    """Détail d'une course : infos + partants (avec pronostic si dispo)."""
    # Vérifier si c'est une course déjà collectée
    for c in COLLECTED:
        if c.get("key") == key:
            return {"ok": True, "source": "collected", "course": c}

    # Sinon, c'est une course à venir : récupérer les partants via PMU
    # key format : "26092026-R1C3"
    parts = key.split("-")
    if len(parts) != 2 or not parts[0] or not parts[1].startswith("R"):
        return {"ok": False, "error": "Clé invalide"}

    ds = parts[0]
    rc = parts[1][1:]  # "1C3"
    if "C" not in rc:
        return {"ok": False, "error": "Clé invalide"}
    nr, nc = rc.split("C", 1)
    try:
        nr = int(nr)
        nc = int(nc)
    except Exception:
        return {"ok": False, "error": "Clé invalide"}

    prog = await pmu_get(PMU_BASE + "/programme/" + ds)
    if not prog:
        return {"ok": False, "error": "PMU indisponible"}

    course_info = None
    reunion_info = None
    for r in ((prog.get("programme") or {}).get("reunions") or []):
        if not isinstance(r, dict):
            continue
        if r.get("numOfficiel") == nr:
            reunion_info = r
            for c in (r.get("courses") or []):
                if isinstance(c, dict) and c.get("numOrdre") == nc:
                    course_info = c
                    break
            break

    if not course_info:
        return {"ok": False, "error": "Course introuvable"}

    parts_data = await get_participants(ds, nr, nc)
    if not parts_data:
        return {"ok": False, "error": "Partants indisponibles"}

    # Construire la liste des partants
    liste = []
    for p in parts_data:
        if not isinstance(p, dict):
            continue
        num = p.get("numPmu")
        if not num:
            continue
        nom = p.get("nom") or "?"
        driver = p.get("driver") or p.get("jockey") or "?"
        entraineur = p.get("entraineur") or "?"
        musique = p.get("musique") or ""
        cote = (p.get("dernierRapportDirect") or {}).get("rapport")
        gains = (p.get("gainsParticipant") or {}).get("gainsCarriere", 0)
        deferrage = p.get("deferrage") or ""
        poids = p.get("poidsConditionMonte") or p.get("poids")
        corde = p.get("corde")
        sexe = p.get("sexe") or "?"
        age = p.get("age")

        liste.append({
            "num": num,
            "nom": nom,
            "driver": driver,
            "entraineur": entraineur,
            "musique": musique,
            "cote": cote,
            "gains": gains,
            "deferrage": deferrage,
            "poids": poids,
            "corde": corde,
            "sexe": sexe,
            "age": age,
        })

    # Calculer les pronostics si possible
    discipline_raw = course_info.get("discipline") or ""
    discipline = detect_discipline(discipline_raw)
    terrain_raw = course_info.get("terrain") or course_info.get("conditionPiste") or ""
    terrain = normalize_terrain(terrain_raw)
    type_depart = course_info.get("depart") or ""
    distance_course = course_info.get("distance") or None
    surface_raw = course_info.get("surface") or course_info.get("piste") or ""

    try:
        preds = predire(parts_data, discipline=discipline, terrain=terrain,
                        hippodrome=(reunion_info.get("hippodrome") or {}).get("libelleLong", "") if reunion_info else "",
                        type_depart=type_depart, distance_course=distance_course, surface=surface_raw)
    except Exception:
        preds = {}

    return {
        "ok": True,
        "source": "pmu",
        "course": {
            "key": key,
            "date": ds,
            "reunion": nr,
            "num_course": nc,
            "hippodrome": (reunion_info.get("hippodrome") or {}).get("libelleLong", "?") if reunion_info else "?",
            "course": course_info.get("libelle", "Course"),
            "discipline": discipline_raw,
            "discipline_norm": discipline,
            "terrain": terrain,
            "distance": distance_course,
            "partants": course_info.get("nombreDeclaresPartants", 0),
            "statut": (course_info.get("statut") or "").upper(),
        },
        "partants": liste,
        "pronostics": preds,
    }


@app.get("/api/quinte/jour")
async def quinte_du_jour(offset: int = 0):
    """Retourne le Quinté+ du jour avec son arrivée si terminé, sinon ses partants."""
    ds = date_str(offset)
    prog = await pmu_get(PMU_BASE + "/programme/" + ds)
    if not prog:
        return {"ok": False, "error": "PMU indisponible"}

    for r in ((prog.get("programme") or {}).get("reunions") or []):
        if not isinstance(r, dict):
            continue
        for c in (r.get("courses") or []):
            if not isinstance(c, dict):
                continue
            if not detecter_quinte(c, r):
                continue
            nr = r.get("numOfficiel")
            nc = c.get("numOrdre")
            key = ds + "-R" + str(nr) + "C" + str(nc)
            # Chercher dans COLLECTED
            for collected in COLLECTED:
                if collected.get("key") == key:
                    return {"ok": True, "statut": "termine", "course": collected}

            # Sinon, récupérer les partants
            details = await course_detail(key)
            return {"ok": True, "statut": "a_venir", **details}

    return {"ok": False, "error": "Aucun Quinté+ trouvé ce jour"}
@app.get("/api/cron/run")
async def cron_run(background_tasks: BackgroundTasks):
    background_tasks.add_task(agent_collect, offset=0)
    return {"ok": True, "queued": True}