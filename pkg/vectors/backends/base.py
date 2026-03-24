from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field

from pkg.vectors.contracts import (
    FilterCondition,
    SearchHit,
    SearchRequest,
    VectorRecord,
)
from pkg.vectors.errors import InvalidEmbeddingDimensionError, RecordValidationError

# =============================================================================
# Collection 名称注册表
# =============================================================================


class CollectionName:
    """向量集合名称注册表。

    集中管理所有向量集合的名称，便于维护和避免硬编码。
    """

    # 默认 collection 名称
    CHUNKS = "chunk_vectors_collection"
    QA_PAIRS = "qa_pair_vectors_collection"


class BackendProvider(StrEnum):
    MILVUS = "milvus"
    ZVEC = "zvec"

    @classmethod
    def is_valid(cls, value: object) -> BackendProvider:
        if isinstance(value, cls):
            return value
        if isinstance(value, str):
            try:
                return cls(value)
            except ValueError as exc:
                raise TypeError(f"非法 backend provider: {value}") from exc
        raise TypeError(f"非法 backend provider: {value!r}")


class ScalarDataType(StrEnum):
    INT64 = "int64"
    FLOAT = "float"
    BOOL = "bool"
    STRING = "string"
    JSON = "json"


class MetricType(StrEnum):
    COSINE = "cosine"
    IP = "ip"
    L2 = "l2"


class ConsistencyLevel(StrEnum):
    STRONG = "Strong"
    SESSION = "Session"
    BOUNDED = "Bounded"
    EVENTUALLY = "Eventually"
    CUSTOMIZED = "Customized"


class TenantIsolationMode(StrEnum):
    """多租户隔离模式。

    定义不同租户数据在向量数据库中的隔离策略。
    """

    SHARED_FILTER = "shared_filter"  # 共享集合，通过 filter 条件隔离租户数据
    NAMESPACE = "namespace"  # 使用 Milvus partition 或 Qdrant namespace 隔离
    COLLECTION_PREFIX = "collection_prefix"  # 每个租户独立集合，集合名加租户前缀


class ScalarFieldSpec(BaseModel, extra="forbid"):
    """标量字段规格定义。

    用于定义集合中除向量字段外的标量元数据字段（如 org_id、doc_id 等）。
    这些字段可用于过滤查询。
    """

    name: str = Field(min_length=1)  # 字段名称
    data_type: ScalarDataType  # 数据类型：INT64, FLOAT, BOOL, STRING, JSON
    nullable: bool = False  # 是否允许为空
    max_length: int | None = Field(default=None, gt=0)  # STRING 类型的最大长度
    filterable: bool = True  # 是否可用于过滤查询
    description: str = ""  # 字段描述


class CollectionSpec(BaseModel, extra="forbid"):
    """向量集合规格定义。

    定义向量数据库集合的完整 schema，包括字段定义、索引配置、租户隔离模式等。
    用于 ensure_collection 时创建或验证集合结构。
    """

    # ========== 基础配置 ==========
    name: str = Field(min_length=1)  # 集合名称
    dimension: int = Field(gt=0)  # 向量维度，必须与 embedding 模型输出维度一致
    metric_type: MetricType = MetricType.COSINE  # 相似度度量类型：COSINE/IP/L2

    # ========== 核心字段名配置 ==========
    id_field: str = "id"  # 主键字段名
    text_field: str = "text"  # 原始文本字段名
    text_max_length: int = Field(default=65_535, gt=0)  # 文本最大长度（VARCHAR）
    vector_field: str = "embedding"  # 向量字段名
    payload_field: str | None = "payload"  # JSON payload 字段名，None 表示不使用

    # ========== 扩展字段配置 ==========
    scalar_fields: list[ScalarFieldSpec] = Field(
        default_factory=list
    )  # 标量元数据字段列表

    # ========== 索引配置 ==========
    # 示例: {"index_type": "HNSW", "metric_type": "COSINE", "params": {"M": 16}}
    index_config: dict[str, Any] = Field(default_factory=dict)

    # ========== 多租户与其他配置 ==========
    tenant_mode: TenantIsolationMode = TenantIsolationMode.SHARED_FILTER  # 租户隔离模式
    consistency_level: ConsistencyLevel = (
        ConsistencyLevel.SESSION
    )  # 默认使用 Session，满足同 client 的读后写一致性
    enable_dynamic_field: bool = False  # 是否启用动态字段（Milvus 特性）
    description: str = ""  # 集合描述


class VectorBackend(ABC):
    @abstractmethod
    async def ensure_collection(self, *, spec: CollectionSpec) -> None:
        """确保 collection 已存在且满足约束。"""

    @abstractmethod
    async def upsert(
        self, *, spec: CollectionSpec, records: Sequence[VectorRecord]
    ) -> None:
        """批量写入记录，必要时自动准备 collection。"""

    @abstractmethod
    async def delete(
        self,
        *,
        spec: CollectionSpec,
        ids: Sequence[int] | None = None,
        filters: Sequence[FilterCondition] | None = None,
    ) -> int:
        """按 id 或过滤条件删除记录；collection 不存在时返回 0。"""

    @abstractmethod
    async def fetch(
        self,
        *,
        spec: CollectionSpec,
        ids: Sequence[int] | None = None,
        filters: Sequence[FilterCondition] | None = None,
        limit: int | None = None,
    ) -> list[VectorRecord]:
        """按 id 或过滤条件获取记录。"""

    @abstractmethod
    async def search(
        self, *, spec: CollectionSpec, request: SearchRequest
    ) -> list[SearchHit]:
        """执行向量检索。"""

    @abstractmethod
    async def healthcheck(self) -> dict[str, str]:
        """返回 backend 健康状态。"""


class BaseVectorBackend(VectorBackend):
    @staticmethod
    def validate_record(*, spec: CollectionSpec, record: VectorRecord) -> None:
        if record.id <= 0:
            raise RecordValidationError("record.id 必须为正整数")
        if record.embedding is None:
            raise RecordValidationError(f"record.embedding 不能为空: id={record.id}")
        if len(record.embedding) != spec.dimension:
            raise InvalidEmbeddingDimensionError(
                f"record embedding 维度不匹配: got={len(record.embedding)}, expected={spec.dimension}, id={record.id}"
            )

    def validate_records(
        self, *, spec: CollectionSpec, records: Sequence[VectorRecord]
    ) -> None:
        for record in records:
            self.validate_record(spec=spec, record=record)

    @staticmethod
    def validate_search_request(
        *, spec: CollectionSpec, request: SearchRequest
    ) -> None:
        if len(request.vector) != spec.dimension:
            raise InvalidEmbeddingDimensionError(
                f"query embedding 维度不匹配: got={len(request.vector)}, expected={spec.dimension}"
            )


def scalar_field_names(*, spec: CollectionSpec) -> list[str]:
    return [field.name for field in spec.scalar_fields]
