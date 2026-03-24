from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, model_validator

type ScalarValue = str | int | float | bool
type VectorRecordId = int


class FilterOperator(StrEnum):
    EQ = "eq"
    NE = "ne"
    IN = "in"
    LT = "lt"
    LTE = "lte"
    GT = "gt"
    GTE = "gte"


class ConsistencyLevel(StrEnum):
    STRONG = "Strong"
    BOUNDED = "Bounded"
    SESSION = "Session"
    EVENTUAL = "Eventual"


class RetrievalMode(StrEnum):
    AUTO = "auto"
    DENSE = "dense"
    FULL_TEXT = "full_text"
    HYBRID = "hybrid"


class RerankerStrategy(StrEnum):
    RRF = "rrf"
    WEIGHTED = "weighted"


class FilterCondition(BaseModel, extra="forbid"):
    field: str = Field(min_length=1)
    op: FilterOperator
    value: ScalarValue | list[ScalarValue]


class VectorRecord(BaseModel, extra="forbid"):
    id: VectorRecordId = Field(gt=0)
    text: str
    embedding: list[float] | None = None
    metadata: dict[str, ScalarValue] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)


class SearchReranker(BaseModel, extra="forbid"):
    strategy: RerankerStrategy = RerankerStrategy.RRF
    k: int = Field(default=60, gt=0)
    weights: list[float] = Field(default_factory=list)
    normalize_score: bool = True

    @model_validator(mode="after")
    def validate_strategy_params(self) -> SearchReranker:
        if self.strategy == RerankerStrategy.RRF and self.weights:
            raise ValueError("RRF reranker 不支持 weights")
        if self.strategy == RerankerStrategy.WEIGHTED and not self.weights:
            raise ValueError("Weighted reranker 需要提供 weights")
        return self


class SearchRequest(BaseModel, extra="forbid"):
    vector: list[float] | None = None
    query_text: str | None = Field(default=None, min_length=1)
    top_k: int = Field(gt=0)
    filters: list[FilterCondition] = Field(default_factory=list)
    include_payload: bool = False
    output_fields: list[str] = Field(default_factory=list)
    search_params: dict[str, Any] = Field(default_factory=dict)
    sparse_search_params: dict[str, Any] = Field(default_factory=dict)
    retrieval_mode: RetrievalMode = RetrievalMode.AUTO
    candidate_top_k: int | None = Field(default=None, gt=0)
    reranker: SearchReranker | None = None
    consistency_level: ConsistencyLevel | None = None

    @model_validator(mode="after")
    def validate_retrieval_inputs(self) -> SearchRequest:
        if self.retrieval_mode in {RetrievalMode.DENSE, RetrievalMode.HYBRID} and self.vector is None:
            raise ValueError(f"{self.retrieval_mode.value} 检索需要 query vector")
        if self.retrieval_mode in {RetrievalMode.FULL_TEXT, RetrievalMode.HYBRID} and not self.query_text:
            raise ValueError(f"{self.retrieval_mode.value} 检索需要 query_text")
        if self.retrieval_mode == RetrievalMode.AUTO and self.vector is None and not self.query_text:
            raise ValueError("至少需要提供 query vector 或 query_text")
        return self


class SearchHit(BaseModel, extra="forbid"):
    id: VectorRecordId = Field(gt=0)
    text: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    payload: dict[str, Any] = Field(default_factory=dict)
    retrieval_mode: RetrievalMode | None = None
    relevance_score: float | None = None
    raw_score: float | None = None
