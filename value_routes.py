from __future__ import annotations

from fastapi import HTTPException
from pydantic import BaseModel, Field

from value_engine import ValueEngine


class ValueRequest(BaseModel):
    runners: list[dict] = Field(..., min_length=1)
    race: dict = Field(default_factory=dict)
    capital: float = Field(default=0.0, ge=0)
    temperature: float = Field(default=10.0, gt=0)


@app.post("/api/value/analyse")
async def analyse_value(payload: ValueRequest):
    try:
        return ValueEngine(payload.temperature).analyse(payload.runners, payload.race, payload.capital)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
