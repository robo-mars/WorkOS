from typing import Any, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tool: str
    args: dict[str, Any] = Field(default_factory=dict)
    specialist: Literal["workplace", "it", "policy", "directory"]
    depends_on: list[int] = Field(default_factory=list)


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    steps: list[Step] = Field(default_factory=list, max_length=12)
    clarification: str | None = None


class AgentState(TypedDict, total=False):
    id: str
    user_id: str
    conversation_id: str
    user_request: str
    plan: list[dict]
    selected_tools: list[str]
    tool_results: list[dict]
    working_memory: dict
    persistent_preferences: dict
    approval_required: bool
    approval_status: str
    approved_steps: list[int]
    cursor: int
    errors: list[dict]
    status: str
    final_response: str
    provider: str
    usage: dict
    created_at: str
    updated_at: str
