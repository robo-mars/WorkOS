# MCP integration

Two independent FastMCP services expose tools over Streamable HTTP at `/mcp`. The runtime uses the official SDK to initialize a session, discover tools, validate arguments against their schemas, and invoke tools. Tool schemas are generated from server functions, not reconstructed from a prompt. The checked-in `docs/tool-schemas.json` is a generated snapshot; `tools/list` remains authoritative.

| Server | Tool | Business arguments | Output |
| --- | --- | --- | --- |
| workplace-booking-mcp | search_rooms | date, time, end_time, capacity, building, kind (desk/room), zone | Available resources |
| workplace-booking-mcp | reserve_room | room_id, start_time, end_time | Confirmed reservation |
| workplace-booking-mcp | cancel_reservation | reservation_id | Cancelled reservation |
| it-service-mcp | create_it_ticket | category (hardware/software/network/other), description, priority (low/normal/high) | Open ticket |
| it-service-mcp | get_it_ticket | ticket_id | Owned ticket |
| it-service-mcp | update_it_ticket | ticket_id, status (open/in_progress/resolved) | Updated ticket |

Writes also require runtime-injected `user_id` and `idempotency_key`; ticket reads require the injected user ID. Dates are ISO dates; timestamps are office-local ISO datetimes without offsets. Dubai and London are the seeded offices. Reservations reject overlapping intervals and unknown resource IDs.

Non-MCP tools are `search_employee` (REST directory), `search_policy` (local vector index), and `request_access` (transactional simulator submission). Explicitly keeping these adapters demonstrates a mixed enterprise integration architecture.

MCP makes discovery and schemas standard and lets a different implementation replace a service at the same protocol boundary. An ordinary REST adapter would be simpler for a single fixed endpoint; MCP is worthwhile here because the client discovers two capability groups and owns a common validation, timeout, and invocation path. MCP is not a substitute for authorization or business transactions.

## Unavailable service / invalid arguments

If discovery fails, healthy capabilities remain usable. Invoking an undiscovered capability produces an explicit unavailable error. Calls that fail transiently retry up to three times; repeated failures open a circuit. Schema and business errors are returned without retries. Dependent booking steps are skipped when search fails. Independent IT/policy steps still run.

`tests/test_runtime.py` includes invalid schema, connection outage, timeout, and response-lost-after-commit cases. `scripts/smoke.py` uses actual MCP sessions and tests an invalid argument call through the SDK. See `docs/failure-recovery.md` for a manual outage demonstration.
