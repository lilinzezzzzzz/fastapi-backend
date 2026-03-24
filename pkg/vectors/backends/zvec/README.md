# Zvec 向量数据库操作模块

基于 [zvec](https://zvec.org/) 的向量数据库异步操作基类，通过 `anyio.to_thread.run_sync()` 实现异步支持。

## 安装

```bash
uv add zvec
```

## 快速开始

### 1. 定义集合配置

```python
from pkg.vectors.backends.zvec import (
    BaseVectorStore,
    CollectionConfig,
    VectorFieldConfig,
    ScalarFieldConfig,
    VectorMetricType,
    IndexType,
)

config = CollectionConfig(
    name="documents",
    path="./data/vectors",
    vector_fields=[
        VectorFieldConfig(
            name="embedding",
            dimension=768,
            metric_type=VectorMetricType.COSINE,
            index_type=IndexType.HNSW,
        )
    ],
    scalar_fields=[
        ScalarFieldConfig(name="title", data_type="STRING"),
        ScalarFieldConfig(name="category", data_type="STRING", indexed=True),
        ScalarFieldConfig(name="price", data_type="DOUBLE"),
    ],
)
```

### 2. 连接与基本操作

```python
import asyncio

async def main():
    # 使用异步上下文管理器
    async with BaseVectorStore(config) as store:
        # 插入文档
        await store.insert({
            "id": "doc_001",
            "embedding": [0.1] * 768,  # 实际使用时替换为真实向量
            "title": "Python 入门教程",
            "category": "programming",
            "price": 29.99,
        })

        # 批量插入
        await store.insert_batch([
            {"id": "doc_002", "embedding": [0.2] * 768, "title": "FastAPI 指南"},
            {"id": "doc_003", "embedding": [0.3] * 768, "title": "SQLAlchemy 教程"},
        ])

        # 根据 ID 获取文档
        docs = await store.fetch(["doc_001", "doc_002"])
        for doc in docs:
            print(f"ID: {doc.id}, Score: {doc.score}")
            print(f"Fields: {doc.fields}")

asyncio.run(main())
```

### 3. 向量搜索

```python
async def search_example():
    async with BaseVectorStore(config) as store:
        # 简单向量搜索
        results = await store.search_by_vector(
            vector=[0.15] * 768,
            vector_field="embedding",
            top_k=10,
        )

        for result in results:
            print(f"ID: {result.id}, Score: {result.score}")

        # 带过滤条件的向量搜索
        results = await store.search_by_vector(
            vector=[0.15] * 768,
            top_k=5,
            filter_expr="price > 20 AND category = 'programming'",
        )

        # 使用 SearchParams
        from pkg.vectors.backends.zvec import SearchParams

        params = SearchParams(
            vector=[0.15] * 768,
            vector_field="embedding",
            top_k=10,
            filter_expr="category = 'programming'",
        )
        results = await store.search(params)
```

### 4. 文档更新与删除

```python
async def crud_example():
    async with BaseVectorStore(config) as store:
        # 更新文档
        await store.update({
            "id": "doc_001",
            "title": "Python 高级教程",
            "price": 39.99,
        })

        # 插入或更新 (Upsert)
        await store.upsert({
            "id": "doc_001",
            "embedding": [0.25] * 768,
            "title": "更新后的标题",
        })

        # 根据 ID 删除
        await store.delete("doc_001")

        # 根据过滤条件删除
        await store.delete_by_filter("price < 10")
```

### 5. 索引管理

```python
async def index_example():
    async with BaseVectorStore(config) as store:
        # 创建 HNSW 索引
        await store.create_index(
            field_name="embedding",
            index_type=IndexType.HNSW,
            metric_type=VectorMetricType.COSINE,
        )

        # 创建 IVF 索引
        await store.create_index(
            field_name="embedding",
            index_type=IndexType.IVF,
        )

        # 创建标量字段倒排索引
        from pkg.vectors.backends.zvec import ScalarFieldConfig

        await store.add_column(
            ScalarFieldConfig(name="tags", data_type="ARRAY_STRING", indexed=True)
        )

        # 删除索引
        await store.drop_index("embedding")
```

### 6. Schema 演进

```python
async def schema_example():
    async with BaseVectorStore(config) as store:
        # 添加新列
        await store.add_column(
            ScalarFieldConfig(name="author", data_type="STRING"),
            default_value="unknown",
        )

        # 添加带索引的列
        await store.add_column(
            ScalarFieldConfig(name="publish_year", data_type="INT64", indexed=True),
        )

        # 删除列
        await store.drop_column("author")
```

### 7. 集合管理

```python
async def collection_example():
    store = BaseVectorStore(config)

    # 连接
    await store.connect()

    # 获取集合信息
    print(f"Schema: {store.schema}")
    print(f"Stats: {store.stats}")

    # 优化集合（合并段、重建索引）
    await store.optimize()

    # 强制刷新到磁盘
    await store.flush()

    # 销毁集合（删除所有数据）
    await store.destroy()
```

## 配置说明

### VectorFieldConfig

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `name` | str | 必填 | 向量字段名称 |
| `dimension` | int | 必填 | 向量维度 |
| `data_type` | VectorDataType | FP32 | 向量数据类型 |
| `metric_type` | VectorMetricType | COSINE | 相似度度量类型 |
| `index_type` | IndexType | FLAT | 索引类型 |
| `quantize_type` | str \| None | None | 量化类型 |

### ScalarFieldConfig

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `name` | str | 必填 | 字段名称 |
| `data_type` | str | 必填 | 数据类型 (INT64, STRING, DOUBLE, BOOL, ARRAY_STRING 等) |
| `nullable` | bool | False | 是否允许为空 |
| `indexed` | bool | False | 是否创建索引 |

### CollectionConfig

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `name` | str | 必填 | 集合名称 |
| `path` | str | 必填 | 集合存储路径 |
| `vector_fields` | list[VectorFieldConfig] | [] | 向量字段配置列表 |
| `scalar_fields` | list[ScalarFieldConfig] | [] | 标量字段配置列表 |
| `read_only` | bool | False | 只读模式 |
| `enable_mmap` | bool | True | 启用内存映射 |

## 枚举类型

### VectorMetricType

- `COSINE` - 余弦相似度
- `L2` - 欧氏距离
- `IP` - 内积

### IndexType

- `FLAT` - 暴力搜索，精确但较慢
- `HNSW` - 层次导航小世界图，高性能近似搜索
- `IVF` - 倒排文件索引，适合大规模数据

### VectorDataType

- `FP32` - 32位浮点数
- `FP16` - 16位浮点数
- `SPARSE_FP32` - 稀疏向量 (32位)
- `SPARSE_FP16` - 稀疏向量 (16位)

## 在 FastAPI 中使用

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from pkg.vectors.backends.zvec import BaseVectorStore, CollectionConfig, VectorFieldConfig

# 全局实例
_vector_store: BaseVectorStore | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _vector_store

    config = CollectionConfig(
        name="documents",
        path="./data/vectors",
        vector_fields=[VectorFieldConfig(name="embedding", dimension=768)],
    )

    _vector_store = BaseVectorStore(config)
    await _vector_store.connect()

    yield

    _vector_store.disconnect()

app = FastAPI(lifespan=lifespan)

@app.post("/search")
async def search(query_vector: list[float], top_k: int = 10):
    results = await _vector_store.search_by_vector(query_vector, top_k=top_k)
    return {"results": [{"id": r.id, "score": r.score, "fields": r.fields} for r in results]}
```

## 注意事项

1. **嵌入式数据库**：zvec 是嵌入式向量数据库，类似 SQLite，不支持连接池，直接操作本地文件。

2. **异步实现**：所有 I/O 操作通过 `anyio.to_thread.run_sync()` 在线程池中执行，避免阻塞事件循环。

3. **线程安全**：
   - zvec 的 Collection 对象本身不是线程安全的
   - BaseVectorStore 内部使用 `threading.Lock` 保证所有操作的线程安全
   - 多个协程可以安全地并发调用同一个 BaseVectorStore 实例的方法
   - 锁在线程池中获取，确保同一时刻只有一个线程操作 Collection

4. **资源管理**：使用 `async with` 上下文管理器确保正确释放资源。

## 参考文档

- [Zvec 官方文档](https://zvec.org/en/docs/quickstart/)
- [Zvec GitHub](https://github.com/alibaba/zvec)
