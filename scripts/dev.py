"""Start all local services; Ctrl-C terminates the complete process group."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.chdir(ROOT)
run = ROOT / ".run"
run.mkdir(exist_ok=True)
env = {
    **os.environ,
    "PYTHONPATH": str(ROOT / "agent-python"),
    "DATABASE_URL": "sqlite:///" + str(run / "workplace.db"),
    "DEMO_MODE": "true",
    "LOGIN_CODE": os.getenv("LOGIN_CODE", "workplace-demo"),
    "SESSION_SECRET": os.getenv(
        "SESSION_SECRET", "local-demo-session-secret-change-before-deploying"
    ),
    "SERVICE_TOKEN": os.getenv("SERVICE_TOKEN", "local-demo-service-token"),
    "WEB_ORIGIN": "http://localhost:5173",
}
python = str(ROOT / ".venv/bin/python")
subprocess.run(
    [
        python,
        "-c",
        "from app.memory.store import Store; from app.tools.domain import Domain; Domain(Store())",
    ],
    env=env,
    check=True,
)
commands = [
    ("booking", [python, "mcp/workplace-booking/server.py"], ROOT),
    ("it", [python, "mcp/it-service/server.py"], ROOT),
    (
        "directory",
        [
            python,
            "-m",
            "uvicorn",
            "app.directory:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8003",
        ],
        ROOT,
    ),
    (
        "agent",
        [
            python,
            "-m",
            "uvicorn",
            "app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            "8000",
        ],
        ROOT,
    ),
    ("retention", [python, "scripts/retention.py"], ROOT),
    ("gateway", ["go", "run", "./cmd/server"], ROOT / "gateway-go"),
    (
        "web",
        ["npm", "run", "dev", "--", "--port", "5173", "--strictPort"],
        ROOT / "frontend",
    ),
]
processes = []


def stop(*_):
    for p in processes:
        try:
            os.killpg(p.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    for p in processes:
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
    sys.exit(0)


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)
for name, command, cwd in commands:
    log = open(run / (name + ".log"), "w")
    processes.append(
        subprocess.Popen(
            command, cwd=cwd, env=env, stdout=log, stderr=log, start_new_session=True
        )
    )
    log.close()
print(
    "WorkplaceOS starting at http://localhost:5173 · demo code: "
    + env["LOGIN_CODE"]
    + " · logs: .run/",
    flush=True,
)
while True:
    time.sleep(1)
    for (name, _, _), p in zip(commands, processes):
        if p.poll() is not None:
            print(f"{name} exited ({p.returncode}). See .run/{name}.log", flush=True)
            stop()
