import json, math, uuid
from datetime import datetime
from typing import Optional, List
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(title="Hippique API", version="14.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])

DB = {"races": {}, "runners": {}, "predictions": {}, "outcomes": {},
      "metrics": {"total_predictions": 0, "total_correct": 0,
                  "total_wrong": 0, "roi": 0.0, "by_discipline": {}}}

DRIVERS_TOP = {'E. Raffin':5,'M. Abrivard':4,'F. Nivard':5,'D. Thomain':4,
    'B. Rochard':3,'A. Barrier':3,'P.ph. Ploquin':3,'M. Heurtebise':2,
    'Ch.a. Mary':2,'A. Collette':2,'A. Thomas':2,'J. Gosselin':2,
    'N. Bazire':4,'J.m. Bazire':4,'Y. Lebourgeois':3,'T. Le Beller':2}

JOCKEYS_TOP = {'C.demuro':5,'M.guyon':5,'C.soumillon':5,'S.pasquier':5,
               'Pc.boudot':4,'M.barzalona':4,'A.hamelin':3,'E.hardouin':3}

def points_musique(m):
    t = 0
    for r in m[:5]:
        s = str(r).strip().lower()
        if s.startswith('1'): t += 10
        elif s.startswith('2'): t += 8
        elif s.startswith('3'): t += 6
        elif s.startswith('4'): t += 5
        elif s.startswith('5'): t += 4
        elif s.startswith('6'): t += 3
        elif s.startswith('7'): t += 2
        elif s.startswith('8'): t += 1
    return t

def podiums3(m):
    return sum(1 for x in m[:3] if str(x).strip() and str(x).strip()[0] in '123')

def compter_da(m, n=5):
    return sum(1 for x in m[:n] if str(x).lower().startswith('d'))

def penalite_da(m):
    d2 = compter_da(m, 2)
    d5 = compter_da(m, 5)
    if d2 >= 1: return -8 * d2
    return -3 * (d5 - d2)

def normaliser(s):
    if not s: return []
    mn, mx = min(s), max(s)
    if mx == mn: return [0.5]*len(s)
    return [(x-mn)/(mx-mn) for x in s]

def softmax(s, T=0.8):
    if not s: return []
    mx = max(s)
    e = [math.exp((x-mx)/T) for x in s]
    tot = sum(e)
    return [x/tot for x in e]

def kelly(cap, cote, p, frac=0.25, maxpct=0.02):
    b = cote - 1
    if b <= 0: return 0.0
    k = (b*p - (1-p))/b
    if k <= 0: return 0.0
    if cote > 15:
        k *= max(0.5, 1 - (cote-15)/100)
    return round(min(cap*k*frac, cap*maxpct), 2)

def score_trot(c, autostart):
    forme = float(c.get('forme', 50))
    ent = float(c.get('entourage', 50))
    num = int(c.get('num', 99))
    gains = float(c.get('gains', 0))
    nbc = float(c.get('nb_courses', 1))
    mus = c.get('musique', [])
    db = DRIVERS_TOP.get(c.get('driver', ''), 0)
    cote = float(c.get('cote_finale', c.get('cote', 10)))
    couv = float(c.get('cote_ouverture', cote))
    if autostart:
        nb = 10 if 1 <= num <= 5 else (0 if num <= 9 else -5)
    else: nb = 0
    mda = penalite_da(mus)
    gb = min((gains / max(nbc, 1)) / 1000, 10)
    db2 = 5 if c.get('deferre') else 0
    pm = points_musique(mus) * 0.7
    bm = 6 if podiums3(mus) >= 3 else 0
    money = 10 if cote < couv * 0.7 else 0
    return (forme*0.30 + ent*0.20 + pm*0.30 + nb + gb + db
            + db2 + bm + money + mda + 25)

def score_plat(c):
    forme = float(c.get('forme', 50))
    ent = float(c.get('entourage', 50))
    corde = int(c.get('corde', 8))
    poids = float(c.get('poids', 60))
    vh = float(c.get('val_hand', 30))
    mus = c.get('musique', [])
    jb = JOCKEYS_TOP.get(c.get('jockey', ''), 1)
    cote = float(c.get('cote_finale', c.get('cote', 10)))
    couv = float(c.get('cote_ouverture', cote))
    if 1 <= corde <= 4: cb = 5
    elif 5 <= corde <= 8: cb = 0
    elif 9 <= corde <= 12: cb = -2.5
    else: cb = -5
    pb = min((60 - poids) * 1.5, 5.0)
    malus = -15 if (poids <= 60 and vh <= 20 and corde >= 8) else 0
    pm = points_musique(mus)
    bm = 5 if podiums3(mus) >= 3 else 0
    money = 10 if cote < couv * 0.7 else 0
    return (forme*0.25 + ent*0.25 + pm*0.5 + cb + pb
            + jb + bm + money + malus + 25)

def analyser(course):
    disc = course.get('discipline', '').lower()
    auto = course.get('autostart', False)
    T = 0.8 if disc == 'plat' else 0.9
    seuil = 0.05
    partants = [c for c in course['partants'] if not c.get('np', False)]
    valides = []
    for c in partants:
        if not c.get('musique'): continue
        if not c.get('cote_finale') and not c.get('cote'): continue
        if c.get('np_final'): continue
        if disc == 'trot':
            if not c.get('driver'): continue
            if compter_da(c.get('musique', []), 5) >= 2: continue
        valides.append(c)
    if not valides: return []
    for c in valides:
        if not c.get('cote_finale'):
            c['cote_finale'] = c.get('cote')
        c['score'] = score_trot(c, auto) if disc == 'trot' else score_plat(c)
    scores = [c['score'] for c in valides]
    probas = softmax(normaliser(scores), T)
    for c, p in zip(valides, probas):
        c['p_calibree'] = p
        c['p_implicite'] = 1.0 / float(c['cote_finale'])
        c['value'] = p - c['p_implicite']
        c['type_pari'] = None
        c['mise'] = 0.0
    for c in valides:
        if c['value'] >= seuil and c['cote_finale'] <= 30:
            c['type_pari'] = 'Place' if c['cote_finale'] > 20 else 'Gagnant'
            c['mise'] = kelly(1000, c['cote_finale'], c['p_calibree'])
    valides.sort(key=lambda x: x['value'], reverse=True)
    return valides

# ============ MODELES ============
class Runner(BaseModel):
    num: int
    nom: str
    cote: float
    cote_finale: Optional[float] = None
    cote_ouverture: Optional[float] = None
    musique: List[str] = []
    forme: Optional[float] = 50
    entourage: Optional[float] = 50
    driver: Optional[str] = None
    gains: Optional[float] = 0
    nb_courses: Optional[int] = 30
    deferre: Optional[bool] = False
    jockey: Optional[str] = None
    corde: Optional[int] = None
    poids: Optional[float] = None
    val_hand: Optional[float] = 30
    np_final: Optional[bool] = False

class RaceCreate(BaseModel):
    nom: str
    discipline: str
    distance: int = 2000
    autostart: bool = False
    terrain: str = "Bon"
    type: Optional[str] = ""
    partants: List[Runner]

class OutcomeCreate(BaseModel):
    arrivee: List[int]

# ============ ENDPOINTS ============
@app.get("/")
def root():
    return {"nom": "Hippique API", "version": "14.0.0",
            "endpoints": ["/api/analysis/race", "/api/analysis/race/{id}",
                "/api/analysis/runner/{id}", "/api/predictions",
                "/api/predictions/{id}/outcome", "/api/learning/metrics",
                "/health", "/docs"]}

@app.get("/health")
def health():
    return {"status": "OK", "time": datetime.now().isoformat()}

@app.post("/api/analysis/race")
def create_race(race: RaceCreate):
    rid = str(uuid.uuid4())[:8]
    cd = race.dict()
    cd['discipline'] = race.discipline.lower()
    try:
        res = analyser(cd)
    except Exception as e:
        raise HTTPException(500, str(e))
    DB["races"][rid] = {"id": rid, "created_at": datetime.now().isoformat(),
        "course": cd, "resultats": [
            {"num": c["num"], "nom": c["nom"], "cote": c["cote_finale"],
             "p_calibree": round(c["p_calibree"], 4),
             "value": round(c["value"], 4), "score": round(c["score"], 2),
             "type_pari": c.get("type_pari"), "mise": c.get("mise", 0)}
            for c in res]}
    for r in race.partants:
        DB["runners"][f"{rid}_{r.num}"] = {"id": f"{rid}_{r.num}",
            "race_id": rid, "num": r.num, "nom": r.nom, "cote": r.cote}
    return DB["races"][rid]

@app.get("/api/analysis/race/{rid}")
def get_race(rid: str):
    if rid not in DB["races"]: raise HTTPException(404, "Race non trouvee")
    return DB["races"][rid]

@app.get("/api/analysis/runner/{runner_id}")
def get_runner(runner_id: str):
    if runner_id not in DB["runners"]: raise HTTPException(404, "Runner non trouve")
    return DB["runners"][runner_id]

@app.post("/api/predictions")
def create_pred(race: RaceCreate):
    pid = str(uuid.uuid4())[:8]
    cd = race.dict()
    cd['discipline'] = race.discipline.lower()
    try:
        res = analyser(cd)
    except Exception as e:
        raise HTTPException(500, str(e))
    paris = [c for c in res if c.get('mise', 0) > 0]
    pred = {"id": pid, "created_at": datetime.now().isoformat(),
        "nom": race.nom, "discipline": cd['discipline'],
        "statut": "en_attente",
        "pronostic": [{"rang": i+1, "num": c["num"], "nom": c["nom"],
            "cote": c["cote_finale"], "p_calibree": round(c["p_calibree"], 4),
            "value": round(c["value"], 4)} for i, c in enumerate(res[:8])],
        "paris": [{"num": p["num"], "nom": p["nom"], "cote": p["cote_finale"],
            "type": p["type_pari"], "mise": p["mise"],
            "value": round(p["value"], 4)} for p in paris],
        "total_mise": round(sum(p["mise"] for p in paris), 2),
        "arrivee": None, "pnl": 0.0}
    DB["predictions"][pid] = pred
    DB["metrics"]["total_predictions"] += 1
    return pred

@app.get("/api/predictions")
def list_preds(statut: Optional[str] = None):
    preds = list(DB["predictions"].values())
    if statut: preds = [p for p in preds if p["statut"] == statut]
    return {"total": len(preds), "predictions": preds}

@app.get("/api/predictions/{pid}")
def get_pred(pid: str):
    if pid not in DB["predictions"]: raise HTTPException(404, "Prediction non trouvee")
    return DB["predictions"][pid]

@app.post("/api/predictions/{pid}/outcome")
def add_outcome(pid: str, outcome: OutcomeCreate):
    if pid not in DB["predictions"]: raise HTTPException(404, "Prediction non trouvee")
    pred = DB["predictions"][pid]
    if pred["statut"] == "terminee": raise HTTPException(400, "Deja cloturee")
    places = {n: i+1 for i, n in enumerate(outcome.arrivee)}
    total = 0.0
    details = []
    for p in pred["paris"]:
        place = places.get(int(p["num"]))
        gain = 0.0; statut = "Perdu"
        if p["type"] == "Gagnant" and place == 1:
            gain = p["mise"] * p["cote"]; statut = "Gagne"
        elif p["type"] == "Place" and place and place <= 3:
            gain = p["mise"] * max((p["cote"]-1)/4+1, 1.1); statut = "Gagne"
        pnl = gain - p["mise"]; total += pnl
        details.append({"num": p["num"], "nom": p["nom"], "place": place,
            "statut": statut, "mise": p["mise"],
            "gain": round(gain, 2), "pnl": round(pnl, 2)})
    pred["statut"] = "terminee"; pred["arrivee"] = outcome.arrivee
    pred["pnl"] = round(total, 2); pred["resultats_paris"] = details
    DB["metrics"]["total_correct"] += sum(1 for d in details if d["statut"] == "Gagne")
    DB["metrics"]["total_wrong"] += sum(1 for d in details if d["statut"] == "Perdu")
    d = pred["discipline"]
    if d not in DB["metrics"]["by_discipline"]:
        DB["metrics"]["by_discipline"][d] = {"nb": 0, "pnl": 0.0}
    DB["metrics"]["by_discipline"][d]["nb"] += 1
    DB["metrics"]["by_discipline"][d]["pnl"] += total
    DB["outcomes"][pid] = {"prediction_id": pid, "arrivee": outcome.arrivee,
        "details": details, "pnl": round(total, 2),
        "created_at": datetime.now().isoformat()}
    return DB["outcomes"][pid]

@app.get("/api/learning/metrics")
def metrics():
    tot = DB["metrics"]["total_correct"] + DB["metrics"]["total_wrong"]
    acc = (DB["metrics"]["total_correct"] / tot * 100) if tot > 0 else 0
    return {"total_predictions": DB["metrics"]["total_predictions"],
        "total_correct": DB["metrics"]["total_correct"],
        "total_wrong": DB["metrics"]["total_wrong"],
        "accuracy": round(acc, 2), "roi": DB["metrics"]["roi"],
        "by_discipline": DB["metrics"]["by_discipline"],
        "last_update": datetime.now().isoformat()}