import os
from typing import Literal

from app.memory.store import Store
from app.tools.domain import Domain
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "workplace-booking-mcp",
    host=os.getenv("MCP_HOST", "127.0.0.1"),
    port=int(os.getenv("PORT", "8001")),
    stateless_http=True,
    json_response=True,
)
domain = Domain(Store())


@mcp.tool()
def search_rooms(
    date: str,
    time: str = "09:00",
    capacity: int = 1,
    building: str = "Dubai",
    kind: Literal["desk", "room"] = "desk",
    zone: str = "",
    end_time: str = "17:00",
) -> list[dict]:
    """Find available desks or rooms in local office time. Search before reserving."""
    if capacity < 1 or capacity > 100:
        raise ValueError("Capacity must be 1–100")
    return domain.search(date, time, capacity, building, kind, zone, end_time)


@mcp.tool()
def reserve_room(
    room_id: str, user_id: str, start_time: str, end_time: str, idempotency_key: str
) -> dict:
    """Reserve a resource. Requires a stable idempotency key."""
    return domain.mutate(
        "reserve_room",
        user_id,
        idempotency_key,
        room_id=room_id,
        start_time=start_time,
        end_time=end_time,
    )


@mcp.tool()
def cancel_reservation(reservation_id: str, user_id: str, idempotency_key: str) -> dict:
    """Cancel an owned reservation; runtime must collect approval first."""
    return domain.mutate(
        "cancel_reservation", user_id, idempotency_key, reservation_id=reservation_id
    )


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
