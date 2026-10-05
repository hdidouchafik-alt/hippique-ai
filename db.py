import os
import json

try:
    import psycopg
    PSYCOPG_OK = True
except Exception:
    PSYCOPG_OK = False

DB_URL = os.environ.get("DATABASE_URL", "")
DB_OK = PSYCOPG_OK and bool(DB_URL)


def init():
    if not DB_OK:
        return
    try:
        with psycopg.connect(DB_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("CREATE TABLE IF NOT EXISTS collected_results (key TEXT PRIMARY KEY, date TEXT, reunion INTEGER, num_course INTEGER, course TEXT, hippodrome TEXT, discipline TEXT, distance INTEGER, partants INTEGER, arrivee TEXT, evaluations TEXT, created_at TIMESTAMP DEFAULT NOW())")
                cur.execute("ALTER TABLE collected_results ADD COLUMN IF NOT EXISTS features TEXT")
                cur.execute("CREATE TABLE IF NOT EXISTS learning_stats (agent TEXT PRIMARY KEY, hits_top1 INTEGER DEFAULT 0, hits_top2 INTEGER DEFAULT 0, hits_top3 INTEGER DEFAULT 0, hits_top4 INTEGER DEFAULT 0, hits_top5 INTEGER DEFAULT 0, total INTEGER DEFAULT 0)")
                cur.execute("ALTER TABLE learning_stats ADD COLUMN IF NOT EXISTS hits_top2 INTEGER DEFAULT 0")
                cur.execute("ALTER TABLE learning_stats ADD COLUMN IF NOT EXISTS hits_top3 INTEGER DEFAULT 0")
                cur.execute("ALTER TABLE learning_stats ADD COLUMN IF NOT EXISTS hits_top4 INTEGER DEFAULT 0")
                cur.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT)")
                cur.execute("CREATE TABLE IF NOT EXISTS driver_stats (driver TEXT PRIMARY KEY, courses INTEGER DEFAULT 0, victoires INTEGER DEFAULT 0, top5 INTEGER DEFAULT 0, updated_at TIMESTAMP DEFAULT NOW())")
                cur.execute("CREATE TABLE IF NOT EXISTS hippodrome_stats (hippodrome TEXT PRIMARY KEY, courses INTEGER DEFAULT 0, updated_at TIMESTAMP DEFAULT NOW())")
                cur.execute("CREATE TABLE IF NOT EXISTS agent_history (agent TEXT, race_key TEXT, date TEXT, h1 INTEGER DEFAULT 0, h2 INTEGER DEFAULT 0, h3 INTEGER DEFAULT 0, h4 INTEGER DEFAULT 0, h5 INTEGER DEFAULT 0, created_at TIMESTAMP DEFAULT NOW(), PRIMARY KEY (agent, race_key))")
                conn.commit()
    except Exception as e:
        print("DB init error: " + str(e))


def save_result(item):
    if not DB_OK:
        return
    try:
        with psycopg.connect(DB_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO collected_results (key, date, reunion, num_course, course, hippodrome, discipline, distance, partants, arrivee, evaluations, features) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (key) DO UPDATE SET features = EXCLUDED.features", (
                    item["key"], item["date"], item["reunion"], item["num_course"],
                    item["course"], item["hippodrome"], item["discipline"],
                    item["distance"], item["partants"],
                    json.dumps(item.get("arrivee", [])),
                    json.dumps(item.get("evaluations", {})),
                    json.dumps(item.get("features", []))
                ))
                conn.commit()
    except Exception as e:
        print("DB save_result error: " + str(e))


def save_agent(name, h1, h2, h3, h4, h5, tot):
    if not DB_OK:
        return
    try:
        with psycopg.connect(DB_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO learning_stats (agent, hits_top1, hits_top2, hits_top3, hits_top4, hits_top5, total) VALUES (%s, %s, %s, %s, %s, %s, %s) ON CONFLICT (agent) DO UPDATE SET hits_top1 = EXCLUDED.hits_top1, hits_top2 = EXCLUDED.hits_top2, hits_top3 = EXCLUDED.hits_top3, hits_top4 = EXCLUDED.hits_top4, hits_top5 = EXCLUDED.hits_top5, total = EXCLUDED.total", (name, h1, h2, h3, h4, h5, tot))
                conn.commit()
    except Exception as e:
        print("DB save_agent error: " + str(e))

def save_agent_history(agent, race_key, date, h1, h2, h3, h4, h5):
    if not DB_OK:
        return
    try:
        with psycopg.connect(DB_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO agent_history (agent, race_key, date, h1, h2, h3, h4, h5) VALUES (%s, %s, %s, %s, %s, %s, %s, %s) ON CONFLICT (agent, race_key) DO UPDATE SET h1 = EXCLUDED.h1, h2 = EXCLUDED.h2, h3 = EXCLUDED.h3, h4 = EXCLUDED.h4, h5 = EXCLUDED.h5", (agent, race_key, date, h1, h2, h3, h4, h5))
                conn.commit()
    except Exception as e:
        print("DB save_agent_history error: " + str(e))


def load_agent_history(agent, limit=100):
    if not DB_OK:
        return []
    try:
        with psycopg.connect(DB_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT race_key, date, h1, h2, h3, h4, h5 FROM agent_history WHERE agent = %s ORDER BY created_at DESC LIMIT %s", (agent, limit))
                return [
                    {"race_key": r[0], "date": r[1], "h1": r[2], "h2": r[3], "h3": r[4], "h4": r[5], "h5": r[6]}
                    for r in cur.fetchall()
                ]
    except Exception as e:
        print("DB load_agent_history error: " + str(e))
        return []



def save_meta(key, value):
    if not DB_OK:
        return
    try:
        with psycopg.connect(DB_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO meta (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value", (key, value))
                conn.commit()
    except Exception as e:
        print("DB save_meta error: " + str(e))


def update_driver(driver, position):
    if not DB_OK or not driver:
        return
    try:
        with psycopg.connect(DB_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO driver_stats (driver, courses, victoires, top5) VALUES (%s, 1, %s, %s) ON CONFLICT (driver) DO UPDATE SET courses = driver_stats.courses + 1, victoires = driver_stats.victoires + %s, top5 = driver_stats.top5 + %s, updated_at = NOW()", (
                    driver,
                    1 if position == 1 else 0,
                    1 if position and position <= 5 else 0,
                    1 if position == 1 else 0,
                    1 if position and position <= 5 else 0
                ))
                conn.commit()
    except Exception as e:
        print("DB update_driver error: " + str(e))


def update_hippodrome(hippodrome):
    if not DB_OK or not hippodrome:
        return
    try:
        with psycopg.connect(DB_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("INSERT INTO hippodrome_stats (hippodrome, courses) VALUES (%s, 1) ON CONFLICT (hippodrome) DO UPDATE SET courses = hippodrome_stats.courses + 1, updated_at = NOW()", (hippodrome,))
                conn.commit()
    except Exception as e:
        print("DB update_hippodrome error: " + str(e))


def get_driver_score(driver):
    if not DB_OK or not driver:
        return None
    try:
        with psycopg.connect(DB_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT courses, victoires, top5 FROM driver_stats WHERE driver = %s", (driver,))
                r = cur.fetchone()
                if not r or r[0] < 3:
                    return None
                courses = r[0]
                tx_v = r[1] / courses
                tx_t5 = r[2] / courses
                score = (tx_v * 100.0) + (tx_t5 * 50.0)
                return round(min(score / 50.0, 3.0), 3)
    except Exception as e:
        print("DB get_driver_score error: " + str(e))
        return None


def get_all_driver_stats():
    if not DB_OK:
        return []
    try:
        with psycopg.connect(DB_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT driver, courses, victoires, top5 FROM driver_stats ORDER BY victoires DESC, top5 DESC LIMIT 50")
                return [{"driver": r[0], "courses": r[1], "victoires": r[2], "top5": r[3]} for r in cur.fetchall()]
    except Exception as e:
        print("DB get_all_driver_stats error: " + str(e))
        return []


def load_results():
    if not DB_OK:
        return []
    try:
        with psycopg.connect(DB_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT key, date, reunion, num_course, course, hippodrome, discipline, distance, partants, arrivee, evaluations, features FROM collected_results ORDER BY created_at ASC")
                rows = cur.fetchall()
                result = []
                for r in rows:
                    result.append({
                        "key": r[0], "date": r[1], "reunion": r[2], "num_course": r[3],
                        "course": r[4], "hippodrome": r[5], "discipline": r[6],
                        "distance": r[7], "partants": r[8],
                        "arrivee": json.loads(r[9] or "[]"),
                        "evaluations": json.loads(r[10] or "{}"),
                        "features": json.loads(r[11] or "[]"),
                    })
                return result
    except Exception as e:
        print("DB load_results error: " + str(e))
        return [] 


def load_agents():
    if not DB_OK:
        return {}
    try:
        with psycopg.connect(DB_URL) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT agent, hits_top1, hits_top2, hits_top3, hits_top4, hits_top5, total FROM learning_stats")
                result = {}
                for r in cur.fetchall():
                    result[r[0]] = {
                        "hits_top1": r[1],
                        "hits_top2": r[2],
                        "hits_top3": r[3],
                        "hits_top4": r[4],
                        "hits_top5": r[5],
                        "total": r[6],
                    }
                return result
    except Exception as e:
        print("DB load_agents error: " + str(e))
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
        print("DB load_meta error: " + str(e))
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
        print("DB reset_all error: " + str(e))