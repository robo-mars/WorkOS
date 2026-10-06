import os
import secrets

from fastapi import FastAPI, Header, HTTPException

from app.tools.domain import EMPLOYEES

app = FastAPI(title="WorkplaceOS Employee Directory (simulator)")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/employees")
def employees(q: str, x_service_token: str = Header(default="")):
    if not secrets.compare_digest(
        x_service_token, os.getenv("SERVICE_TOKEN", "local-demo-service-token")
    ):
        raise HTTPException(401)
    return [e for e in EMPLOYEES if q.lower() in (e["name"] + " " + e["team"]).lower()]
