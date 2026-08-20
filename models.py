from typing import Annotated, Literal
from pydantic import BaseModel, Field


class QueryArgs(BaseModel):
    region: Literal["APAC", "EMEA", "AMER"]
    max_rows: int = Field(default=50, ge=1, le=200) 

class BreachReasonArgs(BaseModel):
    ids: list[Annotated[int, Field(ge=1)]]

class SearchPoliciesArgs(BaseModel):
    question: str = Field(min_length=1)
    k: int = Field(default=4, ge=1, le=8)
# class QueryRecord(BaseModel):
#     id: RecordId | None = None
#     ids: list[RecordId] | None = Field(default=None, min_length=1, max_length=200)
#     max_rows: int = Field(default=50, ge=1, le=200)

# class Aggregate(BaseModel):
#     month: int = Field(default=1, ge=0, le=12)