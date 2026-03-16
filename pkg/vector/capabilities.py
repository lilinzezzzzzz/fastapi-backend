"""可选能力契约层（Capability Contracts）。

这个模块只定义“可选高级能力”的接口协议，不包含任何业务逻辑或后端实现。
基础 CRUD / search 能力由 `VectorBackend` 负责；当调用方需要高级能力时，
可以通过 `isinstance(backend, SupportsXxx)` 进行能力探测后再调用。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol, runtime_checkable

from pydantic import BaseModel, Field

from pkg.vector.contracts import FilterCondition, SearchHit


class HybridSearchRequest(BaseModel, extra="forbid"):
    """hybrid 检索请求体。

    - `dense_vector`: 稠密向量（通常来自 embedding 模型）
    - `sparse_vector`: 稀疏向量（通常来自 BM25 / SPLADE 等）
    - `top_k`: 返回条数
    - `filters`: 结构化过滤条件
    """

    dense_vector: list[float] | None = None
    sparse_vector: dict[int, float] | None = None
    top_k: int = Field(gt=0)
    filters: list[FilterCondition] = Field(default_factory=list)


@runtime_checkable
class SupportsHybridSearch(Protocol):
    """声明 backend 支持 hybrid 检索。"""

    async def hybrid_search(self, *, collection_name: str, request: HybridSearchRequest) -> list[SearchHit]:
        """执行 hybrid search。"""
        ...


@runtime_checkable
class SupportsNamespaceIsolation(Protocol):
    """声明 backend 支持 namespace / database 级隔离。"""

    async def ensure_namespace(self, *, namespace: str) -> None:
        """准备 namespace / database。"""
        ...


@runtime_checkable
class SupportsBulkImport(Protocol):
    """声明 backend 支持 bulk import。"""

    async def bulk_import(self, *, collection_name: str, rows: Sequence[dict]) -> None:
        """执行 bulk import。"""
        ...


@runtime_checkable
class SupportsLoadControl(Protocol):
    """声明 backend 支持显式加载/释放 collection。"""

    async def load_collection(self, *, collection_name: str) -> None:
        """显式加载 collection。"""
        ...

    async def release_collection(self, *, collection_name: str) -> None:
        """显式释放 collection。"""
        ...
