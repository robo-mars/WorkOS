# Security and data boundaries

This repository is a local portfolio demo. Do not expose demo login to the public internet.

| Boundary | Control |
| --- | --- |
| Browser → Go | Signed eight-hour HttpOnly session cookie; strict SameSite; configured Origin checks for mutations; 16 KiB body limit; per-IP 60 requests/minute |
| Go → runtime | Server-owned user ID and service token; incoming identity headers overwritten; browser credentials stripped |
| Runtime → tools | Tool allowlist, specialist scope, JSON Schema validation, bounded timeouts/retries |
| Sensitive writes | Explicit step approval, owner check, timestamped audit record, duplicate decision rejected |
| Business records | Reservation/ticket retrieval and mutation scoped to owner; identity is never supplied by model |
| Policy retrieval | Documents treated as data; cited excerpts; no document-driven tool execution |

All demo users share the fixed `demo-employee` identity. The default login code and secrets are public development defaults. Production mode disables demo login rather than pretending to have SSO. A production identity adapter is a required extension. Real corporate integration requires tenant-aware authorization and workload authentication at MCP servers; network isolation is the current service boundary. MCP does not itself make tools safe.

Access approval in this app confirms submission of an access request, not authorization to grant physical access. The simulator records `submitted`; Facilities review is explicitly outside the demo.

## Retention

Conversation requests, plans, and tool results are retained for seven days. The retention worker sweeps hourly, so removal can lag expiry by up to an hour. At planning time, only the five most recent workflows in the same owned conversation are supplied as context. Explicit preferences are used for 90 days; expired values are ignored. The UI allows immediate forgetting of preference values.

Tickets/reservations/access records and operation receipts are business records, not model memory. The simulator retains them until its database is reset or an administrative retention policy is implemented. Audit events currently share the seven-day retention window. This is not a compliance-grade immutable audit log. Local service stdout files are not automatically rotated: configure rotation and retention before deployment.

Do not enter real employee personal data, credentials, identity documents, or confidential policy text into the demo. No messages are automatically promoted to persistent preferences. A stale office preference can produce an inappropriate search; explicitly supplied building/zone details override it.

## Model boundary

`llm` mode sends the current request, explicit preferences, and recent conversation context to the configured provider. This is an intentional data boundary requiring the deploying organization's provider/privacy review. Model output is untrusted and cannot authorize access/cancellation, choose user identity, introduce tools, or bypass ownership. A plan may still misunderstand the user's intent; auto-booking is a documented product choice. Higher-impact deployments should require approval for all writes.

No claim of complete prompt-injection resistance is made. The deterministic planner rejects common bypass phrases and conservatively handles negated actions; the LLM prompt and tool enforcement reduce risk but do not prove semantic correctness.
