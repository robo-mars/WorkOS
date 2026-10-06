.PHONY: install dev test eval build compose
install:
	python3 -m venv .venv
	.venv/bin/pip install -r agent-python/requirements-dev.txt
	cd gateway-go && go mod download
	cd frontend && npm ci
dev:
	.venv/bin/python scripts/dev.py
test:
	PYTHONPATH=agent-python .venv/bin/pytest agent-python/tests -q
	cd gateway-go && go test ./...
eval:
	PYTHONPATH=agent-python .venv/bin/python -m app.evaluation.run
build:
	mkdir -p .run
	cd frontend && npm run build
	cd gateway-go && go build -o ../.run/gateway ./cmd/server
compose:
	docker compose --env-file .env -f infra/docker-compose.yml up --build -d

lint:
	.venv/bin/ruff check agent-python mcp scripts --select F,I
	frontend/node_modules/.bin/prettier --check frontend/src
