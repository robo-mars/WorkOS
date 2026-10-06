import asyncio
import json
import os
import time

import httpx
from jsonschema import validate
from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from app.tools.domain import Domain
from app.tools.policy import PolicyIndex
from app.tools.schemas import LOCAL_MODELS


class ToolFailure(Exception):
    pass


class InvalidArguments(ToolFailure):
    pass


class Router:
    def __init__(self, store, timeout=8, attempts=3):
        self.store = store
        self.domain = Domain(store)
        self.policy = PolicyIndex()
        self.timeout = timeout
        self.attempts = attempts
        self.breakers = {}
        self.schemas = {}
        self.urls = {
            "booking": os.getenv("BOOKING_MCP_URL", "http://127.0.0.1:8001/mcp"),
            "it": os.getenv("IT_MCP_URL", "http://127.0.0.1:8002/mcp"),
        }

    def group(self, tool):
        return (
            "it"
            if tool in {"create_it_ticket", "get_it_ticket", "update_it_ticket"}
            else "booking"
        )

    async def mcp(self, group, tool=None, args=None):
        async with streamablehttp_client(self.urls[group]) as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                if tool is None:
                    return {
                        t.name: {
                            "description": t.description,
                            "inputSchema": t.inputSchema,
                        }
                        for t in (await session.list_tools()).tools
                    }
                result = await session.call_tool(tool, args)
        if result.isError:
            raise InvalidArguments(
                "; ".join(c.text for c in result.content if hasattr(c, "text"))
            )
        if result.structuredContent is not None:
            data = result.structuredContent
            return data["result"] if set(data) == {"result"} else data
        return json.loads(next(c.text for c in result.content if hasattr(c, "text")))

    async def discover(self):
        result = {
            name: {
                "inputSchema": model.model_json_schema(),
                "description": name.replace("_", " "),
            }
            for name, model in LOCAL_MODELS.items()
        }
        for group in self.urls:
            try:
                result.update(await asyncio.wait_for(self.mcp(group), self.timeout))
            except Exception:
                pass  # A missing server cannot hide healthy capabilities.
        self.schemas = result
        return result

    async def call(self, tool, args, user, run_id):
        started = time.monotonic()
        group = "local" if tool in LOCAL_MODELS else self.group(tool)
        failures, until = self.breakers.get(group, (0, 0))
        if until > time.monotonic():
            raise ToolFailure(f"{group} circuit open; try again after cooldown")
        if tool not in self.schemas:
            await self.discover()
        if tool not in self.schemas:
            raise ToolFailure(f"{tool} unavailable: MCP discovery failed")
        try:
            validate(args, self.schemas[tool]["inputSchema"])
        except Exception as e:
            raise InvalidArguments(f"Invalid {tool} arguments: {e.message}") from e
        for attempt in range(1, self.attempts + 1):
            try:
                result = await asyncio.wait_for(self._call(tool, args), self.timeout)
                self.breakers[group] = (0, 0)
                self.store.audit(
                    user,
                    "tool_completed",
                    run_id=run_id,
                    tool=tool,
                    attempt=attempt,
                    duration_ms=round((time.monotonic() - started) * 1000),
                )
                return result
            except InvalidArguments:
                raise
            except (ValueError, httpx.HTTPStatusError) as e:
                raise InvalidArguments(str(e)) from e
            except Exception as e:
                failures += 1
                self.breakers[group] = (
                    failures,
                    time.monotonic() + 20 if failures >= 3 else 0,
                )
                self.store.audit(
                    user,
                    "tool_retry",
                    run_id=run_id,
                    tool=tool,
                    attempt=attempt,
                    error=type(e).__name__,
                )
                if attempt == self.attempts:
                    raise ToolFailure(
                        f"{tool} unavailable after {attempt} attempts"
                    ) from e
                await asyncio.sleep(0.1 * 2 ** (attempt - 1))

    async def _call(self, tool, args):
        if tool == "search_policy":
            return self.policy.search(**args)
        if tool == "request_access":
            return self.domain.mutate(tool, **args)
        if tool == "search_employee":
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                r = await client.get(
                    os.getenv("DIRECTORY_URL", "http://127.0.0.1:8003") + "/employees",
                    params={"q": args["name_or_team"]},
                    headers={
                        "X-Service-Token": os.getenv(
                            "SERVICE_TOKEN", "local-demo-service-token"
                        )
                    },
                )
                r.raise_for_status()
                return r.json()
        return await self.mcp(self.group(tool), tool, args)
