# Reproduce failures and recovery

## Automated

```sh
make test
make eval
```

The tests inject a transient ticket outage (recovered on retry), sustained booking outage (three attempts then a circuit and safe partial completion), tool timeout, invalid tool schema, malformed model output, provider fallback, and a lost response after a committed write. The last case proves that retrying returns the same ticket rather than creating another.

## Live MCP outage (Docker)

1. Start the Compose stack and open the UI.
2. Run `docker compose --env-file .env -f infra/docker-compose.yml stop booking`.
3. Ask: “Book a desk in Dubai tomorrow and request a monitor.”
4. Verify the workflow is partial, search/reservation failed or were skipped, and an IT ticket was created.
5. Restart with `docker compose --env-file .env -f infra/docker-compose.yml start booking`.
6. Wait at least 20 seconds if the booking circuit opened, then click **Retry unfinished steps**.
7. Verify the existing ticket is not duplicated and a reservation is now created.

The same request ID/step ID survives retry. Fresh conversations create distinct requests and can legitimately create new tickets; use the retry control for recovery.

## Approval restart

Ask for Dubai floor 3 access for onboarding. While the card is pending, restart the agent container. Reopen the workflow and approve it. The pending plan and actor decision come from the database. A second decision receives 409; another user cannot approve the workflow.

## Incomplete running workflow

A process crash can leave a workflow marked running. Once it has been idle for five minutes, POST `/api/runs/{id}/retry` to resume the saved plan. This demo intentionally requires an explicit retry rather than a background worker automatically repeating uncertain actions. A durable queue/lease worker is a documented production extension.
