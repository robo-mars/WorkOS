"""Reproducible demo-planner evaluation with in-process, schema-compatible tools.
This is not a measurement of LLM quality or real MCP network latency.
"""

import asyncio
import json
import os
import statistics
import tempfile
import time
from datetime import date
from pathlib import Path

import yaml

from app.agents.planner import DemoPlanner
from app.evaluation.local import LocalRouter
from app.graph.runtime import Runtime
from app.memory.store import Store

ROOT = Path(__file__).resolve().parents[3]


class FixedPlanner(DemoPlanner):
    async def plan(self, text, preferences, context, schemas, today=None):
        return await super().plan(
            text, preferences, context, schemas, date(2026, 10, 7)
        )


async def evaluate():
    rows = []
    for scenario in yaml.safe_load((ROOT / "evals/scenarios.yaml").read_text()):
        store = Store("sqlite://")
        router = LocalRouter(store, scenario.get("fault"))
        runtime = Runtime(store, router, FixedPlanner())
        if scenario.get("preferences"):
            store.set_preferences("eval", scenario["preferences"])
        text = scenario["input"]
        if scenario.get("fixture") == "ticket":
            item = router.domain.mutate(
                "create_it_ticket",
                "eval",
                "fixture",
                category="hardware",
                description="monitor",
                priority="normal",
            )
            text = text.replace("{ticket_id}", item["id"])
        if scenario.get("fixture") == "reservation":
            item = router.domain.mutate(
                "reserve_room",
                "eval",
                "fixture",
                room_id="desk-eng-01",
                start_time="2026-11-01T09:00:00",
                end_time="2026-11-01T17:00:00",
            )
            text = text.replace("{reservation_id}", item["id"])
        start = time.perf_counter()
        state = await runtime.start("eval", text)
        gated = state["status"] == "awaiting_approval"
        preapproval_safe = not store.list("access") and not any(
            r["tool"] in {"cancel_reservation", "update_it_ticket"}
            for r in state["tool_results"]
        )
        if gated and "decision" in scenario:
            state = await runtime.approve(state["id"], "eval", scenario["decision"])
        latency = (time.perf_counter() - start) * 1000
        expected = scenario["expected_tools"]
        actual = state["selected_tools"]
        args_ok = all(
            any(
                step["tool"] == tool
                and all(step["args"].get(k) == v for k, v in args.items())
                for step in state["plan"]
            )
            for tool, args in scenario.get("expected_args", {}).items()
        )
        sources = [
            doc["source"]
            for r in state["tool_results"]
            if r["ok"] and r["tool"] == "search_policy"
            for doc in r["result"]
        ]
        retrieval = all(s in sources for s in scenario.get("expected_sources", []))
        checks = {
            "reservation_created": bool(store.list("reservation")),
            "ticket_created": bool(store.list("ticket")),
            "access_submitted": bool(store.list("access")),
            "no_access": not store.list("access"),
            "no_reservation": not store.list("reservation"),
            "approval_logged": any(
                e["event"] == "approval_decided" for e in store.list("audit")
            ),
            "reservation_cancelled": any(
                r["status"] == "cancelled" for r in store.list("reservation")
            ),
            "reservation_retained": any(
                r["status"] == "confirmed" for r in store.list("reservation")
            ),
        }
        conditions = all(checks[c] for c in scenario.get("success_conditions", []))
        approval_ok = gated == scenario["requires_approval"] and (
            not scenario["requires_approval"] or preapproval_safe
        )
        success = (
            state["status"] == scenario["expected_status"]
            and actual == expected
            and args_ok
            and retrieval
            and conditions
            and approval_ok
        )
        # Deliberately simple single-tool baseline: keeps only first planned tool.
        baseline = (
            actual[:1] == expected
            and len(expected) <= 1
            and not scenario["requires_approval"]
        )
        rows.append(
            {
                "id": scenario["id"],
                "success": success,
                "status": state["status"],
                "expected_status": scenario["expected_status"],
                "tool_selection_exact": actual == expected,
                "argument_accuracy": args_ok,
                "has_argument_assertions": bool(scenario.get("expected_args")),
                "retrieval_correct": retrieval,
                "approval_compliance": approval_ok,
                "unnecessary_tool_calls": sum(t not in expected for t in actual),
                "latency_ms": round(latency, 2),
                "fault_injected": bool(scenario.get("fault")),
                "baseline_plan_match": baseline,
                "errors": state["errors"],
            }
        )
        store.engine.dispose()
    avg = lambda key: round(sum(r[key] for r in rows) / len(rows), 4)
    retrieval_rows = [
        r
        for r, s in zip(
            rows, yaml.safe_load((ROOT / "evals/scenarios.yaml").read_text())
        )
        if s.get("expected_sources")
    ]
    fault_rows = [r for r in rows if r["fault_injected"]]
    argument_rows = [r for r in rows if r["has_argument_assertions"]]
    report = {
        "mode": "deterministic demo planner + in-process tool adapter",
        "scenario_count": len(rows),
        "task_success_rate": avg("success"),
        "tool_selection_exact_accuracy": avg("tool_selection_exact"),
        "tool_argument_case_accuracy": sum(
            r["argument_accuracy"] for r in argument_rows
        )
        / len(argument_rows),
        "argument_cases_checked": len(argument_rows),
        "retrieval_cases_checked": len(retrieval_rows),
        "policy_retrieval_correctness": sum(
            r["retrieval_correct"] for r in retrieval_rows
        )
        / len(retrieval_rows),
        "approval_compliance": avg("approval_compliance"),
        "unnecessary_tool_calls": sum(r["unnecessary_tool_calls"] for r in rows),
        "average_latency_ms": round(statistics.mean(r["latency_ms"] for r in rows), 2),
        "average_tokens": 0,
        "average_model_cost_usd": 0,
        "failure_handling_success_rate": sum(r["success"] for r in fault_rows)
        / len(fault_rows),
        "single_tool_baseline_plan_match": avg("baseline_plan_match"),
        "results": rows,
    }
    (ROOT / "evals/results.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: v for k, v in report.items() if k != "results"}, indent=2))
    failed = [r["id"] for r in rows if not r["success"]]
    if failed:
        print("FAILED:", failed)
    return not failed


if __name__ == "__main__":
    os.environ.setdefault(
        "DATABASE_URL",
        "sqlite:///" + tempfile.mkdtemp(prefix="workplace-eval-") + "/mcp.db",
    )
    raise SystemExit(0 if asyncio.run(evaluate()) else 1)
