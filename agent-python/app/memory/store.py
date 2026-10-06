"""JSON documents with transactional writes, ownership checks and durable checkpoints."""

import os
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import (
    JSON,
    Column,
    MetaData,
    String,
    Table,
    create_engine,
    delete,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import StaticPool

metadata = MetaData()
records = Table(
    "records",
    metadata,
    Column("id", String, primary_key=True),
    Column("kind", String, index=True),
    Column("owner", String, index=True),
    Column("data", JSON().with_variant(JSONB(), "postgresql"), nullable=False),
)


def now():
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, url=None):
        url = url or os.getenv("DATABASE_URL", "sqlite:///workplace.db")
        opts = (
            {"connect_args": {"check_same_thread": False}}
            if url.startswith("sqlite")
            else {}
        )
        if url == "sqlite://":
            opts["poolclass"] = StaticPool
        self.engine = create_engine(url, **opts)
        metadata.create_all(self.engine)

    def get(self, key, owner=None):
        with self.engine.connect() as c:
            q = select(records).where(records.c.id == key)
            if owner is not None:
                q = q.where(records.c.owner == owner)
            row = c.execute(q).mappings().first()
            return row["data"] if row else None

    def list(self, kind, owner=None):
        with self.engine.connect() as c:
            q = select(records.c.data).where(records.c.kind == kind)
            if owner is not None:
                q = q.where(records.c.owner == owner)
            return list(c.execute(q).scalars())

    def put(self, key, kind, owner, data):
        with self.engine.begin() as c:
            result = c.execute(
                update(records).where(records.c.id == key).values(data=data)
            )
            if not result.rowcount:
                c.execute(
                    records.insert().values(id=key, kind=kind, owner=owner, data=data)
                )

    def insert(self, key, kind, owner, data):
        try:
            with self.engine.begin() as c:
                c.execute(
                    records.insert().values(id=key, kind=kind, owner=owner, data=data)
                )
            return True
        except IntegrityError:
            return False

    def claim_retry(self, key, owner):
        with self.engine.begin() as c:
            row = (
                c.execute(
                    select(records)
                    .where(records.c.id == key, records.c.owner == owner)
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            if not row or "plan" not in row["data"]:
                return None
            old = row["data"]
            stale = old["status"] == "running" and datetime.fromisoformat(
                old["updated_at"]
            ) < datetime.now(timezone.utc) - timedelta(minutes=5)
            if old["status"] not in {"partial", "failed"} and not stale:
                return None
            if not old["plan"]:
                return None
            new = {**old, "status": "running", "updated_at": now()}
            result = c.execute(
                update(records)
                .where(records.c.id == key, records.c.data == old)
                .values(data=new)
            )
            return new if result.rowcount else None

    def audit(self, owner, event, **details):
        entry = {
            "id": str(uuid.uuid4()),
            "at": now(),
            "actor": owner,
            "event": event,
            **details,
        }
        self.put(entry["id"], "audit", owner, entry)
        return entry

    def claim_approval(self, key, owner):
        # Compare-and-swap the complete checkpoint: concurrent approval requests cannot both win.
        with self.engine.begin() as c:
            row = (
                c.execute(
                    select(records)
                    .where(records.c.id == key, records.c.owner == owner)
                    .with_for_update()
                )
                .mappings()
                .first()
            )
            if not row or row["data"]["status"] != "awaiting_approval":
                return None
            old = row["data"]
            new = {**old, "status": "running"}
            result = c.execute(
                update(records)
                .where(records.c.id == key, records.c.data == old)
                .values(data=new)
            )
            return new if result.rowcount else None

    def preferences(self, user):
        value = self.get("prefs:" + user, user)
        if not value or datetime.fromisoformat(value["expires_at"]) < datetime.now(
            timezone.utc
        ):
            return {}
        return value["values"]

    def set_preferences(self, user, values):
        self.put(
            "prefs:" + user,
            "preferences",
            user,
            {
                "values": values,
                "expires_at": (
                    datetime.now(timezone.utc) + timedelta(days=90)
                ).isoformat(),
            },
        )

    def purge(self, days=7):
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        with self.engine.begin() as c:
            for row in c.execute(
                select(records).where(records.c.kind.in_(["workflow", "audit"]))
            ).mappings():
                if row["data"].get("updated_at", row["data"].get("at", now())) < cutoff:
                    c.execute(delete(records).where(records.c.id == row["id"]))
