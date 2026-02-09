"""
OpenTelemetry Demo 控制器

提供 Mock 端点用于观测 OpenTelemetry 的 Traces/Spans 效果以及与 loguru 日志的联动。
包含：LLM 请求、Milvus 全流程请求、MySQL 查询、Redis 查询、完整链路演示。
"""

import asyncio
import random
import time

from fastapi import APIRouter
from opentelemetry.trace import StatusCode
from pydantic import BaseModel, Field

from pkg.logger import logger
from pkg.toolkit.otel import get_current_trace_id, get_tracer
from pkg.toolkit.response import success_response

router = APIRouter(prefix="/otel-demo", tags=["OpenTelemetry Demo"])

# 获取 tracer 实例
tracer = get_tracer("otel_demo")


# ==================== Schema ====================
class LLMChatRequest(BaseModel):
    """LLM 聊天请求"""

    model: str = Field(default="gpt-4o", description="模型名称")
    prompt: str = Field(default="你好，请介绍一下 OpenTelemetry", description="用户提示词")
    max_tokens: int = Field(default=512, ge=1, le=4096, description="最大 token 数")


class MilvusSearchRequest(BaseModel):
    """Milvus 搜索请求"""

    collection_name: str = Field(default="demo_collection", description="集合名称")
    dimension: int = Field(default=768, ge=1, le=4096, description="向量维度")
    top_k: int = Field(default=10, ge=1, le=100, description="返回结果数")
    query_text: str = Field(default="OpenTelemetry 分布式追踪", description="查询文本")


# ==================== Mock 辅助函数 ====================


async def _mock_llm_completion(model: str, prompt: str, max_tokens: int) -> dict:
    """
    模拟 LLM Chat Completion 请求（含手动 span）
    """
    with tracer.start_as_current_span(
        "llm.chat_completion",
        attributes={
            "llm.system": "openai",
            "llm.model": model,
            "llm.max_tokens": max_tokens,
            "llm.prompt_length": len(prompt),
        },
    ) as span:
        # 阶段 1: 构建请求
        span.add_event("llm.request.start", {"llm.prompt": prompt[:100]})
        logger.info(f"LLM request start, model={model}, prompt_length={len(prompt)}")
        await asyncio.sleep(random.uniform(0.05, 0.15))

        # 阶段 2: 模拟模型推理
        span.add_event("llm.inference.start")
        logger.info("LLM inference processing...")
        await asyncio.sleep(random.uniform(0.2, 0.5))

        # 阶段 3: 生成结果
        mock_response_text = (
            f"这是来自 {model} 的模拟回复。OpenTelemetry 是一个开源的可观测性框架，"
            "提供了统一的 API 和 SDK，用于收集分布式系统的追踪（Traces）、"
            "指标（Metrics）和日志（Logs）数据。"
        )
        prompt_tokens = len(prompt) * 2  # 模拟 token 计算
        completion_tokens = len(mock_response_text) * 2
        total_tokens = prompt_tokens + completion_tokens

        span.set_attribute("llm.prompt_tokens", prompt_tokens)
        span.set_attribute("llm.completion_tokens", completion_tokens)
        span.set_attribute("llm.total_tokens", total_tokens)
        span.add_event("llm.inference.complete", {"llm.total_tokens": total_tokens})
        span.set_status(StatusCode.OK)

        logger.info(
            f"LLM completion done, prompt_tokens={prompt_tokens}, "
            f"completion_tokens={completion_tokens}, total_tokens={total_tokens}"
        )

        return {
            "model": model,
            "response": mock_response_text,
            "usage": {
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
            },
        }


async def _mock_milvus_pipeline(collection_name: str, dimension: int, top_k: int, query_text: str) -> dict:
    """
    模拟 Milvus 完整流程（创建集合 -> 插入向量 -> 搜索 -> 删除集合）
    """
    with tracer.start_as_current_span(
        "milvus.search_pipeline",
        attributes={
            "milvus.collection": collection_name,
            "milvus.dimension": dimension,
        },
    ) as parent_span:
        results = {}

        # 子 span 1: 创建集合
        with tracer.start_as_current_span(
            "milvus.create_collection",
            attributes={
                "milvus.collection": collection_name,
                "milvus.dimension": dimension,
                "milvus.metric_type": "COSINE",
            },
        ) as span:
            logger.info(f"Milvus: creating collection '{collection_name}', dimension={dimension}")
            await asyncio.sleep(random.uniform(0.05, 0.1))
            span.set_status(StatusCode.OK)
            span.add_event("collection.created")
            results["create_collection"] = "ok"

        # 子 span 2: 插入向量
        num_vectors = random.randint(100, 500)
        with tracer.start_as_current_span(
            "milvus.insert_vectors",
            attributes={
                "milvus.collection": collection_name,
                "milvus.num_vectors": num_vectors,
                "milvus.dimension": dimension,
            },
        ) as span:
            logger.info(f"Milvus: inserting {num_vectors} vectors into '{collection_name}'")
            await asyncio.sleep(random.uniform(0.1, 0.3))
            span.set_status(StatusCode.OK)
            span.add_event("vectors.inserted", {"count": num_vectors})
            results["insert_vectors"] = {"count": num_vectors}

        # 子 span 3: 相似度搜索
        with tracer.start_as_current_span(
            "milvus.search",
            attributes={
                "milvus.collection": collection_name,
                "milvus.top_k": top_k,
                "milvus.query_text": query_text[:100],
                "milvus.metric_type": "COSINE",
            },
        ) as span:
            logger.info(f"Milvus: searching top_{top_k} in '{collection_name}', query='{query_text[:50]}'")
            await asyncio.sleep(random.uniform(0.08, 0.2))

            # 模拟搜索结果
            mock_results = [
                {"id": random.randint(1000, 9999), "score": round(random.uniform(0.7, 0.99), 4)}
                for _ in range(top_k)
            ]
            mock_results.sort(key=lambda x: x["score"], reverse=True)

            span.set_attribute("milvus.result_count", len(mock_results))
            span.set_status(StatusCode.OK)
            span.add_event("search.complete", {"result_count": len(mock_results)})
            results["search_results"] = mock_results

        # 子 span 4: 删除集合
        with tracer.start_as_current_span(
            "milvus.delete_collection",
            attributes={"milvus.collection": collection_name},
        ) as span:
            logger.info(f"Milvus: deleting collection '{collection_name}'")
            await asyncio.sleep(random.uniform(0.03, 0.08))
            span.set_status(StatusCode.OK)
            span.add_event("collection.deleted")
            results["delete_collection"] = "ok"

        parent_span.set_status(StatusCode.OK)
        logger.info(f"Milvus pipeline complete for '{collection_name}'")

        return results


async def _mock_mysql_query() -> dict:
    """
    模拟 MySQL 查询请求
    """
    with tracer.start_as_current_span(
        "db.mysql.query",
        attributes={
            "db.system": "mysql",
            "db.name": "demo_db",
            "db.operation": "SELECT",
            "db.statement": "SELECT id, name, email, created_at FROM users WHERE status = 'active' ORDER BY created_at DESC LIMIT 10",
        },
    ) as span:
        logger.info("MySQL: executing SELECT query on users table")
        await asyncio.sleep(random.uniform(0.02, 0.1))

        # 模拟查询结果
        mock_rows = [
            {
                "id": i,
                "name": f"user_{i}",
                "email": f"user_{i}@example.com",
                "created_at": "2026-02-09T10:00:00Z",
            }
            for i in range(1, 6)
        ]

        span.set_attribute("db.row_count", len(mock_rows))
        span.set_status(StatusCode.OK)
        span.add_event("query.complete", {"row_count": len(mock_rows)})

        logger.info(f"MySQL: query returned {len(mock_rows)} rows")

        return {"query": "SELECT ... FROM users", "row_count": len(mock_rows), "rows": mock_rows}


async def _mock_redis_query() -> dict:
    """
    模拟 Redis 查询请求（GET/SET/HGETALL）
    """
    results = {}

    # SET 操作
    with tracer.start_as_current_span(
        "db.redis.set",
        attributes={
            "db.system": "redis",
            "db.operation": "SET",
            "db.redis.key": "otel_demo:user:1001",
        },
    ) as span:
        logger.info("Redis: SET otel_demo:user:1001")
        await asyncio.sleep(random.uniform(0.005, 0.02))
        span.set_status(StatusCode.OK)
        results["set"] = {"key": "otel_demo:user:1001", "status": "OK"}

    # GET 操作
    with tracer.start_as_current_span(
        "db.redis.get",
        attributes={
            "db.system": "redis",
            "db.operation": "GET",
            "db.redis.key": "otel_demo:user:1001",
        },
    ) as span:
        logger.info("Redis: GET otel_demo:user:1001")
        await asyncio.sleep(random.uniform(0.003, 0.015))
        mock_value = '{"id": 1001, "name": "demo_user", "role": "admin"}'
        span.set_attribute("db.redis.value_length", len(mock_value))
        span.set_status(StatusCode.OK)
        results["get"] = {"key": "otel_demo:user:1001", "value": mock_value}

    # HGETALL 操作
    with tracer.start_as_current_span(
        "db.redis.hgetall",
        attributes={
            "db.system": "redis",
            "db.operation": "HGETALL",
            "db.redis.key": "otel_demo:session:abc123",
        },
    ) as span:
        logger.info("Redis: HGETALL otel_demo:session:abc123")
        await asyncio.sleep(random.uniform(0.005, 0.02))
        mock_hash = {
            "user_id": "1001",
            "token": "eyJhbGciOiJIUzI1NiJ9...",
            "expires_at": "2026-02-10T10:00:00Z",
            "ip": "192.168.1.100",
        }
        span.set_attribute("db.redis.field_count", len(mock_hash))
        span.set_status(StatusCode.OK)
        results["hgetall"] = {"key": "otel_demo:session:abc123", "fields": mock_hash}

    return results


# ==================== API 端点 ====================


@router.post("/llm-chat", summary="Mock LLM 聊天请求")
async def mock_llm_chat(req: LLMChatRequest):
    """
    模拟 LLM Chat Completion 请求。

    演示手动创建 span 并记录 LLM 相关属性（model、tokens 等），
    通过 span events 追踪请求各阶段。
    """
    otel_trace_id = get_current_trace_id() or "-"
    logger.info(f"[otel-demo] LLM chat request, trace_id={otel_trace_id}, model={req.model}")

    result = await _mock_llm_completion(model=req.model, prompt=req.prompt, max_tokens=req.max_tokens)
    result["otel_trace_id"] = otel_trace_id

    return success_response(data=result)


@router.post("/milvus-search", summary="Mock Milvus 全流程请求")
async def mock_milvus_search(req: MilvusSearchRequest):
    """
    模拟 Milvus 向量数据库完整流程：创建集合 -> 插入向量 -> 搜索 -> 删除集合。

    演示父子 span 的嵌套关系，以及在每个子 span 中记录不同的属性和事件。
    """
    otel_trace_id = get_current_trace_id() or "-"
    logger.info(
        f"[otel-demo] Milvus search pipeline, trace_id={otel_trace_id}, "
        f"collection={req.collection_name}, top_k={req.top_k}"
    )

    result = await _mock_milvus_pipeline(
        collection_name=req.collection_name,
        dimension=req.dimension,
        top_k=req.top_k,
        query_text=req.query_text,
    )
    result["otel_trace_id"] = otel_trace_id

    return success_response(data=result)


@router.get("/mysql-query", summary="Mock MySQL 查询请求")
async def mock_mysql_query():
    """
    模拟 MySQL 数据库查询请求。

    演示数据库操作的 span 记录，包含 db.system、db.statement、db.operation 等语义化属性。
    """
    otel_trace_id = get_current_trace_id() or "-"
    logger.info(f"[otel-demo] MySQL query request, trace_id={otel_trace_id}")

    result = await _mock_mysql_query()
    result["otel_trace_id"] = otel_trace_id

    return success_response(data=result)


@router.get("/redis-query", summary="Mock Redis 查询请求")
async def mock_redis_query():
    """
    模拟 Redis 缓存操作请求（SET / GET / HGETALL）。

    演示 Redis 操作的 span 记录，包含 db.system、db.operation、db.redis.key 等属性。
    """
    otel_trace_id = get_current_trace_id() or "-"
    logger.info(f"[otel-demo] Redis query request, trace_id={otel_trace_id}")

    result = await _mock_redis_query()
    result["otel_trace_id"] = otel_trace_id

    return success_response(data=result)


@router.get("/full-pipeline", summary="完整链路演示")
async def mock_full_pipeline():
    """
    串联调用 LLM -> Milvus -> MySQL -> Redis 四种 mock 操作，
    演示完整的分布式追踪链路。

    所有子操作共享同一个 trace_id，形成完整的调用链路树。
    """
    otel_trace_id = get_current_trace_id() or "-"
    logger.info(f"[otel-demo] Full pipeline start, trace_id={otel_trace_id}")

    pipeline_start = time.perf_counter()
    step_timings = {}

    with tracer.start_as_current_span(
        "demo.full_pipeline",
        attributes={"demo.pipeline_type": "full", "demo.steps": "llm,milvus,mysql,redis"},
    ) as pipeline_span:
        # Step 1: LLM
        t0 = time.perf_counter()
        llm_result = await _mock_llm_completion(model="gpt-4o", prompt="请解释分布式追踪的概念", max_tokens=256)
        step_timings["llm"] = round(time.perf_counter() - t0, 4)
        logger.info(f"[otel-demo] Pipeline step 1/4 (LLM) done, elapsed={step_timings['llm']}s")

        # Step 2: Milvus
        t0 = time.perf_counter()
        milvus_result = await _mock_milvus_pipeline(
            collection_name="pipeline_collection", dimension=768, top_k=5, query_text="分布式追踪"
        )
        step_timings["milvus"] = round(time.perf_counter() - t0, 4)
        logger.info(f"[otel-demo] Pipeline step 2/4 (Milvus) done, elapsed={step_timings['milvus']}s")

        # Step 3: MySQL
        t0 = time.perf_counter()
        mysql_result = await _mock_mysql_query()
        step_timings["mysql"] = round(time.perf_counter() - t0, 4)
        logger.info(f"[otel-demo] Pipeline step 3/4 (MySQL) done, elapsed={step_timings['mysql']}s")

        # Step 4: Redis
        t0 = time.perf_counter()
        redis_result = await _mock_redis_query()
        step_timings["redis"] = round(time.perf_counter() - t0, 4)
        logger.info(f"[otel-demo] Pipeline step 4/4 (Redis) done, elapsed={step_timings['redis']}s")

        total_time = round(time.perf_counter() - pipeline_start, 4)
        pipeline_span.set_attribute("demo.total_time_seconds", total_time)
        pipeline_span.set_status(StatusCode.OK)
        pipeline_span.add_event("pipeline.complete", {"total_time": total_time})

    logger.info(f"[otel-demo] Full pipeline complete, total_time={total_time}s, trace_id={otel_trace_id}")

    return success_response(
        data={
            "otel_trace_id": otel_trace_id,
            "total_time_seconds": total_time,
            "step_timings": step_timings,
            "steps": {
                "llm": {"model": llm_result["model"], "total_tokens": llm_result["usage"]["total_tokens"]},
                "milvus": {
                    "search_result_count": len(milvus_result.get("search_results", [])),
                },
                "mysql": {"row_count": mysql_result["row_count"]},
                "redis": {"operations": list(redis_result.keys())},
            },
        }
    )
