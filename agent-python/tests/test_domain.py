import pytest

from app.memory.store import now
from app.tools.domain import Domain


def reserve(
    domain, user="a", key="one", start="2026-10-12T09:00:00", end="2026-10-12T17:00:00"
):
    return domain.mutate(
        "reserve_room", user, key, room_id="desk-eng-01", start_time=start, end_time=end
    )


def test_idempotency_and_conflicts(store):
    d = Domain(store)
    first = reserve(d)
    assert reserve(d) == first
    assert len(store.list("reservation")) == 1
    with pytest.raises(ValueError, match="already booked"):
        reserve(d, user="b", key="two")
    with pytest.raises(ValueError, match="Idempotency"):
        reserve(d, start="2026-10-12T10:00:00")
    assert reserve(
        d, key="adjacent", start="2026-10-12T17:00:00", end="2026-10-12T18:00:00"
    )


def test_owner_enforcement(store):
    d = Domain(store)
    r = reserve(d)
    with pytest.raises(ValueError, match="not found"):
        d.mutate("cancel_reservation", "other", "cancel", reservation_id=r["id"])
    assert store.get(r["id"], "other") is None
    assert store.get(r["id"], "a")["status"] == "confirmed"


def test_invalid_time(store):
    with pytest.raises(ValueError):
        reserve(Domain(store), start="2026-10-12T17:00:00", end="2026-10-12T09:00:00")


def test_search_excludes_conflicts(store):
    d = Domain(store)
    reserve(d)
    assert "desk-eng-01" not in [r["id"] for r in d.search("2026-10-12")]


def test_retention_and_expiry(store):
    store.put("old", "workflow", "a", {"updated_at": "2020-01-01T00:00:00+00:00"})
    store.put("fresh", "workflow", "a", {"updated_at": now()})
    store.purge()
    assert store.get("old") is None and store.get("fresh")
    store.put(
        "prefs:a",
        "preferences",
        "a",
        {"values": {"building": "London"}, "expires_at": "2020-01-01T00:00:00+00:00"},
    )
    assert store.preferences("a") == {}
