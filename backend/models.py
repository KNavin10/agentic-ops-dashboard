from typing import Annotated, Literal
from pydantic import BaseModel, Field


class QueryArgs(BaseModel):
    region: Literal["APAC", "EMEA", "AMER"]
    max_rows: int = Field(default=50, ge=1, le=200)

class BreachReasonArgs(BaseModel):
    ids: list[Annotated[int, Field(ge=1)]] = Field(min_length=1)

class SearchPoliciesArgs(BaseModel):
    question: str = Field(min_length=1)
    k: int = Field(default=4, ge=1, le=8)

class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)
    approve_sensitive: bool = False

class AskResponse(BaseModel):
    status: str
    answer: str | None = None
    trace: list[dict] = Field(default_factory=list)
    rows: list[dict] = Field(default_factory=list)
    approval: dict | None = None
    tokens: int = 0
