"""Local enterprise-system simulators. No real corporate data or credentials."""

import hashlib
from datetime import datetime

from sqlalchemy import select, update

from app.memory.store import now, records

RESOURCES = [
    {
        "id": "desk-eng-01",
        "name": "Engineering · D01",
        "kind": "desk",
        "building": "Dubai",
        "zone": "Engineering",
        "capacity": 1,
    },
    {
        "id": "desk-eng-02",
        "name": "Engineering · D02",
        "kind": "desk",
        "building": "Dubai",
        "zone": "Engineering",
        "capacity": 1,
    },
    {
        "id": "desk-quiet-01",
        "name": "Quiet zone · D12",
        "kind": "desk",
        "building": "Dubai",
        "zone": "Quiet",
        "capacity": 1,
    },
    {
        "id": "room-palm",
        "name": "Palm",
        "kind": "room",
        "building": "Dubai",
        "zone": "Engineering",
        "capacity": 8,
    },
    {
        "id": "room-creek",
        "name": "Creek",
        "kind": "room",
        "building": "Dubai",
        "zone": "Central",
        "capacity": 4,
    },
    {
        "id": "desk-london-01",
        "name": "London · D01",
        "kind": "desk",
        "building": "London",
        "zone": "Engineering",
        "capacity": 1,
    },
    {
        "id": "room-thames",
        "name": "Thames",
        "kind": "room",
        "building": "London",
        "zone": "Central",
        "capacity": 10,
    },
]
EMPLOYEES = [
    {
        "id": "e-101",
        "name": "Mariam Hashmi",
        "team": "Engineering",
        "role": "Software Engineer",
        "office": "Dubai",
        "email": "mariam@example.test",
    },
    {
        "id": "e-102",
        "name": "Alex Chen",
        "team": "Engineering",
        "role": "Engineering Manager",
        "office": "Dubai",
        "email": "alex@example.test",
    },
    {
        "id": "e-103",
        "name": "Sara Ahmed",
        "team": "People",
        "role": "People Partner",
        "office": "Dubai",
        "email": "sara@example.test",
    },
    {
        "id": "e-104",
        "name": "James Wilson",
        "team": "IT",
        "role": "IT Support Lead",
        "office": "London",
        "email": "james@example.test",
    },
]


class Domain:
    def __init__(self, store):
        self.store = store
        if not store.get("domain-lock"):
            store.put("domain-lock", "lock", "system", {})

    def search(
        self,
        date,
        time="09:00",
        capacity=1,
        building="Dubai",
        kind="desk",
        zone="",
        end_time="17:00",
    ):
        start = datetime.fromisoformat(f"{date}T{time}")
        end = datetime.fromisoformat(f"{date}T{end_time}")
        if end <= start:
            raise ValueError("End time must follow start time")
        booked = self.store.list("reservation")
        return [
            r
            for r in RESOURCES
            if r["kind"] == kind
            and r["building"].lower() == building.lower()
            and r["capacity"] >= capacity
            and (not zone or zone.lower() in r["zone"].lower())
            and not any(
                b["room_id"] == r["id"]
                and b["status"] == "confirmed"
                and b["start_time"] < end.isoformat()
                and b["end_time"] > start.isoformat()
                for b in booked
            )
        ]

    def mutate(self, tool, user_id, idempotency_key, **args):
        key = (
            "op:"
            + hashlib.sha256(f"{user_id}:{tool}:{idempotency_key}".encode()).hexdigest()
        )
        fingerprint = hashlib.sha256(str(sorted(args.items())).encode()).hexdigest()
        with self.store.engine.begin() as c:
            # Serializes simulator writes on both SQLite and PostgreSQL; suitable for demo load.
            c.execute(
                update(records)
                .where(records.c.id == "domain-lock")
                .values(owner="system")
            )
            cached = c.execute(
                select(records.c.data).where(records.c.id == key)
            ).scalar_one_or_none()
            if cached:
                if cached["fingerprint"] != fingerprint:
                    raise ValueError("Idempotency key reused with different arguments")
                return cached["result"]
            rid = tool.split("_")[0] + "-" + key[3:13]
            if tool == "reserve_room":
                resource = next(
                    (r for r in RESOURCES if r["id"] == args["room_id"]), None
                )
                if not resource:
                    raise ValueError("Unknown resource")
                start = datetime.fromisoformat(args["start_time"])
                end = datetime.fromisoformat(args["end_time"])
                if start.tzinfo or end.tzinfo:
                    raise ValueError("Use local office time without UTC offset")
                if end <= start:
                    raise ValueError("End must follow start")
                args.update(start_time=start.isoformat(), end_time=end.isoformat())
                reservations = c.execute(
                    select(records.c.data).where(records.c.kind == "reservation")
                ).scalars()
                if any(
                    r["room_id"] == args["room_id"]
                    and r["status"] == "confirmed"
                    and r["start_time"] < args["end_time"]
                    and r["end_time"] > args["start_time"]
                    for r in reservations
                ):
                    raise ValueError("Resource already booked; search again")
                result = {
                    "id": rid,
                    **args,
                    "user_id": user_id,
                    "status": "confirmed",
                    "resource": resource,
                }
                kind = "reservation"
            elif tool in ("cancel_reservation", "update_it_ticket"):
                target = args.get("reservation_id", args.get("ticket_id"))
                old = (
                    c.execute(
                        select(records).where(
                            records.c.id == target, records.c.owner == user_id
                        )
                    )
                    .mappings()
                    .first()
                )
                expected = "reservation" if tool == "cancel_reservation" else "ticket"
                if not old or old["kind"] != expected:
                    raise ValueError("Record not found")
                result = {
                    **old["data"],
                    "status": "cancelled"
                    if tool == "cancel_reservation"
                    else args["status"],
                }
                c.execute(
                    update(records).where(records.c.id == target).values(data=result)
                )
                kind = None
            elif tool == "create_it_ticket":
                kind = "ticket"
                result = {
                    "id": rid,
                    **args,
                    "user_id": user_id,
                    "status": "open",
                    "created_at": now(),
                }
            elif tool == "request_access":
                kind = "access"
                result = {
                    "id": rid,
                    **args,
                    "user_id": user_id,
                    "status": "submitted",
                    "note": "Facilities must review; this does not grant access.",
                }
            else:
                raise ValueError("Unsupported mutation")
            if kind:
                c.execute(
                    records.insert().values(
                        id=rid, kind=kind, owner=user_id, data=result
                    )
                )
            c.execute(
                records.insert().values(
                    id=key,
                    kind="idempotency",
                    owner=user_id,
                    data={"fingerprint": fingerprint, "result": result},
                )
            )
            return result
