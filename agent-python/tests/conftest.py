import os
import tempfile

# Isolate the module-level MCP server databases created while collecting their schemas.
os.environ["DATABASE_URL"] = (
    "sqlite:///" + tempfile.mkdtemp(prefix="workplace-tests-") + "/mcp.db"
)
import pytest

from app.evaluation.local import LocalRouter
from app.graph.runtime import Runtime
from app.memory.store import Store


@pytest.fixture
def store():
    return Store("sqlite://")


@pytest.fixture
def router(store):
    return LocalRouter(store)


@pytest.fixture
def runtime(store, router):
    return Runtime(store, router)
