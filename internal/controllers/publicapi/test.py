import asyncio
import random
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import numpy as np
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from internal.core.exception import AppException
from internal.dao.user import user_dao
from internal.infra.anyio_task import anyio_task_manager
from internal.infra.database import get_session
from internal.models.user import User
from pkg.loguru_logger import logger
from pkg.response import response_factory
from pkg.stream_control import stream_with_chunk_control

router = APIRouter(prefix="/test", tags=["public v1 test"])


@router.get("/test_raise_exception", summary="测试异常")
async def test_raise_exception(_: Request):
    # 如果触发fastapi.HTTPException会有限被main.py的exception_handler捕获，
    # 如果是Exception会被middleware的exception.py捕获
    raise Exception("test_raise_exception")


@router.get("/test_raise_app_exception", summary="测试APP异常")
async def test_raise_app_exception():
    raise AppException(code=500, detail="test_raise_app_exception")


@router.get(
    "/test_custom_response_class_basic_types", summary="测试自定义响应类-基本类型"
)
async def test_custom_response_class_basic_types(_: Request):
    return response_factory.success(
        data={
            "large_int": 2**53 + 1,  # 超过JS安全整数
            "normal_int": 42,
            "float_num": 3.1415926535,
            "boolean": True,
            "none_value": None,
        }
    )


@router.get(
    "/test_custom_response_class_containers", summary="测试自定义响应类-容器类型"
)
async def test_custom_response_class_containers(_: Request):
    return response_factory.success(
        data=[
            {"set_data": {1, 2, 3}},  # 集合转列表
            (4, 5, 6),  # 元组转列表
            [datetime(2023, 1, 1), datetime(2023, 1, 1, tzinfo=timezone.utc)],
        ]
    )


@router.get("/test_custom_response_class_nested", summary="测试自定义响应类-嵌套结构")
async def test_custom_response_class_nested(_: Request):
    return response_factory.success(
        data={
            "level1": {
                "level2": [
                    {
                        "mixed_types": [
                            Decimal("999.999"),
                            {uuid.uuid4(): datetime.now()},
                            [2**60, {"deep": True}],
                        ]
                    }
                ]
            }
        }
    )


@router.get(
    "/test_custom_response_class_third_party", summary="测试自定义响应类-第三方库"
)
async def test_custom_response_class_third_party(_: Request):
    return response_factory.success(
        data={
            "numpy_array": np.array([1.1, 2.2, 3.3]),  # NumPy数组
            "numpy_int": np.int64(2**63 - 1),
        }
    )


@router.get(
    "/test_custom_response_class_edge_cases", summary="测试自定义响应类-边缘情况"
)
async def test_custom_response_class_edge_cases(_: Request):
    return response_factory.success(
        data={
            "numpy_array": np.array([1.1, 2.2, 3.3]),  # NumPy数组
            "numpy_int": np.int64(2**63),
        }
    )


@router.get("/test_custom_response_class_complex", summary="测试自定义响应类-复杂情况")
async def test_custom_response_class_complex(_: Request):
    return response_factory.success(
        data={
            "empty_dict": {},
            "empty_list": [],
            "zero": Decimal("0.000000"),
            "max_precision": Decimal("0.12345678901234567890123456789"),
        }
    )


@router.get(
    "/test_custom_response_class_special_types", summary="测试自定义响应类-特殊类型"
)
async def test_custom_response_class_special_types(_: Request):
    return response_factory.success(
        data={
            "decimal": Decimal("123.4567890123456789"),
            "bytes": b"\x80abc\xff",
            "datetime_naive": datetime.now(),
            "big_int": 2**60,
            "timedelta": timedelta(days=1, seconds=3600),
        }
    )


async def async_task():
    """可以继承上下文的trace_id"""
    logger.info("async_task_trace_id-test")
    await asyncio.sleep(10)


@router.get("/test_contextvars_on_asyncio_task", summary="测试Contextvars在Asyncio任务")
async def test_contextvars_on_asyncio_task():
    await anyio_task_manager.add_task("test", coro_func=async_task)
    return response_factory.success()


@router.get("/test_dao", summary="测试DAO")
async def test_dao():
    unique_hex = uuid.uuid4().hex[:16]  # 缩短长度
    test_user: User = user_dao.init_by_phone(
        str(random.randint(10000000000, 99999999999))
    )
    test_user.account = f"lilinze_{unique_hex}"
    test_user.username = f"lilinze_{unique_hex}"
    await test_user.save(session_provider=get_session)

    try:
        # 1. 验证基础查询
        created_user: User = (
            await user_dao.create(User, session_provider=get_session)
            .eq_(User.id, test_user.id)
            .first()
        )
        assert created_user.id == test_user.id
        logger.info("test created success")

        # 2. 测试各种查询操作符
        # eq
        user = await user_dao.querier.eq_(User.id, test_user.id).first()
        assert user.id == test_user.id
        logger.info("test eq success")

        # ne
        ne_users = await user_dao.querier.ne_(User.id, test_user.id).all()
        assert all(u.id != test_user.id for u in ne_users)
        logger.info("test ne success")

        # gt
        gt_users: list[User] = (
            await user_dao.querier(session_provider=get_session)
            .gt_(User.id, test_user.id)
            .all()
        )
        assert all(u.id > test_user.id for u in gt_users)
        logger.info("test gt success")

        # lt
        lt_users = await user_dao.querier.lt_(User.id, test_user.id).all()
        assert all(u.id < test_user.id for u in lt_users)
        logger.info("test lt success")

        # ge
        ge_users = await user_dao.querier.ge_(User.id, test_user.id).all()
        assert all(u.id >= test_user.id for u in ge_users)
        logger.info("test ge success")

        # le
        le_users = await user_dao.querier.le_(User.id, test_user.id).all()
        assert all(u.id <= test_user.id for u in le_users)
        logger.info("test le success")

        # in_ 测试
        in_users = await user_dao.querier.in_(User.id, [test_user.id]).all()
        assert len(in_users) == 1
        logger.info("test in_ success")

        # like 测试
        like_users: list[User] = await user_dao.querier.like(
            User.username, "lilinze"
        ).all()
        assert all("lilinze" in u.username for u in like_users)
        logger.info("test like success")

        # is_null 测试（确保测试时deleted_at为null）
        null_users = await user_dao.querier.is_null(User.deleted_at).all()
        assert any(u.deleted_at is None for u in null_users)
        logger.info("test is_null success")

        # 4. 计数测试
        count = await user_dao.counter.ge_(User.id, 0).count()
        assert count >= 1
        logger.info("test count success")

        # AND 组合
        and_users = await (
            user_dao.querier.eq_(User.username, test_user.username)
            .eq_(User.username, test_user.username)
            .eq_(User.account, test_user.account)
            .first()
        )
        assert and_users.username == test_user.username, (
            and_users.account == test_user.account
        )
        logger.info("test and success")

        # where 组合
        where_user = await user_dao.querier.where(
            User.username == test_user.username, User.account == test_user.account
        ).first()
        assert where_user.username == test_user.username, (
            where_user.account == test_user.account
        )
        logger.info("test where success")

        # OR 组合
        or_users = await user_dao.querier.or_(
            User.username == test_user.username, User.account == "invalid_account"
        ).all()
        assert len(or_users) >= 1
        logger.info("test or success")

        # BETWEEN 组合
        between_users = await user_dao.querier.between_(
            User.id, test_user.id - 1, test_user.id + 1
        ).all()
        assert len(between_users) >= 1
        logger.info("test between success")

        # 3. 更新操作测试
        # 显式使用新查询器避免缓存问题
        updated_name = f"updated_name_{unique_hex}"
        await (
            user_dao.updater.eq_(User.id, test_user.id)
            .update(username=updated_name)
            .execute()
        )
        # 重新查询验证更新
        updated_user = await user_dao.querier.eq_(User.id, test_user.id).first()
        assert updated_user.username == updated_name
        logger.info("test update-1 success")

        # 显式使用新查询器避免缓存问题
        updated_name = f"updated_name_{unique_hex}"
        await (
            user_dao.updater.eq_(User.id, test_user.id)
            .update(**{"username": updated_name})
            .execute()
        )
        # 重新查询验证更新
        updated_user = await user_dao.querier.eq_(User.id, test_user.id).first()
        assert updated_user.username == updated_name
        logger.info("test update-2 success")
    except Exception:
        raise
    else:
        return response_factory.success()
    finally:
        test_user.deleted_at = datetime.now()
        await test_user.save(session_provider=get_session)


async def text_generator():
    """异步生成器：逐字返回文本"""
    answer_text = "演示用异步生成器陆续返回文本答案。"
    for c in answer_text:
        yield c
        await asyncio.sleep(0.05)


@router.get("/test/sse-stream", summary="测试SSE")
async def test_sse():
    async def event_generator():
        # 1. 请求进入，先返回：hello，正在查询资料
        yield "data: hello，正在查询资料\n\n"
        await asyncio.sleep(2)

        # 2. sleep，返回：正在组织回答
        yield "data: 正在组织回答\n\n"
        await asyncio.sleep(2)

        yield "data: 开始回答\n\n"
        yield "data: =========\n\n"
        # 3. 逐字返回文本答案
        answer_text = "演示了SSE的基本用法, 逐字返回文本答案"
        for c in answer_text:
            yield f"data: {c}\n\n"
            await asyncio.sleep(0.05)

        yield "data: =========\n\n"

        # 3. sleep，用异步生成器陆续返回文本答案
        async for char in text_generator():
            yield f"data: {char}\n\n"

        yield "data: =========\n\n"
        yield "data: 回答结束\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


async def fake_stream_generator():
    for i in range(5):
        yield f"data: chunk {i}\n\n"
        await asyncio.sleep(3)


@router.get("/chat/sse-stream/timeout", summary="测试SSE超时控制")
async def chat_endpoint(request: Request):
    wrapped_generator = stream_with_chunk_control(
        request, generator=fake_stream_generator(), chunk_timeout=2.0, is_sse=True
    )
    return StreamingResponse(wrapped_generator, media_type="text/event-stream")
