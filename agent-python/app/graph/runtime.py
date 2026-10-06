import copy
import logging
import os
import uuid
from datetime import datetime
from zoneinfo import ZoneInfo

from langgraph.graph import END, START, StateGraph

from app.agents.planner import DemoPlanner, RemotePlanner
from app.agents.specialists import Specialist
from app.memory.store import now
from app.models import AgentState
from app.tools.schemas import GROUPS, SENSITIVE, WRITES

log = logging.getLogger("workplace.runtime")


class Runtime:
    def __init__(self, store, router, planner=None):
        self.store = store
        self.router = router
        self.planner = planner or (
            RemotePlanner() if os.getenv("PLANNER_MODE") == "llm" else DemoPlanner()
        )
        self.specialists = {k: Specialist(k, router) for k in GROUPS}
        graph = StateGraph(AgentState)
        graph.add_node("supervisor", self.plan)
        graph.add_node("approval", self.gate)
        for name in GROUPS:
            graph.add_node(name, self.execute)
        graph.add_node("evaluator", self.synthesize)
        graph.add_conditional_edges(
            START,
            lambda s: "approval" if s.get("plan") else "supervisor",
            {"approval": "approval", "supervisor": "supervisor"},
        )
        graph.add_edge("supervisor", "approval")
        graph.add_conditional_edges(
            "approval", self.route, {k: k for k in [*GROUPS, "evaluator"]}
        )
        for name in GROUPS:
            graph.add_edge(name, "approval")
        graph.add_edge("evaluator", END)
        self.graph = graph.compile()

    def save(self, s):
        s["updated_at"] = now()
        self.store.put(s["id"], "workflow", s["user_id"], dict(s))

    async def start(self, user, text, conversation_id=None, request_id=None):
        s = AgentState(
            id=str(uuid.uuid5(uuid.NAMESPACE_URL, user + ":" + request_id))
            if request_id
            else str(uuid.uuid4()),
            user_id=user,
            conversation_id=conversation_id or str(uuid.uuid4()),
            user_request=text,
            plan=[],
            selected_tools=[],
            tool_results=[],
            working_memory={},
            persistent_preferences=self.store.preferences(user),
            approval_required=False,
            approval_status="not_required",
            approved_steps=[],
            cursor=0,
            errors=[],
            status="running",
            final_response="",
            provider=self.planner.name,
            usage={},
            created_at=now(),
        )
        s["updated_at"] = now()
        if not self.store.insert(s["id"], "workflow", user, dict(s)):
            existing = self.store.get(s["id"], user)
            if existing["user_request"] != text:
                raise ValueError("Request ID already used for a different message")
            return existing
        return await self.graph.ainvoke(s, {"recursion_limit": 60})

    async def plan(self, s):
        schemas = await self.router.discover()
        recent = sorted(
            [
                w
                for w in self.store.list("workflow", s["user_id"])
                if w["conversation_id"] == s["conversation_id"] and w["id"] != s["id"]
            ],
            key=lambda w: w["created_at"],
        )[-5:]
        context = [
            {
                "request": w["user_request"],
                "results": w["tool_results"],
                "status": w["status"],
            }
            for w in recent
        ]
        try:
            plan, usage = await self.planner.plan(
                s["user_request"],
                s["persistent_preferences"],
                context,
                schemas,
                datetime.now(ZoneInfo("Asia/Dubai")).date(),
            )
            for i, step in enumerate(plan.steps):
                if step.tool not in GROUPS[step.specialist]:
                    raise ValueError("Invalid specialist/tool mapping")
                if any(d < 0 or d >= i for d in step.depends_on):
                    raise ValueError("Dependencies must reference earlier steps")
                if any(k in step.args for k in ["user_id", "idempotency_key"]):
                    raise ValueError(
                        "Planner cannot choose identity or idempotency key"
                    )
                for value in step.args.values():
                    if isinstance(value, str) and value.startswith("$"):
                        ref = int(value[1:].split(".")[0])
                        if ref not in step.depends_on:
                            raise ValueError(
                                "Reference must be declared as a dependency"
                            )
                if step.tool == "reserve_room" and not any(
                    plan.steps[d].tool == "search_rooms" for d in step.depends_on
                ):
                    raise ValueError("Reservation requires availability search")
            if plan.clarification:
                s["plan"] = []
                s["status"] = "needs_input"
                s["final_response"] = plan.clarification
            else:
                s["plan"] = [step.model_dump() for step in plan.steps]
                s["selected_tools"] = [step.tool for step in plan.steps]
            s["usage"] = usage
            s["working_memory"] = {"recent_turns": len(context)}
            self.store.audit(
                s["user_id"],
                "plan_created",
                run_id=s["id"],
                tools=s["selected_tools"],
                provider=s["provider"],
            )
        except Exception as e:
            s["errors"].append({"phase": "planner", "message": str(e)[:500]})
            s["status"] = "failed"
            s["final_response"] = (
                "I could not validate a safe plan. Please provide the date, location, and task details and try again."
            )
        self.save(s)
        return s

    async def gate(self, s):
        if s["status"] in {"needs_input", "failed", "rejected"}:
            return s
        if s["cursor"] >= len(s["plan"]):
            s["status"] = "partial" if s["errors"] else "completed"
        else:
            tool = s["plan"][s["cursor"]]["tool"]
            if tool in SENSITIVE and s["cursor"] not in s["approved_steps"]:
                # Freeze resolved business arguments before showing an approval card.
                # The eventual action must match the concrete values the employee saw.
                step = s["plan"][s["cursor"]]
                try:
                    step["args"] = self.resolve(step["args"], s)
                except ValueError as exc:
                    error = {"step": s["cursor"], "tool": tool, "message": str(exc)}
                    s["errors"].append(error)
                    s["tool_results"].append(
                        {
                            "step": s["cursor"],
                            "tool": tool,
                            "ok": False,
                            "error": str(exc),
                        }
                    )
                    self.store.audit(
                        s["user_id"],
                        "tool_failed",
                        run_id=s["id"],
                        tool=tool,
                        error=str(exc),
                    )
                    s["cursor"] += 1
                    self.save(s)
                    return await self.gate(s)
                s["status"] = "awaiting_approval"
                s["approval_required"] = True
                s["approval_status"] = "pending"
                s["final_response"] = (
                    "Please review and approve the pending action. No sensitive action has been executed."
                )
                self.store.audit(
                    s["user_id"],
                    "approval_requested",
                    run_id=s["id"],
                    step=s["cursor"],
                    tool=tool,
                )
        self.save(s)
        return s

    def route(self, s):
        if s["status"] != "running":
            return "evaluator"
        return s["plan"][s["cursor"]]["specialist"]

    def resolve(self, args, s):
        result = copy.deepcopy(args)
        for key, value in result.items():
            if isinstance(value, str) and value.startswith("$"):
                parts = value[1:].split(".")
                step = int(parts.pop(0))
                source = next(
                    (r for r in s["tool_results"] if r["step"] == step and r["ok"]),
                    None,
                )
                if source is None:
                    raise ValueError("Dependency did not succeed")
                value = source["result"]
                try:
                    for part in parts:
                        value = (
                            value[int(part)] if isinstance(value, list) else value[part]
                        )
                except (IndexError, KeyError, TypeError):
                    raise ValueError(
                        "No available resource matched the search; adjust location, date, or capacity"
                    )
                result[key] = value
        return result

    async def execute(self, s):
        index = s["cursor"]
        step = s["plan"][index]
        tool = step["tool"]
        if any(r["step"] == index and r["ok"] for r in s["tool_results"]):
            s["cursor"] += 1
            self.save(s)
            return s
        try:
            if tool in SENSITIVE and index not in s["approved_steps"]:
                raise ValueError("Approval is required")
            if any(
                not any(r["step"] == d and r["ok"] for r in s["tool_results"])
                for d in step["depends_on"]
            ):
                raise ValueError("Skipped because a required step failed")
            args = self.resolve(step["args"], s)
            if tool in WRITES or tool == "get_it_ticket":
                args["user_id"] = s["user_id"]
            if tool in WRITES:
                args["idempotency_key"] = f"{s['id']}:{index}"
            result = await self.specialists[step["specialist"]].execute(
                tool, args, s["user_id"], s["id"]
            )
            s["tool_results"].append(
                {
                    "step": index,
                    "tool": tool,
                    "specialist": step["specialist"],
                    "ok": True,
                    "args": args,
                    "result": result,
                }
            )
        except Exception as e:
            error = {"step": index, "tool": tool, "message": str(e)[:500]}
            s["errors"].append(error)
            s["tool_results"].append(
                {"step": index, "tool": tool, "ok": False, "error": error["message"]}
            )
            self.store.audit(
                s["user_id"],
                "tool_failed",
                run_id=s["id"],
                tool=tool,
                error=error["message"],
            )
        s["cursor"] += 1
        self.save(s)
        return s

    async def synthesize(self, s):
        if s["status"] not in {"completed", "partial"}:
            self.save(s)
            return s
        lines = []
        for r in s["tool_results"]:
            if not r["ok"]:
                lines.append(
                    f"Could not complete {r['tool'].replace('_', ' ')}: {r['error']}"
                )
                continue
            data = r["result"]
            tool = r["tool"]
            if tool == "reserve_room":
                lines.append(
                    f"Booked {data['resource']['name']} in {data['resource']['building']} from {data['start_time']} to {data['end_time']} (local time). Reservation: {data['id']}."
                )
            elif tool == "create_it_ticket":
                lines.append(
                    f"Created {data['category']} support ticket {data['id']} · {data['priority']} priority · {data['status']}."
                )
            elif tool in {"get_it_ticket", "update_it_ticket", "cancel_reservation"}:
                lines.append(f"{data['id']}: {data['status']}.")
            elif tool == "request_access":
                lines.append(
                    f"Access request {data['id']} submitted for {data['building']}, floor {data['floor']}. Facilities review is still required; access has not been granted."
                )
            elif tool == "search_policy":
                lines.extend(
                    [
                        f"{d['title']}: {d['text'].split(chr(10), 2)[-1].strip()} [Source: {d['source']}]"
                        for d in data[:2]
                    ]
                )
                if not data:
                    lines.append(
                        "No relevant policy was found. Ask People Operations for guidance."
                    )
            elif tool == "search_employee":
                lines.extend(
                    [
                        f"{e['name']} · {e['role']} · {e['team']} · {e['office']} · {e['email']}"
                        for e in data
                    ]
                )
            elif tool == "search_rooms" and not any(
                x["tool"] == "reserve_room" for x in s["plan"]
            ):
                lines.append(
                    "Available: " + ", ".join(d["name"] for d in data)
                    if data
                    else "No resources matched your search."
                )
        s["final_response"] = "\n\n".join(lines) or "No matching results were found."
        self.save(s)
        return s

    async def approve(self, run_id, user, approved):
        s = self.store.claim_approval(run_id, user)
        if s is None:
            raise ValueError("Workflow not found or no longer awaiting approval")
        self.store.audit(
            user, "approval_decided", run_id=run_id, step=s["cursor"], approved=approved
        )
        s["approval_status"] = "approved" if approved else "rejected"
        if not approved:
            s["status"] = "rejected"
            s["final_response"] = (
                "The pending action was rejected. Earlier completed actions remain in place."
            )
            self.save(s)
            return s
        s["approved_steps"].append(s["cursor"])
        s["status"] = "running"
        self.save(s)
        return await self.graph.ainvoke(s, {"recursion_limit": 60})

    async def retry(self, run_id, user):
        s = self.store.claim_retry(run_id, user)
        if s is None:
            raise ValueError(
                "Retry requires a partial/failed workflow, or a running workflow idle for five minutes"
            )
        self.store.audit(
            user, "workflow_retried", run_id=run_id, previous_errors=s["errors"]
        )
        s["errors"] = []
        s["tool_results"] = [r for r in s["tool_results"] if r["ok"]]
        s["cursor"] = 0
        s["final_response"] = ""
        self.save(s)
        return await self.graph.ainvoke(s, {"recursion_limit": 60})
