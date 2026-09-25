from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx

app = FastAPI(title="PMU Proxy")

# Autorise les appels depuis n'importe quel site (notre site principal)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

PMU_BASE_URL = "https://online.turfinfo.api.pmu.fr/rest/client/61"

@app.get("/")
async def root():
    return {"message": "Proxy PMU en ligne"}

@app.get("/pmu/{path:path}")
async def proxy_pmu(path: str):
    """
    Relaye la requête vers l'API PMU.
    Exemple : /pmu/programme/25092026
    """
    url = f"{PMU_BASE_URL}/{path}"
    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            r = await client.get(url)
            return r.json()
    except Exception as e:
        return {"error": str(e)}