"""In-process test adapter, never selected by the application.
Schemas come from the real MCP server decorators; production uses HTTP MCP.
"""

import importlib.util
from pathlib import Path

from app.tools.domain import EMPLOYEES
from app.tools.router import Router
from app.tools.schemas import LOCAL_MODELS


class LocalRouter(Router):
    def __init__(self, store, fault=None):
        super().__init__(store, timeout=0.2)
        self.fault = fault
        self.injected = 0

    async def discover(self):
        schemas = {
            n: {"inputSchema": m.model_json_schema(), "description": n}
            for n, m in LOCAL_MODELS.items()
        }
        root = Path(__file__).resolve().parents[3]
        for name in ["workplace-booking", "it-service"]:
            spec = importlib.util.spec_from_file_location(
                name, root / "mcp" / name / "server.py"
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            schemas.update(
                {
                    t.name: {"inputSchema": t.inputSchema, "description": t.description}
                    for t in await module.mcp.list_tools()
                }
            )
        self.schemas = schemas
        return schemas

    async def _call(self, tool, args):
        if (
            self.fault
            and self.fault["tool"] == tool
            and self.injected < self.fault.get("count", 1)
        ):
            self.injected += 1
            raise ConnectionError("Injected downstream outage")
        args = dict(args)
        if tool == "search_rooms":
            return self.domain.search(**args)
        if tool in {
            "reserve_room",
            "cancel_reservation",
            "create_it_ticket",
            "update_it_ticket",
            "request_access",
        }:
            return self.domain.mutate(tool, **args)
        if tool == "get_it_ticket":
            result = self.store.get(args["ticket_id"], args["user_id"])
            if result is None:
                raise ValueError("Ticket not found")
            return result
        if tool == "search_employee":
            return [
                e
                for e in EMPLOYEES
                if args["name_or_team"].lower() in (e["name"] + " " + e["team"]).lower()
            ]
        return await super()._call(tool, args)
