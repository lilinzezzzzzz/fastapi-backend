"""
Zvec 向量数据库操作基类测试

测试覆盖：
- 配置类 (VectorFieldConfig, ScalarFieldConfig, CollectionConfig)
- 枚举类型 (VectorMetricType, VectorDataType, IndexType)
- SearchResult 数据转换
- SearchParams 参数类
- BaseVectorStore 集合生命周期管理
- BaseVectorStore 文档 CRUD 操作
- BaseVectorStore 向量搜索
- BaseVectorStore 索引管理
- BaseVectorStore Schema 演进
- 异步上下文管理器
"""

import tempfile
from pathlib import Path

import pytest
import pytest_asyncio
from zvec import Doc

from pkg.zvec_vector import (
    BaseVectorStore,
    CollectionConfig,
    IndexType,
    ScalarFieldConfig,
    SearchParams,
    SearchResult,
    VectorDataType,
    VectorFieldConfig,
    VectorMetricType,
)

# ==========================================================================
# Fixtures
# ==========================================================================


@pytest.fixture
def anyio_backend():
    """配置 anyio 后端"""
    return "asyncio"


@pytest.fixture
def temp_dir():
    """创建临时目录用于测试"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def basic_config(temp_dir: Path) -> CollectionConfig:
    """基础集合配置"""
    return CollectionConfig(
        name="test_collection",
        path=str(temp_dir / "test_vectors"),
        vector_fields=[
            VectorFieldConfig(
                name="embedding",
                dimension=4,
                metric_type=VectorMetricType.COSINE,
                index_type=IndexType.FLAT,
            )
        ],
        scalar_fields=[
            ScalarFieldConfig(name="title", data_type="STRING"),
            ScalarFieldConfig(name="category", data_type="STRING", indexed=True),
            ScalarFieldConfig(name="price", data_type="DOUBLE"),
        ],
    )


@pytest.fixture
def multi_vector_config(temp_dir: Path) -> CollectionConfig:
    """多向量字段配置"""
    return CollectionConfig(
        name="multi_vector_collection",
        path=str(temp_dir / "multi_vectors"),
        vector_fields=[
            VectorFieldConfig(name="dense_vec", dimension=8, index_type=IndexType.HNSW),
            VectorFieldConfig(name="sparse_vec", dimension=4, data_type=VectorDataType.SPARSE_FP32),
        ],
        scalar_fields=[
            ScalarFieldConfig(name="doc_id", data_type="INT64"),
        ],
    )


@pytest_asyncio.fixture
async def vector_store(basic_config: CollectionConfig) -> BaseVectorStore:
    """创建并连接向量存储"""
    store = BaseVectorStore(basic_config)
    await store.connect()
    yield store
    store.disconnect()


# ==========================================================================
# 枚举类型测试
# ==========================================================================


class TestEnums:
    """测试枚举类型"""

    def test_vector_metric_type_values(self):
        assert VectorMetricType.COSINE == "COSINE"
        assert VectorMetricType.L2 == "L2"
        assert VectorMetricType.IP == "IP"

    def test_vector_data_type_values(self):
        assert VectorDataType.FP32 == "VECTOR_FP32"
        assert VectorDataType.FP16 == "VECTOR_FP16"
        assert VectorDataType.SPARSE_FP32 == "SPARSE_VECTOR_FP32"
        assert VectorDataType.SPARSE_FP16 == "SPARSE_VECTOR_FP16"

    def test_index_type_values(self):
        assert IndexType.FLAT == "FLAT"
        assert IndexType.HNSW == "HNSW"
        assert IndexType.IVF == "IVF"


# ==========================================================================
# 配置类测试
# ==========================================================================


class TestConfigs:
    """测试配置类"""

    def test_vector_field_config_defaults(self):
        config = VectorFieldConfig(name="test", dimension=128)

        assert config.name == "test"
        assert config.dimension == 128
        assert config.data_type == VectorDataType.FP32
        assert config.metric_type == VectorMetricType.COSINE
        assert config.index_type == IndexType.FLAT
        assert config.quantize_type is None

    def test_vector_field_config_custom(self):
        config = VectorFieldConfig(
            name="custom_vec",
            dimension=768,
            data_type=VectorDataType.FP16,
            metric_type=VectorMetricType.L2,
            index_type=IndexType.HNSW,
            quantize_type="INT8",
        )

        assert config.name == "custom_vec"
        assert config.dimension == 768
        assert config.data_type == VectorDataType.FP16
        assert config.metric_type == VectorMetricType.L2
        assert config.index_type == IndexType.HNSW
        assert config.quantize_type == "INT8"

    def test_scalar_field_config_defaults(self):
        config = ScalarFieldConfig(name="field", data_type="STRING")

        assert config.name == "field"
        assert config.data_type == "STRING"
        assert config.nullable is False
        assert config.indexed is False

    def test_scalar_field_config_custom(self):
        config = ScalarFieldConfig(
            name="indexed_field",
            data_type="INT64",
            nullable=True,
            indexed=True,
        )

        assert config.name == "indexed_field"
        assert config.data_type == "INT64"
        assert config.nullable is True
        assert config.indexed is True

    def test_collection_config_defaults(self):
        config = CollectionConfig(name="test", path="/tmp/test")

        assert config.name == "test"
        assert config.path == "/tmp/test"
        assert config.vector_fields == []
        assert config.scalar_fields == []
        assert config.read_only is False
        assert config.enable_mmap is True

    def test_collection_config_with_fields(self, basic_config: CollectionConfig):
        assert basic_config.name == "test_collection"
        assert len(basic_config.vector_fields) == 1
        assert len(basic_config.scalar_fields) == 3


# ==========================================================================
# SearchResult 测试
# ==========================================================================


class TestSearchResult:
    """测试 SearchResult 数据类"""

    def test_from_doc_basic(self):
        """测试从 Doc 对象转换"""
        doc = Doc(
            id="test_id",
            score=0.95,
            fields={"title": "Test Document", "category": "test"},
            vectors={"embedding": [0.1, 0.2, 0.3, 0.4]},
        )

        result = SearchResult.from_doc(doc)

        assert result.id == "test_id"
        assert result.score == 0.95
        assert result.fields == {"title": "Test Document", "category": "test"}
        assert result.vectors == {"embedding": [0.1, 0.2, 0.3, 0.4]}

    def test_from_doc_no_score(self):
        """测试无分数的 Doc 转换"""
        doc = Doc(id="no_score", fields={"key": "value"})

        result = SearchResult.from_doc(doc)

        assert result.id == "no_score"
        assert result.score == 0.0  # 默认分数

    def test_from_doc_no_vectors(self):
        """测试无向量的 Doc 转换"""
        doc = Doc(id="no_vectors", score=0.5, fields={"key": "value"})

        result = SearchResult.from_doc(doc)

        assert result.vectors == {}

    def test_search_result_defaults(self):
        """测试 SearchResult 默认值"""
        result = SearchResult(id="test", score=0.5)

        assert result.fields == {}
        assert result.vectors == {}


# ==========================================================================
# SearchParams 测试
# ==========================================================================


class TestSearchParams:
    """测试搜索参数"""

    def test_search_params_defaults(self):
        params = SearchParams(vector=[0.1, 0.2, 0.3])

        assert params.vector == [0.1, 0.2, 0.3]
        assert params.vector_field == "embedding"
        assert params.top_k == 10
        assert params.filter_expr is None
        assert params.include_vectors is False
        assert params.include_fields is None

    def test_search_params_custom(self):
        params = SearchParams(
            vector=[0.1] * 768,
            vector_field="dense_vec",
            top_k=50,
            filter_expr="category = 'test'",
            include_vectors=True,
            include_fields=["title", "price"],
        )

        assert params.vector_field == "dense_vec"
        assert params.top_k == 50
        assert params.filter_expr == "category = 'test'"
        assert params.include_vectors is True
        assert params.include_fields == ["title", "price"]


# ==========================================================================
# BaseVectorStore 生命周期测试
# ==========================================================================


@pytest.mark.anyio
class TestBaseVectorStoreLifecycle:
    """测试向量存储生命周期"""

    async def test_connect_creates_collection(self, basic_config: CollectionConfig):
        """测试连接时创建新集合"""
        store = BaseVectorStore(basic_config)

        # 连接前 collection 为 None
        assert store._collection is None

        await store.connect()

        # 连接后 collection 已初始化
        assert store._collection is not None
        assert store.schema is not None

        store.disconnect()

    async def test_connect_opens_existing_collection(self, basic_config: CollectionConfig):
        """测试连接时打开已存在的集合"""
        # 第一次连接创建集合
        store1 = BaseVectorStore(basic_config)
        await store1.connect()
        store1.disconnect()

        # 第二次连接打开已存在的集合
        store2 = BaseVectorStore(basic_config)
        await store2.connect()

        assert store2._collection is not None

        store2.disconnect()

    async def test_disconnect(self, basic_config: CollectionConfig):
        """测试断开连接"""
        store = BaseVectorStore(basic_config)
        await store.connect()

        assert store._collection is not None

        store.disconnect()

        assert store._collection is None

    async def test_destroy(self, basic_config: CollectionConfig):
        """测试销毁集合"""
        store = BaseVectorStore(basic_config)
        await store.connect()

        # 插入数据
        await store.insert({"id": "doc1", "embedding": [0.1, 0.2, 0.3, 0.4]})

        # 销毁集合
        await store.destroy()

        assert store._collection is None

    async def test_collection_property_raises_when_not_connected(self, basic_config: CollectionConfig):
        """测试未连接时访问 collection 属性抛出异常"""
        store = BaseVectorStore(basic_config)

        with pytest.raises(RuntimeError, match="Collection not initialized"):
            _ = store.collection

    async def test_schema_property(self, vector_store: BaseVectorStore):
        """测试 schema 属性"""
        schema = vector_store.schema
        assert schema is not None

    async def test_stats_property(self, vector_store: BaseVectorStore):
        """测试 stats 属性"""
        stats = vector_store.stats
        assert stats is not None

    async def test_async_context_manager(self, basic_config: CollectionConfig):
        """测试异步上下文管理器"""
        async with BaseVectorStore(basic_config) as store:
            assert store._collection is not None

        # 退出后已断开连接
        assert store._collection is None

    async def test_flush(self, vector_store: BaseVectorStore):
        """测试刷新到磁盘"""
        await vector_store.flush()  # 不应抛出异常

    async def test_optimize(self, vector_store: BaseVectorStore):
        """测试优化集合"""
        await vector_store.optimize()  # 不应抛出异常


# ==========================================================================
# BaseVectorStore 文档操作测试
# ==========================================================================


@pytest.mark.anyio
class TestBaseVectorStoreDocuments:
    """测试文档 CRUD 操作"""

    async def test_insert_dict(self, vector_store: BaseVectorStore):
        """测试插入字典格式文档"""
        await vector_store.insert(
            {
                "id": "doc_001",
                "embedding": [0.1, 0.2, 0.3, 0.4],
                "title": "Test Document",
                "category": "test",
                "price": 19.99,
            }
        )

        # 验证插入成功
        results = await vector_store.fetch("doc_001")
        assert len(results) == 1
        assert results[0].id == "doc_001"

    async def test_insert_doc_object(self, vector_store: BaseVectorStore):
        """测试插入 Doc 对象"""
        doc = Doc(
            id="doc_002",
            vectors={"embedding": [0.5, 0.6, 0.7, 0.8]},
            fields={"title": "Doc Object"},
        )

        await vector_store.insert(doc)

        results = await vector_store.fetch("doc_002")
        assert len(results) == 1

    async def test_insert_batch(self, vector_store: BaseVectorStore):
        """测试批量插入"""
        docs = [
            {"id": "batch_1", "embedding": [0.1, 0.2, 0.3, 0.4], "title": "Batch 1"},
            {"id": "batch_2", "embedding": [0.5, 0.6, 0.7, 0.8], "title": "Batch 2"},
            {"id": "batch_3", "embedding": [0.9, 1.0, 0.1, 0.2], "title": "Batch 3"},
        ]

        await vector_store.insert_batch(docs)

        results = await vector_store.fetch(["batch_1", "batch_2", "batch_3"])
        assert len(results) == 3

    async def test_upsert_insert(self, vector_store: BaseVectorStore):
        """测试 upsert 插入新文档"""
        await vector_store.upsert(
            {
                "id": "upsert_new",
                "embedding": [0.1, 0.2, 0.3, 0.4],
                "title": "Upsert New",
            }
        )

        results = await vector_store.fetch("upsert_new")
        assert len(results) == 1

    async def test_upsert_update(self, vector_store: BaseVectorStore):
        """测试 upsert 更新已存在的文档"""
        # 先插入
        await vector_store.insert(
            {
                "id": "upsert_update",
                "embedding": [0.1, 0.2, 0.3, 0.4],
                "title": "Original Title",
            }
        )

        # 更新
        await vector_store.upsert(
            {
                "id": "upsert_update",
                "embedding": [0.5, 0.6, 0.7, 0.8],
                "title": "Updated Title",
            }
        )

        results = await vector_store.fetch("upsert_update")
        assert len(results) == 1
        assert results[0].fields.get("title") == "Updated Title"

    async def test_upsert_batch(self, vector_store: BaseVectorStore):
        """测试批量 upsert"""
        docs = [
            {"id": "upsert_batch_1", "embedding": [0.1, 0.2, 0.3, 0.4], "title": "Batch 1"},
            {"id": "upsert_batch_2", "embedding": [0.5, 0.6, 0.7, 0.8], "title": "Batch 2"},
        ]

        await vector_store.upsert_batch(docs)

        results = await vector_store.fetch(["upsert_batch_1", "upsert_batch_2"])
        assert len(results) == 2

    async def test_update(self, vector_store: BaseVectorStore):
        """测试更新文档"""
        # 先插入
        await vector_store.insert(
            {
                "id": "update_test",
                "embedding": [0.1, 0.2, 0.3, 0.4],
                "title": "Original",
                "price": 10.0,
            }
        )

        # 更新字段
        await vector_store.update(
            {
                "id": "update_test",
                "title": "Updated",
                "price": 20.0,
            }
        )

        results = await vector_store.fetch("update_test")
        assert results[0].fields.get("title") == "Updated"
        assert results[0].fields.get("price") == 20.0

    async def test_delete_single(self, vector_store: BaseVectorStore):
        """测试删除单个文档"""
        await vector_store.insert(
            {
                "id": "delete_single",
                "embedding": [0.1, 0.2, 0.3, 0.4],
            }
        )

        await vector_store.delete("delete_single")

        results = await vector_store.fetch("delete_single")
        assert len(results) == 0

    async def test_delete_multiple(self, vector_store: BaseVectorStore):
        """测试删除多个文档"""
        await vector_store.insert_batch(
            [
                {"id": "delete_multi_1", "embedding": [0.1, 0.2, 0.3, 0.4]},
                {"id": "delete_multi_2", "embedding": [0.5, 0.6, 0.7, 0.8]},
                {"id": "delete_multi_3", "embedding": [0.9, 1.0, 0.1, 0.2]},
            ]
        )

        await vector_store.delete(["delete_multi_1", "delete_multi_2"])

        results = await vector_store.fetch(["delete_multi_1", "delete_multi_2", "delete_multi_3"])
        assert len(results) == 1

    async def test_delete_by_filter(self, vector_store: BaseVectorStore):
        """测试根据过滤条件删除"""
        await vector_store.insert_batch(
            [
                {"id": "filter_1", "embedding": [0.1, 0.2, 0.3, 0.4], "category": "delete"},
                {"id": "filter_2", "embedding": [0.5, 0.6, 0.7, 0.8], "category": "keep"},
            ]
        )

        await vector_store.delete_by_filter("category = 'delete'")

        results = await vector_store.fetch(["filter_1", "filter_2"])
        assert len(results) == 1
        assert results[0].id == "filter_2"

    async def test_fetch_single(self, vector_store: BaseVectorStore):
        """测试获取单个文档"""
        await vector_store.insert(
            {
                "id": "fetch_single",
                "embedding": [0.1, 0.2, 0.3, 0.4],
                "title": "Fetch Test",
            }
        )

        results = await vector_store.fetch("fetch_single")

        assert len(results) == 1
        assert results[0].id == "fetch_single"
        assert results[0].fields.get("title") == "Fetch Test"

    async def test_fetch_multiple(self, vector_store: BaseVectorStore):
        """测试获取多个文档"""
        await vector_store.insert_batch(
            [
                {"id": "fetch_1", "embedding": [0.1, 0.2, 0.3, 0.4]},
                {"id": "fetch_2", "embedding": [0.5, 0.6, 0.7, 0.8]},
            ]
        )

        results = await vector_store.fetch(["fetch_1", "fetch_2"])

        assert len(results) == 2
        ids = {r.id for r in results}
        assert ids == {"fetch_1", "fetch_2"}

    async def test_fetch_nonexistent(self, vector_store: BaseVectorStore):
        """测试获取不存在的文档"""
        results = await vector_store.fetch("nonexistent_id")
        assert len(results) == 0


# ==========================================================================
# BaseVectorStore 向量搜索测试
# ==========================================================================


@pytest.mark.anyio
class TestBaseVectorStoreSearch:
    """测试向量搜索"""

    async def test_search_by_vector(self, vector_store: BaseVectorStore):
        """测试基本向量搜索"""
        # 插入测试数据
        await vector_store.insert_batch(
            [
                {"id": "search_1", "embedding": [0.1, 0.2, 0.3, 0.4], "title": "Document 1"},
                {"id": "search_2", "embedding": [0.5, 0.6, 0.7, 0.8], "title": "Document 2"},
                {"id": "search_3", "embedding": [0.9, 1.0, 0.1, 0.2], "title": "Document 3"},
            ]
        )

        # 优化索引
        await vector_store.optimize()

        # 搜索
        results = await vector_store.search_by_vector([0.1, 0.2, 0.3, 0.4], top_k=2)

        assert len(results) <= 2
        # 第一个结果应该是 search_1（最相似）
        assert results[0].id == "search_1"

    async def test_search_with_params(self, vector_store: BaseVectorStore):
        """测试使用 SearchParams 搜索"""
        await vector_store.insert_batch(
            [
                {"id": "params_1", "embedding": [0.1, 0.2, 0.3, 0.4]},
                {"id": "params_2", "embedding": [0.5, 0.6, 0.7, 0.8]},
            ]
        )

        await vector_store.optimize()

        params = SearchParams(
            vector=[0.1, 0.2, 0.3, 0.4],
            vector_field="embedding",
            top_k=5,
        )

        results = await vector_store.search(params)

        assert len(results) >= 1
        assert all(isinstance(r, SearchResult) for r in results)

    async def test_search_with_filter(self, vector_store: BaseVectorStore):
        """测试带过滤条件的搜索"""
        await vector_store.insert_batch(
            [
                {"id": "filter_search_1", "embedding": [0.1, 0.2, 0.3, 0.4], "category": "tech"},
                {"id": "filter_search_2", "embedding": [0.5, 0.6, 0.7, 0.8], "category": "news"},
            ]
        )

        await vector_store.optimize()

        results = await vector_store.search_by_vector(
            vector=[0.1, 0.2, 0.3, 0.4],
            top_k=10,
            filter_expr="category = 'tech'",
        )

        # 只返回 category = 'tech' 的结果
        assert all(r.fields.get("category") == "tech" for r in results if r.fields)


# ==========================================================================
# BaseVectorStore 索引管理测试
# ==========================================================================


@pytest.mark.anyio
class TestBaseVectorStoreIndex:
    """测试索引管理"""

    async def test_create_flat_index(self, vector_store: BaseVectorStore):
        """测试创建 FLAT 索引"""
        await vector_store.create_index(
            field_name="embedding",
            index_type=IndexType.FLAT,
            metric_type=VectorMetricType.COSINE,
        )  # 不应抛出异常

    async def test_create_hnsw_index(self, vector_store: BaseVectorStore):
        """测试创建 HNSW 索引"""
        await vector_store.create_index(
            field_name="embedding",
            index_type=IndexType.HNSW,
            metric_type=VectorMetricType.L2,
        )  # 不应抛出异常

    async def test_drop_index(self, vector_store: BaseVectorStore):
        """测试删除索引"""
        await vector_store.create_index("embedding", IndexType.FLAT)
        await vector_store.drop_index("embedding")  # 不应抛出异常


# ==========================================================================
# BaseVectorStore Schema 演进测试
# ==========================================================================


@pytest.mark.anyio
class TestBaseVectorStoreSchema:
    """测试 Schema 演进"""

    async def test_add_column(self, vector_store: BaseVectorStore):
        """测试添加新列"""
        new_field = ScalarFieldConfig(name="new_column", data_type="STRING")

        await vector_store.add_column(new_field, default_value="default_value")

        # 插入数据验证新列存在
        await vector_store.insert(
            {
                "id": "new_col_test",
                "embedding": [0.1, 0.2, 0.3, 0.4],
                "new_column": "test_value",
            }
        )

        results = await vector_store.fetch("new_col_test")
        assert len(results) == 1

    async def test_drop_column(self, vector_store: BaseVectorStore):
        """测试删除列"""
        # 先添加一个列
        await vector_store.add_column(
            ScalarFieldConfig(name="to_drop", data_type="STRING"),
        )

        # 删除列
        await vector_store.drop_column("to_drop")  # 不应抛出异常


# ==========================================================================
# 辅助方法测试
# ==========================================================================


class TestHelperMethods:
    """测试辅助方法"""

    def test_dict_to_doc_basic(self, basic_config: CollectionConfig):
        """测试字典转 Doc 基本功能"""
        store = BaseVectorStore(basic_config)

        doc = store._dict_to_doc(
            {
                "id": "test_id",
                "embedding": [0.1, 0.2, 0.3, 0.4],
                "title": "Test Title",
                "category": "test",
                "price": 19.99,
            }
        )

        assert doc.id == "test_id"
        assert doc.vectors == {"embedding": [0.1, 0.2, 0.3, 0.4]}
        assert doc.fields == {"title": "Test Title", "category": "test", "price": 19.99}

    def test_dict_to_doc_missing_id(self, basic_config: CollectionConfig):
        """测试缺少 id 时抛出异常"""
        store = BaseVectorStore(basic_config)

        with pytest.raises(ValueError, match="Document must have an 'id' field"):
            store._dict_to_doc({"title": "No ID"})

    def test_dict_to_doc_no_vectors(self, basic_config: CollectionConfig):
        """测试无向量字段的字典转换"""
        store = BaseVectorStore(basic_config)

        doc = store._dict_to_doc(
            {
                "id": "no_vectors",
                "title": "Only Scalars",
            }
        )

        assert doc.id == "no_vectors"
        assert doc.vectors == {}
        assert doc.fields == {"title": "Only Scalars"}

    def test_dict_to_doc_ignores_unknown_fields(self, basic_config: CollectionConfig):
        """测试忽略未知字段"""
        store = BaseVectorStore(basic_config)

        doc = store._dict_to_doc(
            {
                "id": "unknown_fields",
                "embedding": [0.1, 0.2, 0.3, 0.4],
                "title": "Known",
                "unknown_field": "should be ignored",
            }
        )

        assert "unknown_field" not in doc.fields
        assert doc.fields == {"title": "Known"}


# ==========================================================================
# build_schema 测试
# ==========================================================================


class TestBuildSchema:
    """测试 Schema 构建"""

    def test_build_schema_basic(self, basic_config: CollectionConfig):
        """测试基本 Schema 构建"""
        store = BaseVectorStore(basic_config)
        schema = store.build_schema()

        assert schema.name == "test_collection"
        assert len(schema.fields) == 3  # title, category, price
        assert len(schema.vectors) == 1  # embedding

    def test_build_schema_multi_vector(self, multi_vector_config: CollectionConfig):
        """测试多向量字段 Schema 构建"""
        store = BaseVectorStore(multi_vector_config)
        schema = store.build_schema()

        assert len(schema.vectors) == 2
        vector_names = {v.name for v in schema.vectors}
        assert "dense_vec" in vector_names
        assert "sparse_vec" in vector_names

    def test_build_schema_with_indexed_field(self, basic_config: CollectionConfig):
        """测试带索引字段的 Schema 构建"""
        store = BaseVectorStore(basic_config)
        schema = store.build_schema()

        # category 字段有索引
        category_field = next(f for f in schema.fields if f.name == "category")
        assert category_field.index_param is not None


# ==========================================================================
# 边界条件测试
# ==========================================================================


@pytest.mark.anyio
class TestEdgeCases:
    """测试边界条件"""

    async def test_empty_vector_search(self, vector_store: BaseVectorStore):
        """测试空集合搜索"""
        results = await vector_store.search_by_vector([0.1, 0.2, 0.3, 0.4])
        assert len(results) == 0

    async def test_insert_empty_batch(self, vector_store: BaseVectorStore):
        """测试插入空批次"""
        await vector_store.insert_batch([])  # 不应抛出异常

    async def test_fetch_empty_list(self, vector_store: BaseVectorStore):
        """测试获取空 ID 列表"""
        results = await vector_store.fetch([])
        assert len(results) == 0

    async def test_delete_nonexistent(self, vector_store: BaseVectorStore):
        """测试删除不存在的文档"""
        await vector_store.delete("nonexistent_id")  # 不应抛出异常

    async def test_update_nonexistent(self, vector_store: BaseVectorStore):
        """测试更新不存在的文档"""
        # zvec 的 update 可能会失败或静默处理
        try:
            await vector_store.update(
                {
                    "id": "nonexistent",
                    "title": "Update Nonexistent",
                }
            )
        except Exception:
            pass  # 某些实现可能会抛出异常

    async def test_read_only_mode(self, temp_dir: Path):
        """测试只读模式"""
        config = CollectionConfig(
            name="readonly_test",
            path=str(temp_dir / "readonly"),
            vector_fields=[VectorFieldConfig(name="embedding", dimension=4)],
            read_only=False,  # 先创建
        )

        # 创建并插入数据
        store = BaseVectorStore(config)
        await store.connect()
        await store.insert({"id": "doc1", "embedding": [0.1, 0.2, 0.3, 0.4]})
        store.disconnect()

        # 以只读模式重新打开
        config.read_only = True
        readonly_store = BaseVectorStore(config)
        await readonly_store.connect()

        # 读取应该成功
        results = await readonly_store.fetch("doc1")
        assert len(results) == 1

        readonly_store.disconnect()
