import asyncio
from abc import ABC, abstractmethod
from datetime import datetime, timedelta

import grpc
from grpc.aio import Metadata

from pkg.logger_tool import logger


class AsyncGrpcChannelPool:
    _channels: dict[str, tuple[grpc.aio.Channel, datetime]] = {}
    _lock = asyncio.Lock()  # 异步锁保证线程安全
    _default_options = [
        ("grpc.max_concurrent_streams", 1000),
        ("grpc.http2.max_pings_without_data", 0),
        ("grpc.keepalive_time_ms", 10000),
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
            options: list[tuple[str, any]] | None = None,
            force_refresh: bool = False,
            health_check_timeout: float = 5.0
    ) -> grpc.aio.Channel:
        """
        获取或创建gRPC异步通道

        Args:
            service_name: 服务唯一标识
            endpoint: 服务地址 (格式: host:port)
            options: 自定义通道参数 (会与默认参数合并)
            force_refresh: 强制创建新连接
            health_check_timeout: 健康检查超时时间(秒)
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
                    cls._channels[service_name] = (channel, datetime.now())  # 更新时间戳
                    return channel
                else:
                    await channel.close()  # 关闭不健康的连接

            # 创建新连接
            merged_options = cls._default_options + (options or [])
            channel = grpc.aio.insecure_channel(
                endpoint,
                options=merged_options,
            )

            # 等待连接就绪（非阻塞式）
            try:
                await asyncio.wait_for(
                    channel.channel_ready(),
                    timeout=health_check_timeout
                )
            except (TimeoutError, grpc.RpcError):
                await channel.close()
                raise Exception(f"Failed to connect to {service_name} at {endpoint}")

            cls._channels[service_name] = (channel, datetime.now())
            return channel

    @staticmethod
    async def _check_channel_health(
            channel: grpc.aio.Channel,
            timeout: float
    ) -> bool:
        """改进的健康检查方法"""
        try:
            state = channel.get_state()
            if state == grpc.ChannelConnectivity.READY:
                return True

            return await asyncio.wait_for(
                channel.wait_for_state_change(state),
                timeout=timeout
            ) == grpc.ChannelConnectivity.READY

        except (TimeoutError, grpc.RpcError):
            logger.warning(f"Failed to check health of {channel}")
            return False

    @classmethod
    async def close_all(cls):
        """优雅关闭所有连接"""
        async with cls._lock:
            await asyncio.gather(
                *[channel.close() for channel, _ in cls._channels.values()],
                return_exceptions=True
            )
            cls._channels.clear()


class BaseGrpcClient(ABC):
    def __init__(self, service_name: str, host: str, port: int):
        self.service_name: str = service_name
        self.endpoint: str = f"{host}:{port}"
        self._channel: grpc.aio.Channel | None = None
        self._stub = None

    @staticmethod
    def build_grpc_metadata(token):
        return Metadata(
            ('authorization', f"bearer {token}"),
            ("app_id", "setting.APP_ID")
        )

    async def _ensure_connected(self):
        if self._channel is None or self._channel.get_state(True) in (
                grpc.ChannelConnectivity.SHUTDOWN,
                grpc.ChannelConnectivity.TRANSIENT_FAILURE,
        ):
            logger.info(f"Reconnecting grpc channel to {self.service_name}")
            self._channel = await AsyncGrpcChannelPool.get_channel(
                self.service_name, self.endpoint
            )
            self._stub = self.create_stub(self._channel)

    @abstractmethod
    def create_stub(self, channel):
        """由子类实现具体的stub创建"""
        pass


class AsyncUserClient(BaseGrpcClient):
    def __init__(self, host: str, port: int):
        super().__init__("user", host, port)

    def create_stub(self, channel):
        ...

# 使用示例：
# async_user_client = AsyncUserClient(setting.GRPC_HOST, setting.GRPC_PORT)
