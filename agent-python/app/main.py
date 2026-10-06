import json
import logging
import os
import secrets
import time
from typing import Literal

from fastapi import Depends, FastAPI, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field

from app.graph.runtime import Runtime
from app.memory.store import Store
from app.tools.router import Router

logging.basicConfig(level=logging.INFO, format="%(message)s")
store = Store()
router = Router(store)
runtime = Runtime(store, router)
app = FastAPI(title="WorkplaceOS Agent Runtime", version="1.0.0")
metrics = {"runs": 0, "failures": 0, "seconds": 0.0}


def identity(
    x_service_token: str = Header(default=""), x_user_id: str = Header(default="")
):
    if (
        not secrets.compare_digest(
            x_service_token, os.getenv("SERVICE_TOKEN", "local-demo-service-token")
        )
        or not x_user_id
    ):
        raise HTTPException(401, "Invalid service identity")
    return x_user_id


class RunRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    message: str = Field(min_length=3, max_length=4000)
    conversation_id: str | None = Field(default=None, max_length=100)
    request_id: str | None = Field(default=None, min_length=8, max_length=100)


class Decision(BaseModel):
    approved: bool


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid")
    building: Literal["Dubai", "London"] = "Dubai"
    zone: Literal["Engineering", "Quiet", ""] = "Engineering"


@app.get("/health")
def health():
    store.get("healthcheck")
    return {"status": "ok", "planner": runtime.planner.name}


@app.get("/metrics")
def metric_values(user=Depends(identity)):
    return Response(
        "\n".join(
            [
                f"workplace_runs_total {metrics['runs']}",
                f"workplace_failures_total {metrics['failures']}",
                f"workplace_run_seconds_sum {metrics['seconds']}",
            ]
        )
        + "\n",
        media_type="text/plain",
    )


@app.post("/runs")
async def run(body: RunRequest, user=Depends(identity)):
    started = time.monotonic()
    metrics["runs"] += 1
    try:
        result = await runtime.start(
            user, body.message, body.conversation_id, body.request_id
        )
    except ValueError as e:
        raise HTTPException(409, str(e))
    metrics["seconds"] += time.monotonic() - started
    if result["errors"]:
        metrics["failures"] += 1
    logging.info(
        json.dumps(
            {
                "event": "run_finished",
                "run_id": result["id"],
                "status": result["status"],
                "duration_ms": round((time.monotonic() - started) * 1000),
            }
        )
    )
    return result


@app.get("/runs")
def runs(user=Depends(identity)):
    return sorted(
        store.list("workflow", user), key=lambda s: s["created_at"], reverse=True
    )[:50]


@app.get("/runs/{run_id}")
def get_run(run_id: str, user=Depends(identity)):
    value = store.get(run_id, user)
    if not value or "plan" not in value:
        raise HTTPException(404)
    return value


@app.post("/runs/{run_id}/approval")
async def approve(run_id: str, body: Decision, user=Depends(identity)):
    try:
        return await runtime.approve(run_id, user, body.approved)
    except ValueError as e:
        raise HTTPException(409, str(e))


@app.get("/preferences")
def preferences(user=Depends(identity)):
    return store.preferences(user)


@app.put("/preferences")
def update_preferences(body: Preferences, user=Depends(identity)):
    store.set_preferences(user, body.model_dump())
    store.audit(user, "preferences_updated")
    return body


@app.delete("/preferences")
def forget_preferences(user=Depends(identity)):
    store.set_preferences(user, {})
    return {"status": "forgotten"}


@app.get("/audit")
def audit(user=Depends(identity)):
    return sorted(store.list("audit", user), key=lambda e: e["at"], reverse=True)[:200]


@app.get("/tools")
async def tools(user=Depends(identity)):
    return await router.discover()


@app.get("/resources")
def resources(user=Depends(identity)):
    return {
        kind: store.list(kind, user) for kind in ["reservation", "ticket", "access"]
    }


@app.post("/runs/{run_id}/retry")
async def retry(run_id: str, user=Depends(identity)):
    try:
        return await runtime.retry(run_id, user)
    except ValueError as e:
        raise HTTPException(409, str(e))
