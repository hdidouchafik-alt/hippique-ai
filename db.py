import os
import json

print("=== DB.PY CHARGEMENT ===")

try:
    import psycopg
    print("=== psycopg OK ===")
    PSYCOPG_OK = True
except Exception as e:
    print("=== psycopg FAIL: " + str(e) + " ===")
    PSYCOPG_OK = False

DB_URL = os.environ.get("DATABASE_URL", "")

if DB_URL:
    print("=== DATABASE_URL present, longueur=" + str(len(DB_URL)) + " ===")
else:
    print("=== DATABASE_URL ABSENT ===")

DB_OK = PSYCOPG_OK and bool(DB_URL)

print("=== DB_OK = " + str(DB_OK) + " ===")


def init():
    if not DB_OK:
        print("=== init: DB_OK False ===")
        return
    try:
        with psycopg.connect(DB_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE TABLE IF NOT EXISTS collected_results (key TEXT PRIMARY KEY, date TEXT, reunion INTEGER, num_course INTEGER, course TEXT, hippodrome TEXT, discipline TEXT, distance INTEGER, partants INTEGER, arrivee TEXT, evaluations TEXT, created_at TIMESTAMP DEFAULT NOW())")
                cur.execute("CREATE TABLE IF NOT EXISTS learning_stats (agent TEXT PRIMARY KEY, hits_top1 INTEGER DEFAULT 0, hits_top5 INTEGER DEFAULT 0, total INTEGER DEFAULT 0)")
                cur.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
                conn.commit()
        print("=== init OK ===")
    except Exception as e:
        print("=== init FAIL: " + str(e) + " ===")


def save_result(item):
    if not DB_OK:
        return
    try:
        with psycopg.connect(DB_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO collected_results (key, date, reunion, num_course, course, hippodrome, discipline, distance, partants, arrivee, evaluations) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (key) DO NOTHING", (
                    item["key"], item["date"], item["reunion"], item["num_course"],
                    item["course"], item["hippodrome"], item["discipline"],
                    item["distance"], item["partants"],
                    json.dumps(item.get("arrivee", [])),
                    json.dumps(item.get("evaluations", {}))
                ))
                conn.commit()
    except Exception as e:
        print("=== save_result FAIL: " + str(e) + " ===")


def save_agent(name, h1, h5, tot):
    if not DB_OK:
        return
    try:
        with psycopg.connect(DB_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO learning_stats (agent, hits_top1, hits_top5, total) VALUES (%s, %s, %s, %s) ON CONFLICT (agent) DO UPDATE SET hits_top1 = EXCLUDED.hits_top1, hits_top5 = EXCLUDED.hits_top5, total = EXCLUDED.total", (name, h1, h5, tot))
                conn.commit()
    except Exception as e:
        print("=== save_agent FAIL: " + str(e) + " ===")


def save_meta(key, value):
    if not DB_OK:
        return
    try:
        with psycopg.connect(DB_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO meta (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", (key, value))
                conn.commit()
    except Exception as e:
        print("=== save_meta FAIL: " + str(e) + " ===")


def load_results():
    if not DB_OK:
        return []
    try:
        with psycopg.connect(DB_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT key, date, reunion, num_course, course, hippodrome, discipline, distance, partants, arrivee, evaluations FROM collected_results ORDER BY created_at ASC")
                rows = cur.fetchall()
                result = []
                for r in rows:
                    result.append({
                        "key": r[0], "date": r[1], "reunion": r[2], "num_course": r[3],
                        "course": r[4], "hippodrome": r[5], "discipline": r[6],
                        "distance": r[7], "partants": r[8],
                        "arrivee": json.loads(r[9] or "[]"),
                        "evaluations": json.loads(r[10] or "{}"),
                    })
                print("=== load_results: " + str(len(result)) + " cours ===")
                return result
    except Exception as e:
        print("=== load_results FAIL: " + str(e) + " ===")
        return []


def load_agents():
    if not DB_OK:
        return {}
    try:
        with psycopg.connect(DB_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT agent, hits_top1, hits_top5, total FROM learning_stats")
                result = {}
                for r in cur.fetchall():
                    result[r[0]] = {"hits_top1": r[1], "hits_top5": r[2], "total": r[3]}
                return result
    except Exception as e:
        print("=== load_agents FAIL: " + str(e) + " ===")
        return {}


def load_meta(key):
    if not DB_OK:
        return None
    try:
        with psycopg.connect(DB_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT value FROM meta WHERE key = %s", (key,))
                r = cur.fetchone()
                return r[0] if r else None
    except Exception as e:
        print("=== load_meta FAIL: " + str(e) + " ===")
        return None


def reset_all():
    if not DB_OK:
        return
    try:
        with psycopg.connect(DB_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM collected_results")
                cur.execute("DELETE FROM learning_stats")
                cur.execute("DELETE FROM meta")
                conn.commit()
    except Exception as e:
        print("=== reset_all FAIL: " + str(e) + " ===") 