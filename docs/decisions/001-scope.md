# ADR 001: A small enterprise agent with inspectable boundaries

Status: accepted.

Use Go at the public HTTP boundary and Python for agent orchestration. Gin provides straightforward middleware and proxy composition; Python provides first-class LangGraph/MCP integrations and typed planning. Keeping the runtime private makes identity forwarding explicit.

Use one LangGraph with a supervisor and scoped execution specialists, rather than separate conversational agents. This gives each domain a narrow capability boundary without repeated planning or recursive delegation. The specialists execute deterministic tools; only the supervisor optionally calls a model.

Use official MCP services for booking and IT, REST for directory, and a local TF-IDF vector index for the tiny policy corpus. MCP is a protocol demonstration; the enterprise backends are explicitly simulators. Avoid external account setup and embedding dependencies for a reproducible portfolio demo.

Use PostgreSQL in Compose, SQLite locally, and a JSON document table with transactional ownership/idempotency. Application checkpoints keep resume behavior visible in the code. The globally serialized simulator lock and full document scans are intentionally small-data choices, not scalable architecture claims.

Do not add Redis before it solves a measured problem. Keep rate limiting and circuit counters process-local and document that replicas require a shared coordination store. Do not claim immutable auditing, enterprise SSO, distributed tracing, or real model accuracy where these are not implemented.
