from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

type ScalarValue = str | int | float | bool


class FilterOperator(StrEnum):
    EQ = "eq"
    NE = "ne"
    IN = "in"
    LT = "lt"
    LTE = "lte"
    GT = "gt"
    GTE = "gte"


class FilterCondition(BaseModel, extra="forbid"):
    field: str = Field(min_length=1)
    op: FilterOperator
    value: ScalarValue | list[ScalarValue]


class VectorRecord(BaseModel, extra="forbid"):
    id: str = Field(min_length=1)
    text: str
    embedding: list[float] | None = None
    metadata: dict[str, ScalarValue] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)


class SearchRequest(BaseModel, extra="forbid"):
    vector: list[float]
    top_k: int = Field(gt=0)
    filters: list[FilterCondition] = Field(default_factory=list)
    include_payload: bool = False
    output_fields: list[str] = Field(default_factory=list)
    search_params: dict[str, Any] = Field(default_factory=dict)


class SearchHit(BaseModel, extra="forbid"):
    id: str
    text: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)
    relevance_score: float | None = None
    raw_score: float | None = None
