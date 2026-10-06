from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchPolicy(Strict):
    query: str = Field(min_length=2, max_length=1000)


class SearchEmployee(Strict):
    name_or_team: str = Field(min_length=2, max_length=100)


class Access(Strict):
    building: Literal["Dubai", "London"]
    floor: int = Field(ge=1, le=50)
    reason: str = Field(min_length=3, max_length=1000)
    user_id: str
    idempotency_key: str


LOCAL_MODELS = {
    "search_policy": SearchPolicy,
    "search_employee": SearchEmployee,
    "request_access": Access,
}
GROUPS = {
    "workplace": {
        "search_rooms",
        "reserve_room",
        "cancel_reservation",
        "request_access",
    },
    "it": {"create_it_ticket", "get_it_ticket", "update_it_ticket"},
    "policy": {"search_policy"},
    "directory": {"search_employee"},
}
SENSITIVE = {"request_access", "cancel_reservation", "update_it_ticket"}
WRITES = {"reserve_room", "create_it_ticket", *SENSITIVE}
