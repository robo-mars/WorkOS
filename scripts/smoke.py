"""Real HTTP integration test against a running local stack (fictional data only)."""

import asyncio
import json
import os
import uuid
from datetime import date, timedelta
from pathlib import Path

import httpx
from mcp.client.streamable_http import streamablehttp_client

from mcp import ClientSession


async def main():
    checks = []
    # MCP discovery and schema-error responses over actual protocol sessions.
    for port, expected in [
        (8001, {"search_rooms", "reserve_room", "cancel_reservation"}),
        (8002, {"create_it_ticket", "get_it_ticket", "update_it_ticket"}),
    ]:
        async with streamablehttp_client(
            os.getenv(
                "BOOKING_MCP_URL" if port == 8001 else "IT_MCP_URL",
                f"http://127.0.0.1:{port}/mcp",
            )
        ) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                assert expected == {t.name for t in tools.tools}
                invalid = await session.call_tool(
                    "reserve_room" if port == 8001 else "create_it_ticket", {}
                )
                assert invalid.isError
                checks.append(f"MCP {port}: discovery + invalid arguments")
    async with httpx.AsyncClient(
        base_url=os.getenv("SMOKE_GATEWAY_URL", "http://127.0.0.1:8080"), timeout=120
    ) as client:
        assert (await client.get("/api/runs")).status_code == 401
        login = await client.post(
            "/api/session", json={"code": os.getenv("LOGIN_CODE", "workplace-demo")}
        )
        login.raise_for_status()
        checks.append("Gateway authentication")
        # Unique future date avoids conflicting with interactive demo reservations.
        when = date(2027, 1, 1) + timedelta(days=uuid.uuid4().int % 10000)
        rid = str(uuid.uuid4())
        body = {
            "message": f"Book a desk near Engineering in Dubai on {when}, check onboarding requirements, and request a monitor.",
            "request_id": rid,
        }
        response = await client.post("/api/runs", json=body)
        response.raise_for_status()
        run = response.json()
        assert run["status"] == "completed", run
        assert {r["tool"] for r in run["tool_results"]} == {
            "search_rooms",
            "reserve_room",
            "create_it_ticket",
            "search_policy",
        }
        repeat = (await client.post("/api/runs", json=body)).json()
        assert repeat["id"] == run["id"]
        checks.append(
            "Real booking + ticket MCP calls + grounded policy + request deduplication"
        )
        access = (
            await client.post(
                "/api/runs",
                json={"message": "Request Dubai floor 3 access for onboarding"},
            )
        ).json()
        assert access["status"] == "awaiting_approval"
        assert not any(r["tool"] == "request_access" for r in access["tool_results"])
        result = (
            await client.post(
                f"/api/runs/{access['id']}/approval", json={"approved": True}
            )
        ).json()
        assert result["status"] == "completed", result
        assert (
            await client.post(
                f"/api/runs/{access['id']}/approval", json={"approved": True}
            )
        ).status_code == 409
        checks.append("Approval gate + durable resume + duplicate decision rejected")
        people = (
            await client.post(
                "/api/runs", json={"message": "Find the Engineering team"}
            )
        ).json()
        assert (
            people["status"] == "completed"
            and len(people["tool_results"][0]["result"]) == 2
        )
        checks.append("REST directory integration")
        reservation = next(
            r["result"]["id"]
            for r in run["tool_results"]
            if r["tool"] == "reserve_room"
        )
        cancel = (
            await client.post(
                "/api/runs", json={"message": "Cancel reservation " + reservation}
            )
        ).json()
        assert cancel["status"] == "awaiting_approval"
        done = (
            await client.post(
                f"/api/runs/{cancel['id']}/approval", json={"approved": True}
            )
        ).json()
        assert done["status"] == "completed"
        checks.append("Owned reservation cancellation through approval + MCP")
        audit = (await client.get("/api/audit")).json()
        assert any(e["event"] == "approval_decided" for e in audit)
        assert "workplace_runs_total" in (await client.get("/api/metrics")).text
        checks.append("Audit and metrics endpoints")
    report = {
        "mode": "real HTTP gateway + MCP + REST, local simulator data",
        "passed": len(checks),
        "checks": checks,
    }
    print(json.dumps(report, indent=2))
    Path(os.getenv("SMOKE_REPORT", "evals/smoke-results.json")).write_text(
        json.dumps(report, indent=2) + "\n"
    )


if __name__ == "__main__":
    asyncio.run(main())
