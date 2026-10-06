import pytest

from app.agents.planner import RemotePlanner
from app.evaluation.local import LocalRouter
from app.graph.runtime import Runtime
from app.models import Plan, Step
from app.tools.policy import PolicyIndex
from app.tools.router import InvalidArguments, ToolFailure


@pytest.mark.asyncio
async def test_onboarding_end_to_end(runtime, store):
    s = await runtime.start(
        "alice",
        "I start Monday in Dubai. Book a desk near Engineering, check onboarding requirements, and create an IT ticket for a monitor.",
    )
    assert s["status"] == "completed", s["errors"]
    assert s["selected_tools"] == [
        "search_rooms",
        "reserve_room",
        "create_it_ticket",
        "search_policy",
    ]
    assert len(store.list("reservation", "alice")) == 1
    assert len(store.list("ticket", "alice")) == 1
    assert "onboarding.md" in s["final_response"]
    assert store.get(s["id"], "alice")["status"] == "completed"


@pytest.mark.asyncio
async def test_approval_rejection_never_writes(runtime, store):
    s = await runtime.start("alice", "Request Dubai floor 3 access for onboarding")
    assert s["status"] == "awaiting_approval"
    assert not store.list("access")
    rejected = await runtime.approve(s["id"], "alice", False)
    assert rejected["status"] == "rejected" and not store.list("access")


@pytest.mark.asyncio
async def test_approval_survives_runtime_restart(runtime, store, router):
    s = await runtime.start("alice", "Request Dubai floor 3 access for onboarding")
    new_runtime = Runtime(store, router)
    with pytest.raises(ValueError):
        await new_runtime.approve(s["id"], "bob", True)
    done = await new_runtime.approve(s["id"], "alice", True)
    assert done["status"] == "completed" and len(store.list("access", "alice")) == 1
    with pytest.raises(ValueError):
        await new_runtime.approve(s["id"], "alice", True)
    audits = [
        e for e in store.list("audit", "alice") if e["event"] == "approval_decided"
    ]
    assert audits[0]["actor"] == "alice" and audits[0]["approved"] and audits[0]["at"]


@pytest.mark.asyncio
async def test_missing_parameters_are_clarified(runtime):
    s = await runtime.start("a", "Book me a desk")
    assert s["status"] == "needs_input" and not s["tool_results"]
    s = await runtime.start("a", "Request building access")
    assert s["status"] == "needs_input"


@pytest.mark.asyncio
async def test_partial_failure_continues_independent_work(store):
    router = LocalRouter(store, fault={"tool": "search_rooms", "count": 3})
    r = Runtime(store, router)
    s = await r.start(
        "a", "Book a desk in Dubai tomorrow and create an IT ticket for a monitor"
    )
    assert s["status"] == "partial"
    assert len(store.list("ticket", "a")) == 1 and not store.list("reservation")
    assert len([e for e in store.list("audit") if e["event"] == "tool_retry"]) == 3


@pytest.mark.asyncio
async def test_retry_recovers_once_without_duplicate(store):
    router = LocalRouter(store, fault={"tool": "create_it_ticket", "count": 1})
    s = await Runtime(store, router).start("a", "Request a monitor")
    assert s["status"] == "completed" and len(store.list("ticket")) == 1


@pytest.mark.asyncio
async def test_circuit_breaker(store):
    router = LocalRouter(store, fault={"tool": "search_rooms", "count": 9})
    await router.discover()
    args = {"date": "2026-10-12"}
    with pytest.raises(ToolFailure):
        await router.call("search_rooms", args, "a", "run")
    with pytest.raises(ToolFailure, match="circuit open"):
        await router.call("search_rooms", args, "a", "run")
    assert router.injected == 3


@pytest.mark.asyncio
async def test_schema_validation_before_execution(router):
    await router.discover()
    with pytest.raises(InvalidArguments):
        await router.call("create_it_ticket", {"category": "invalid"}, "a", "run")


@pytest.mark.asyncio
async def test_planner_cannot_spoof_identity(store, router):
    class BadPlanner:
        name = "bad"

        async def plan(self, *args):
            return Plan(
                steps=[
                    Step(
                        tool="request_access",
                        specialist="workplace",
                        args={
                            "user_id": "victim",
                            "building": "Dubai",
                            "floor": 3,
                            "reason": "test",
                        },
                    )
                ]
            ), {}

    s = await Runtime(store, router, BadPlanner()).start("a", "Request access")
    assert s["status"] == "failed" and not store.list("access")


@pytest.mark.asyncio
async def test_invalid_dependency_rejected(store, router):
    class BadPlanner:
        name = "bad"

        async def plan(self, *args):
            return Plan(
                steps=[
                    Step(
                        tool="reserve_room",
                        specialist="workplace",
                        args={"room_id": "$2.0.id"},
                        depends_on=[2],
                    )
                ]
            ), {}

    s = await Runtime(store, router, BadPlanner()).start("a", "book")
    assert s["status"] == "failed"


@pytest.mark.asyncio
async def test_preferences_and_conversation_context(runtime, store):
    store.set_preferences("a", {"building": "London", "zone": "Engineering"})
    first = await runtime.start("a", "Book a desk tomorrow")
    second = await runtime.start(
        "a", "What are onboarding requirements?", first["conversation_id"]
    )
    assert first["plan"][0]["args"]["building"] == "London"
    assert second["working_memory"]["recent_turns"] == 1
    assert store.preferences("other") == {}


def test_policy_grounding():
    result = PolicyIndex().search("onboarding requirements first day")
    assert result[0]["source"] == "onboarding.md"
    assert PolicyIndex().search("quantum aardvark zyzzyva") == []


@pytest.mark.asyncio
async def test_provider_failure_fails_closed(store, router, monkeypatch):
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("FALLBACK_LLM_BASE_URL", raising=False)
    s = await Runtime(store, router, RemotePlanner()).start("a", "book a desk tomorrow")
    assert s["status"] == "failed" and not store.list("reservation")


@pytest.mark.asyncio
async def test_empty_search_does_not_invent_resource(runtime, store):
    s = await runtime.start("a", "Book a meeting room in Dubai tomorrow for 99")
    assert s["status"] == "partial" and not store.list("reservation")
    assert "No available resource" in s["final_response"]


@pytest.mark.asyncio
async def test_sensitive_cancellation(runtime, store):
    await runtime.start("a", "Book a desk tomorrow")
    rid = store.list("reservation", "a")[0]["id"]
    pending = await runtime.start("a", "Cancel reservation " + rid)
    assert (
        pending["status"] == "awaiting_approval"
        and store.get(rid)["status"] == "confirmed"
    )
    await runtime.approve(pending["id"], "a", True)
    assert store.get(rid)["status"] == "cancelled"


@pytest.mark.asyncio
async def test_clarification_followup_and_ticket_memory(runtime, store):
    first = await runtime.start("a", "Book a desk")
    followup = await runtime.start("a", "tomorrow", first["conversation_id"])
    assert followup["status"] == "completed"
    ticket = await runtime.start("a", "Request a monitor")
    check = await runtime.start("a", "check it", ticket["conversation_id"])
    assert check["status"] == "completed" and check["selected_tools"] == [
        "get_it_ticket"
    ]


@pytest.mark.asyncio
async def test_policy_question_never_books_or_creates_ticket(runtime, store):
    for question in [
        "What is the desk and meeting room booking policy?",
        "What is the monitor request policy?",
    ]:
        s = await runtime.start("a", question)
        assert s["selected_tools"] == ["search_policy"]
    assert not store.list("ticket") and not store.list("reservation")


@pytest.mark.asyncio
async def test_client_request_id_deduplicates(runtime, store):
    first = await runtime.start("a", "Request a monitor", request_id="stable-request")
    again = await runtime.start("a", "Request a monitor", request_id="stable-request")
    assert first["id"] == again["id"] and len(store.list("ticket")) == 1
    with pytest.raises(ValueError):
        await runtime.start("a", "Request a laptop", request_id="stable-request")


@pytest.mark.asyncio
async def test_retry_preserves_completed_independent_actions(store):
    router = LocalRouter(store, fault={"tool": "search_rooms", "count": 3})
    r = Runtime(store, router)
    first = await r.start("a", "Book a desk tomorrow and request a monitor")
    assert first["status"] == "partial" and len(store.list("ticket")) == 1
    recovered = await Runtime(store, LocalRouter(store)).retry(first["id"], "a")
    assert recovered["status"] == "completed"
    assert len(store.list("ticket")) == 1 and len(store.list("reservation")) == 1


@pytest.mark.asyncio
async def test_timeout_after_commit_replays_same_write(store):
    class UncertainRouter(LocalRouter):
        async def _call(self, tool, args):
            result = await super()._call(tool, args)
            if tool == "create_it_ticket" and not self.injected:
                self.injected += 1
                raise ConnectionError("Response lost after commit")
            return result

    s = await Runtime(store, UncertainRouter(store)).start("a", "Request a monitor")
    assert s["status"] == "completed" and len(store.list("ticket")) == 1


@pytest.mark.asyncio
async def test_provider_malformed_output_uses_fallback(monkeypatch):
    import json

    import httpx

    monkeypatch.setenv("LLM_BASE_URL", "https://primary.example.test/v1")
    monkeypatch.setenv("LLM_MODEL", "primary")
    monkeypatch.setenv("FALLBACK_LLM_BASE_URL", "https://fallback.example.test/v1")
    monkeypatch.setenv("FALLBACK_LLM_MODEL", "fallback")
    requested = []

    def respond(request):
        requested.append(request.url.host)
        content = (
            "not valid JSON"
            if len(requested) == 1
            else json.dumps(
                {
                    "steps": [
                        {
                            "tool": "search_policy",
                            "specialist": "policy",
                            "args": {"query": "onboarding"},
                        }
                    ]
                }
            )
        )
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": content}}],
                "usage": {"total_tokens": 25},
            },
        )

    client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: client(transport=httpx.MockTransport(respond), **kwargs),
    )
    plan, usage = await RemotePlanner().plan("onboarding", {}, [], {})
    assert plan.steps[0].tool == "search_policy" and usage["fallback"]
    assert requested == ["primary.example.test", "fallback.example.test"]


@pytest.mark.asyncio
async def test_tool_timeout_is_bounded(store):
    import asyncio

    class SlowRouter(LocalRouter):
        async def _call(self, *args):
            await asyncio.sleep(1)

    router = SlowRouter(store)
    router.timeout = 0.01
    result = await Runtime(store, router).start("a", "Request a monitor")
    assert result["status"] == "partial" and not store.list("ticket")
    assert len([e for e in store.list("audit") if e["event"] == "tool_retry"]) == 3


@pytest.mark.asyncio
async def test_approval_displays_resolved_arguments(store, router):
    class Planner:
        name = "fixture"

        async def plan(self, *args):
            return Plan(
                steps=[
                    Step(
                        tool="create_it_ticket",
                        specialist="it",
                        args={
                            "category": "hardware",
                            "description": "monitor",
                            "priority": "normal",
                        },
                    ),
                    Step(
                        tool="update_it_ticket",
                        specialist="it",
                        args={"ticket_id": "$0.id", "status": "resolved"},
                        depends_on=[0],
                    ),
                ]
            ), {}

    runtime = Runtime(store, router, Planner())
    state = await runtime.start("a", "Create a monitor ticket and then resolve it")
    assert state["status"] == "awaiting_approval"
    assert state["plan"][1]["args"]["ticket_id"].startswith("create-")
    done = await runtime.approve(state["id"], "a", True)
    assert done["status"] == "completed"
    assert store.list("ticket")[0]["status"] == "resolved"
