import os
from typing import Literal

from app.memory.store import Store
from app.tools.domain import Domain
from mcp.server.fastmcp import FastMCP

mcp = FastMCP(
    "it-service-mcp",
    host=os.getenv("MCP_HOST", "127.0.0.1"),
    port=int(os.getenv("PORT", "8002")),
    stateless_http=True,
    json_response=True,
)
store = Store()
domain = Domain(store)


@mcp.tool()
def create_it_ticket(
    category: Literal["hardware", "software", "network", "other"],
    description: str,
    priority: Literal["low", "normal", "high"],
    user_id: str,
    idempotency_key: str,
) -> dict:
    """Create an IT support ticket; never put secrets in the description."""
    if not 3 <= len(description) <= 2000:
        raise ValueError("Description must be 3–2000 characters")
    return domain.mutate(
        "create_it_ticket",
        user_id,
        idempotency_key,
        category=category,
        description=description,
        priority=priority,
    )


@mcp.tool()
def get_it_ticket(ticket_id: str, user_id: str) -> dict:
    """Read the current employee's ticket."""
    ticket = store.get(ticket_id, user_id)
    if not ticket or "category" not in ticket:
        raise ValueError("Ticket not found")
    return ticket


@mcp.tool()
def update_it_ticket(
    ticket_id: str,
    status: Literal["open", "in_progress", "resolved"],
    user_id: str,
    idempotency_key: str,
) -> dict:
    """Update an owned support ticket; runtime requires confirmation."""
    return domain.mutate(
        "update_it_ticket", user_id, idempotency_key, ticket_id=ticket_id, status=status
    )


if __name__ == "__main__":
    mcp.run(transport="streamable-http")
