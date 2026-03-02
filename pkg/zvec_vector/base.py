"""
Zvec 向量数据库操作基类

参考文档: https://zvec.org/en/docs/quickstart/

注意：
- zvec 本身是同步库，异步方法通过 anyio.to_thread.run_sync() 实现
- zvec 是嵌入式数据库，不支持连接池
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Self

import anyio
import zvec
from zvec import Collection, CollectionOption, CollectionSchema, Doc


class VectorMetricType(StrEnum):
    """向量相似度度量类型"""

    COSINE = "COSINE"
    L2 = "L2"
    IP = "IP"  # Inner Product


class VectorDataType(StrEnum):
    """向量数据类型"""

    FP32 = "VECTOR_FP32"
    FP16 = "VECTOR_FP16"
    SPARSE_FP32 = "SPARSE_VECTOR_FP32"
    SPARSE_FP16 = "SPARSE_VECTOR_FP16"


class IndexType(StrEnum):
    """索引类型"""

    FLAT = "FLAT"
    HNSW = "HNSW"
    IVF = "IVF"


@dataclass
class VectorFieldConfig:
    """向量字段配置"""

    name: str
    dimension: int
    data_type: VectorDataType = VectorDataType.FP32
    metric_type: VectorMetricType = VectorMetricType.COSINE
    index_type: IndexType = IndexType.FLAT
    quantize_type: str | None = None


@dataclass
class ScalarFieldConfig:
    """标量字段配置"""

    name: str
    data_type: str  # INT64, STRING, DOUBLE, BOOL, etc.
    nullable: bool = False
    indexed: bool = False


@dataclass
class CollectionConfig:
    """集合配置"""

    name: str
    path: str
    vector_fields: list[VectorFieldConfig] = field(default_factory=list)
    scalar_fields: list[ScalarFieldConfig] = field(default_factory=list)
    read_only: bool = False
    enable_mmap: bool = True


@dataclass
class SearchResult:
    """搜索结果"""

    id: str
    score: float
    fields: dict[str, Any] = field(default_factory=dict)
    vectors: dict[str, list[float]] = field(default_factory=dict)

    @classmethod
    def from_doc(cls, doc: Doc) -> Self:
        """从 Zvec Doc 转换为 SearchResult"""
        return cls(
            id=doc.id,
            score=doc.score or 0.0,
            fields=doc.fields or {},
            vectors={name: doc.vector(name) for name in doc.vector_names()} if doc.vectors else {},
        )


@dataclass
class SearchParams:
    """搜索参数"""

    vector: list[float]
    vector_field: str = "embedding"
    top_k: int = 10
    filter_expr: str | None = None
    include_vectors: bool = False
    include_fields: list[str] | None = None


class BaseVectorStore:
    """
    向量数据库操作基类

    提供向量数据库的基本操作接口：
    - 集合管理：创建、打开、销毁
    - 文档操作：插入、更新、删除、获取
    - 向量搜索：相似度搜索、过滤搜索

    注意：
    - 所有方法均为异步，使用 anyio.to_thread.run_sync() 包装 zvec 同步操作
    - 使用 threading.Lock 保证线程安全，zvec Collection 对象本身不是线程安全的
    """

    def __init__(self, config: CollectionConfig):
        self._config = config
        self._collection: Collection | None = None
        self._lock = threading.Lock()  # 线程锁，保护 Collection 操作

    async def _run_sync(self, func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
        """
        在线程池中执行同步函数，并自动加锁保证线程安全。

        所有 Collection 操作都应通过此方法执行。
        """

        def _do_with_lock():
            with self._lock:
                return func(*args, **kwargs)

        return await anyio.to_thread.run_sync(_do_with_lock)

    @property
    def collection(self) -> Collection:
        """获取集合实例（注意：直接访问不保证线程安全）"""
        if self._collection is None:
            raise RuntimeError("Collection not initialized. Call connect() first.")
        return self._collection

    @property
    def schema(self) -> CollectionSchema:
        """获取集合 Schema"""
        return self.collection.schema

    @property
    def stats(self) -> Any:
        """获取集合统计信息"""
        return self.collection.stats

    # ==========================================================================
    # 集合生命周期管理
    # ==========================================================================

    def build_schema(self) -> CollectionSchema:
        """构建集合 Schema"""
        fields = []
        vectors = []

        # 构建标量字段
        for sf in self._config.scalar_fields:
            data_type = getattr(zvec.DataType, sf.data_type, zvec.DataType.STRING)
            field_schema = zvec.FieldSchema(
                name=sf.name,
                data_type=data_type,
                nullable=sf.nullable,
            )
            if sf.indexed:
                field_schema = zvec.FieldSchema(
                    name=sf.name,
                    data_type=data_type,
                    nullable=sf.nullable,
                    index_param=zvec.InvertIndexParam(),
                )
            fields.append(field_schema)

        # 构建向量字段
        for vf in self._config.vector_fields:
            data_type = getattr(zvec.DataType, vf.data_type, zvec.DataType.VECTOR_FP32)
            metric_type = getattr(zvec.MetricType, vf.metric_type, zvec.MetricType.COSINE)

            # 根据索引类型创建索引参数
            if vf.index_type == IndexType.HNSW:
                index_param = zvec.HnswIndexParam(metric_type=metric_type)
            elif vf.index_type == IndexType.IVF:
                index_param = zvec.IVFIndexParam(metric_type=metric_type)
            else:
                index_param = zvec.FlatIndexParam(metric_type=metric_type)

            vectors.append(
                zvec.VectorSchema(
                    name=vf.name,
                    data_type=data_type,
                    dimension=vf.dimension,
                    index_param=index_param,
                )
            )

        return CollectionSchema(
            name=self._config.name,
            fields=fields,
            vectors=vectors,
        )

    async def connect(self) -> Self:
        """
        连接到向量数据库集合。

        如果集合不存在则创建，否则打开现有集合。
        """
        option = CollectionOption(
            read_only=self._config.read_only,
            enable_mmap=self._config.enable_mmap,
        )

        def _do_connect():
            try:
                return zvec.open(self._config.path, option)
            except Exception:
                schema = self.build_schema()
                return zvec.create_and_open(
                    path=self._config.path,
                    schema=schema,
                    option=option,
                )

        self._collection = await self._run_sync(_do_connect)
        return self

    def disconnect(self) -> None:
        """断开连接（释放资源）"""
        with self._lock:
            if self._collection is not None:
                self._collection = None

    async def destroy(self) -> None:
        """销毁集合（删除所有数据）"""

        def _do_destroy():
            if self._collection is not None:
                self._collection.destroy()
                return None
            return None

        await self._run_sync(_do_destroy)
        self._collection = None

    async def optimize(self) -> None:
        """优化集合（合并段、重建索引）"""
        await self._run_sync(self.collection.optimize)

    async def flush(self) -> None:
        """强制将所有待写入的数据刷新到磁盘"""
        await self._run_sync(self.collection.flush)

    # ==========================================================================
    # 文档操作
    # ==========================================================================

    async def insert(self, doc: Doc | dict[str, Any]) -> None:
        """
        插入单个文档

        Args:
            doc: 文档对象或字典
        """
        if isinstance(doc, dict):
            doc = self._dict_to_doc(doc)
        await self._run_sync(self.collection.insert, doc)

    async def insert_batch(self, docs: list[Doc] | list[dict[str, Any]]) -> None:
        """
        批量插入文档

        Args:
            docs: 文档列表
        """
        converted_docs = [self._dict_to_doc(d) if isinstance(d, dict) else d for d in docs]
        await self._run_sync(self.collection.insert, converted_docs)

    async def upsert(self, doc: Doc | dict[str, Any]) -> None:
        """
        插入或更新文档

        Args:
            doc: 文档对象或字典
        """
        if isinstance(doc, dict):
            doc = self._dict_to_doc(doc)
        await self._run_sync(self.collection.upsert, doc)

    async def upsert_batch(self, docs: list[Doc] | list[dict[str, Any]]) -> None:
        """
        批量插入或更新文档

        Args:
            docs: 文档列表
        """
        converted_docs = [self._dict_to_doc(d) if isinstance(d, dict) else d for d in docs]
        await self._run_sync(self.collection.upsert, converted_docs)

    async def update(self, doc: Doc | dict[str, Any]) -> None:
        """
        更新已存在的文档

        Args:
            doc: 文档对象或字典（必须包含 id）
        """
        if isinstance(doc, dict):
            doc = self._dict_to_doc(doc)
        await self._run_sync(self.collection.update, doc)

    async def delete(self, doc_ids: str | list[str]) -> None:
        """
        根据 ID 删除文档

        Args:
            doc_ids: 文档 ID 或 ID 列表
        """
        await self._run_sync(self.collection.delete, doc_ids)

    async def delete_by_filter(self, filter_expr: str) -> None:
        """
        根据过滤表达式删除文档

        Args:
            filter_expr: 过滤表达式，如 "price > 100"
        """
        await self._run_sync(self.collection.delete_by_filter, filter=filter_expr)

    async def fetch(self, doc_ids: str | list[str]) -> list[SearchResult]:
        """
        根据 ID 获取文档

        Args:
            doc_ids: 文档 ID 或 ID 列表

        Returns:
            文档列表
        """
        results = await self._run_sync(self.collection.fetch, doc_ids)
        return [SearchResult.from_doc(doc) for doc in results]

    # ==========================================================================
    # 向量搜索
    # ==========================================================================

    async def search(self, params: SearchParams) -> list[SearchResult]:
        """
        执行向量相似度搜索

        Args:
            params: 搜索参数

        Returns:
            搜索结果列表
        """
        vector_query = zvec.VectorQuery(
            field_name=params.vector_field,
            vector=params.vector,
        )
        results = await self._run_sync(
            self.collection.query,
            vector_query,
            filter=params.filter_expr,
            topk=params.top_k,
        )
        return [SearchResult.from_doc(doc) for doc in results]

    async def search_by_vector(
        self,
        vector: list[float],
        vector_field: str = "embedding",
        top_k: int = 10,
        filter_expr: str | None = None,
    ) -> list[SearchResult]:
        """
        简化的向量搜索方法

        Args:
            vector: 查询向量
            vector_field: 向量字段名称
            top_k: 返回结果数量
            filter_expr: 过滤表达式

        Returns:
            搜索结果列表
        """
        params = SearchParams(
            vector=vector,
            vector_field=vector_field,
            top_k=top_k,
            filter_expr=filter_expr,
        )
        return await self.search(params)

    # ==========================================================================
    # 索引管理
    # ==========================================================================

    async def create_index(
        self,
        field_name: str,
        index_type: IndexType = IndexType.HNSW,
        metric_type: VectorMetricType = VectorMetricType.COSINE,
    ) -> None:
        """
        为字段创建索引

        Args:
            field_name: 字段名称
            index_type: 索引类型
            metric_type: 相似度度量类型（仅向量字段）
        """
        metric = getattr(zvec.MetricType, metric_type, zvec.MetricType.COSINE)

        if index_type == IndexType.HNSW:
            index_param = zvec.HnswIndexParam(metric_type=metric)
        elif index_type == IndexType.IVF:
            index_param = zvec.IVFIndexParam(metric_type=metric)
        elif index_type == IndexType.FLAT:
            index_param = zvec.FlatIndexParam(metric_type=metric)
        else:
            index_param = zvec.InvertIndexParam()

        await self._run_sync(self.collection.create_index, field_name, index_param)

    async def drop_index(self, field_name: str) -> None:
        """
        删除字段索引

        Args:
            field_name: 字段名称
        """
        await self._run_sync(self.collection.drop_index, field_name)

    # ==========================================================================
    # Schema 演进
    # ==========================================================================

    async def add_column(
        self,
        field_config: ScalarFieldConfig,
        default_value: Any = None,
    ) -> None:
        """
        添加新列

        Args:
            field_config: 字段配置
            default_value: 默认值表达式
        """
        data_type = getattr(zvec.DataType, field_config.data_type, zvec.DataType.STRING)
        field_schema = zvec.FieldSchema(
            name=field_config.name,
            data_type=data_type,
            nullable=field_config.nullable,
        )
        expression = str(default_value) if default_value is not None else ""
        await self._run_sync(self.collection.add_column, field_schema, expression)

    async def drop_column(self, field_name: str) -> None:
        """
        删除列

        Args:
            field_name: 字段名称
        """
        await self._run_sync(self.collection.drop_column, field_name)

    # ==========================================================================
    # 辅助方法
    # ==========================================================================

    def _dict_to_doc(self, data: dict[str, Any]) -> Doc:
        """
        将字典转换为 Doc 对象

        Args:
            data: 包含 id, fields, vectors 等键的字典

        Returns:
            Doc 对象
        """
        doc_id = data.get("id")
        if doc_id is None:
            raise ValueError("Document must have an 'id' field")

        # 提取向量字段
        vectors = {}
        for vf in self._config.vector_fields:
            if vf.name in data:
                vectors[vf.name] = data[vf.name]

        # 提取标量字段
        fields = {}
        scalar_field_names = {sf.name for sf in self._config.scalar_fields}
        for key, value in data.items():
            if key != "id" and key not in vectors and key in scalar_field_names:
                fields[key] = value

        return Doc(
            id=str(doc_id),
            vectors=vectors if vectors else None,
            fields=fields if fields else None,
        )

    async def __aenter__(self) -> Self:
        return await self.connect()

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        self.disconnect()
