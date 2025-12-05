import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from functools import wraps
from typing import TypeVar, Callable, Any

import grpc
from grpc.aio import Metadata

from pkg.logger_tool import logger

T = TypeVar('T')


class GrpcConnectionError(Exception):
    """gRPC 连接异常"""
    pass


class GrpcCallError(Exception):
    """gRPC 调用异常"""

    def __init__(self, message: str, code: grpc.StatusCode | None = None, details: str | None = None):
        super().__init__(message)
        self.code = code
        self.details = details


class AsyncGrpcChannelPool:
    """异步 gRPC 连接池管理器"""
    _channels: dict[str, tuple[grpc.aio.Channel, datetime]] = {}
    _lock = asyncio.Lock()
    _default_options = [
        ("grpc.max_concurrent_streams", 1000),
        ("grpc.http2.max_pings_without_data", 0),
        ("grpc.keepalive_time_ms", 10000),
        ("grpc.keepalive_timeout_ms", 5000),
        ("grpc.keepalive_permit_without_calls", 1),
        ("grpc.max_receive_message_length", 100 * 1024 * 1024),  # 100MB
        ("grpc.max_send_message_length", 100 * 1024 * 1024),
        ("grpc.enable_retries", 1),
        ("grpc.service_config", """{"loadBalancingConfig": [{"round_robin":{}}]}""")
    ]

    @classmethod
    async def get_channel(
            cls,
            service_name: str,
            endpoint: str,
            *,
            options: list[tuple[str, Any]] | None = None,
            force_refresh: bool = False,
            health_check_timeout: float = 5.0
    ) -> grpc.aio.Channel:
        """
        获取或创建 gRPC 异步通道

        Args:
            service_name: 服务唯一标识
            endpoint: 服务地址 (格式: host:port)
            options: 自定义通道参数 (会与默认参数合并)
            force_refresh: 强制创建新连接
            health_check_timeout: 健康检查超时时间(秒)

        Returns:
            grpc.aio.Channel: 可用的 gRPC 通道

        Raises:
            GrpcConnectionError: 连接失败时抛出
        """
        async with cls._lock:
            # 存在可用连接且不强制刷新
            if not force_refresh and service_name in cls._channels:
                channel, last_checked = cls._channels[service_name]

                # 30分钟内创建的连接直接复用
                if datetime.now() - last_checked < timedelta(minutes=30):
                    return channel

                # 检查连接健康状态
                if await cls._check_channel_health(channel, health_check_timeout):
                    cls._channels[service_name] = (channel, datetime.now())
                    return channel
                else:
                    await cls._safe_close_channel(channel)
                    del cls._channels[service_name]

            # 创建新连接
            merged_options = cls._default_options + (options or [])
            channel = grpc.aio.insecure_channel(
                endpoint,
                options=merged_options,
            )

            # 等待连接就绪
            try:
                await asyncio.wait_for(
                    channel.channel_ready(),
                    timeout=health_check_timeout
                )
            except asyncio.TimeoutError:
                await cls._safe_close_channel(channel)
                raise GrpcConnectionError(f"Connection timeout to {service_name} at {endpoint}")
            except grpc.RpcError as e:
                await cls._safe_close_channel(channel)
                raise GrpcConnectionError(f"Failed to connect to {service_name} at {endpoint}: {e}")

            cls._channels[service_name] = (channel, datetime.now())
            logger.info(f"Created new gRPC channel to {service_name} at {endpoint}")
            return channel

    @classmethod
    async def _check_channel_health(
            cls,
            channel: grpc.aio.Channel,
            timeout: float
    ) -> bool:
        """检查通道健康状态"""
        try:
            state = channel.get_state(try_to_connect=True)
            if state == grpc.ChannelConnectivity.READY:
                return True

            if state in (grpc.ChannelConnectivity.SHUTDOWN, grpc.ChannelConnectivity.TRANSIENT_FAILURE):
                return False

            # 等待状态变化
            await asyncio.wait_for(
                channel.wait_for_state_change(state),
                timeout=timeout
            )
            # 再次检查状态
            new_state = channel.get_state()
            return new_state == grpc.ChannelConnectivity.READY

        except asyncio.TimeoutError:
            logger.warning(f"Health check timeout for channel")
            return False
        except Exception as e:
            logger.warning(f"Health check failed: {e}")
            return False

    @staticmethod
    async def _safe_close_channel(channel: grpc.aio.Channel) -> None:
        """安全关闭通道"""
        try:
            await channel.close()
        except Exception as e:
            logger.warning(f"Error closing channel: {e}")

    @classmethod
    async def close_channel(cls, service_name: str) -> None:
        """关闭指定服务的连接"""
        async with cls._lock:
            if service_name in cls._channels:
                channel, _ = cls._channels.pop(service_name)
                await cls._safe_close_channel(channel)
                logger.info(f"Closed gRPC channel for {service_name}")

    @classmethod
    async def close_all(cls) -> None:
        """优雅关闭所有连接"""
        async with cls._lock:
            if not cls._channels:
                return
            await asyncio.gather(
                *[cls._safe_close_channel(channel) for channel, _ in cls._channels.values()],
                return_exceptions=True
            )
            cls._channels.clear()
            logger.info("Closed all gRPC channels")


def grpc_retry(
        max_retries: int = 3,
        retry_delay: float = 0.5,
        retryable_codes: tuple[grpc.StatusCode, ...] = (
                grpc.StatusCode.UNAVAILABLE,
                grpc.StatusCode.DEADLINE_EXCEEDED,
                grpc.StatusCode.RESOURCE_EXHAUSTED,
        )
) -> Callable:
    """gRPC 调用重试装饰器"""

    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            last_exception = None
            for attempt in range(max_retries + 1):
                try:
                    return await func(*args, **kwargs)
                except grpc.RpcError as e:
                    last_exception = e
                    if e.code() not in retryable_codes or attempt == max_retries:
                        raise GrpcCallError(
                            f"gRPC call failed: {e.details()}",
                            code=e.code(),
                            details=e.details()
                        )
                    logger.warning(
                        f"gRPC call failed (attempt {attempt + 1}/{max_retries + 1}): {e.code()}, retrying..."
                    )
                    await asyncio.sleep(retry_delay * (attempt + 1))  # 指数退避
            raise last_exception

        return wrapper

    return decorator


class BaseGrpcClient(ABC):
    """gRPC 客户端基类"""

    def __init__(
            self,
            service_name: str,
            host: str,
            port: int,
            *,
            app_id: str = "",
            default_timeout: float = 30.0
    ):
        self.service_name = service_name
        self.endpoint = f"{host}:{port}"
        self.app_id = app_id
        self.default_timeout = default_timeout
        self._channel: grpc.aio.Channel | None = None
        self._stub = None
        self._connect_lock = asyncio.Lock()

    def build_metadata(self, token: str | None = None, **extra) -> Metadata:
        """构建 gRPC 元数据"""
        metadata = []
        if token:
            metadata.append(('authorization', f"Bearer {token}"))
        if self.app_id:
            metadata.append(('app_id', self.app_id))
        for key, value in extra.items():
            metadata.append((key, str(value)))
        return Metadata(*metadata)

    async def _ensure_connected(self) -> None:
        """确保连接可用"""
        async with self._connect_lock:
            need_reconnect = (
                    self._channel is None or
                    self._stub is None or
                    self._channel.get_state(try_to_connect=False) in (
                        grpc.ChannelConnectivity.SHUTDOWN,
                        grpc.ChannelConnectivity.TRANSIENT_FAILURE,
                    )
            )
            if need_reconnect:
                logger.info(f"Connecting gRPC channel to {self.service_name}")
                self._channel = await AsyncGrpcChannelPool.get_channel(
                    self.service_name, self.endpoint
                )
                self._stub = self.create_stub(self._channel)

    @abstractmethod
    def create_stub(self, channel: grpc.aio.Channel):
        """由子类实现具体的 stub 创建"""
        pass

    async def close(self) -> None:
        """关闭客户端连接"""
        await AsyncGrpcChannelPool.close_channel(self.service_name)
        self._channel = None
        self._stub = None

    async def __aenter__(self):
        await self._ensure_connected()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass  # 连接由连接池管理，不在此处关闭


# ==================== 使用示例 ====================
# 假设有一个 user.proto 生成的 user_pb2 和 user_pb2_grpc
#
# from protos import user_pb2, user_pb2_grpc
#
# class UserGrpcClient(BaseGrpcClient):
#     """用户服务 gRPC 客户端"""
#
#     def __init__(self, host: str, port: int, app_id: str = ""):
#         super().__init__("user-service", host, port, app_id=app_id)
#
#     def create_stub(self, channel: grpc.aio.Channel):
#         return user_pb2_grpc.UserServiceStub(channel)
#
#     @grpc_retry(max_retries=3)
#     async def get_user(self, user_id: int, token: str | None = None) -> user_pb2.User:
#         """获取用户信息"""
#         await self._ensure_connected()
#         request = user_pb2.GetUserRequest(user_id=user_id)
#         response = await self._stub.GetUser(
#             request,
#             metadata=self.build_metadata(token),
#             timeout=self.default_timeout
#         )
#         return response
#
#     @grpc_retry(max_retries=2)
#     async def create_user(self, name: str, email: str, token: str) -> user_pb2.User:
#         """创建用户"""
#         await self._ensure_connected()
#         request = user_pb2.CreateUserRequest(name=name, email=email)
#         response = await self._stub.CreateUser(
#             request,
#             metadata=self.build_metadata(token),
#             timeout=self.default_timeout
#         )
#         return response
#
#
# # === 在 FastAPI 中使用 ===
# from contextlib import asynccontextmanager
# from fastapi import FastAPI
#
# user_client: UserGrpcClient | None = None
#
# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     global user_client
#     user_client = UserGrpcClient("localhost", 50051, app_id="my-app")
#     yield
#     await AsyncGrpcChannelPool.close_all()
#
# app = FastAPI(lifespan=lifespan)
#
# @app.get("/users/{user_id}")
# async def get_user(user_id: int):
#     try:
#         user = await user_client.get_user(user_id)
#         return {"id": user.id, "name": user.name}
#     except GrpcCallError as e:
#         return {"error": str(e), "code": e.code.name if e.code else None}
#     except GrpcConnectionError as e:
#         return {"error": f"Connection failed: {e}"}

