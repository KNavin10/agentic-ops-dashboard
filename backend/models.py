import re
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid")


class QueryArgs(ToolArguments):
    region: Literal["APAC", "EMEA", "AMER"]
    max_rows: int = Field(default=50, ge=1, le=200)

class BreachReasonArgs(ToolArguments):
    ids: list[Annotated[int, Field(ge=1)]] = Field(min_length=1)

class SearchPoliciesArgs(ToolArguments):
    question: str = Field(min_length=1)
    k: int = Field(default=4, ge=1, le=8)

class EmailSummaryArgs(ToolArguments):
    recipient: str = Field(min_length=3, max_length=320)
    subject: str = Field(min_length=1, max_length=200)
    body: str = Field(min_length=1, max_length=5000)

    @field_validator("recipient")
    @classmethod
    def valid_email(cls, value: str) -> str:
        if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", value):
            raise ValueError("recipient must be a valid email address")
        return value


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=1, max_length=500)


class ApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "decline"]

class AskResponse(BaseModel):
    model_config = ConfigDict(extra="allow")
    status: str
    answer: str | None = None
    trace: list[dict] = Field(default_factory=list)
    rows: list[dict] = Field(default_factory=list)
    approval: dict | None = None
    tokens: int = 0
    request_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    cost_usd: float | None = None
    latency_ms: int | None = None
    cached: bool | None = None
