import asyncio
import logging
import json
from abc import ABC, abstractmethod
from typing import Dict, Tuple, Optional, Any, List

import grpc
from grpc.aio import ClientCallDetails, Metadata

# 假设的配置和日志工具
from pkg.logger_tool import logger


# ==========================================
# 1. 定义拦截器 (处理 Auth 和 Meta)
# ==========================================
class AuthInterceptor(grpc.aio.UnaryUnaryClientInterceptor):
    def __init__(self, token_func, app_id: str):
        self.token_func = token_func
        self.app_id = app_id

    async def intercept_unary_unary(self, continuation, client_call_details, request):
        """统一注入 Metadata"""
        metadata = []
        if client_call_details.metadata:
            metadata = list(client_call_details.metadata)

        # 获取最新的 Token (支持动态获取)
        token = self.token_func() if callable(self.token_func) else self.token_func

        metadata.append(('authorization', f"Bearer {token}"))
        metadata.append(('app_id', str(self.app_id)))

        new_details = ClientCallDetails(
            method=client_call_details.method,
            timeout=client_call_details.timeout,
            metadata=metadata,
            credentials=client_call_details.credentials,
            wait_for_ready=client_call_details.wait_for_ready,
        )
        return await continuation(new_details, request)


# ==========================================
# 2. 优化后的连接池
# ==========================================
class AsyncGrpcChannelPool:
    """
    gRPC 异步连接池 (单例模式推荐)
    """
    _instance = None
    _lock = asyncio.Lock()

    def __new__(cls, *args, **kwargs):
        if not cls._instance:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._channels: Dict[str, grpc.aio.Channel] = {}
        self._pool_lock = asyncio.Lock()
        self._default_options = [
            ("grpc.max_concurrent_streams", 1000),
            ("grpc.keepalive_time_ms", 10000),  # 10s 发送一次保活 ping
            ("grpc.keepalive_timeout_ms", 5000),  # 5s 等待 ack
            ("grpc.keepalive_permit_without_calls", 1),  # 允许无调用时 ping
            ("grpc.http2.max_pings_without_data", 0),
            ("grpc.max_receive_message_length", 100 * 1024 * 1024),
            ("grpc.max_send_message_length", 100 * 1024 * 1024),
            ("grpc.enable_retries", 1),
            # 开启 Service Config 以支持重试策略
            ("grpc.service_config", json.dumps({
                "methodConfig": [{
                    "name": [{}],
                    "retryPolicy": {
                        "maxAttempts": 3,
                        "initialBackoff": "0.1s",
                        "maxBackoff": "1s",
                        "backoffMultiplier": 2,
                        "retryableStatusCodes": ["UNAVAILABLE"]
                    }
                }]
            }))
        ]
        self._initialized = True

    async def get_channel(self, endpoint: str) -> grpc.aio.Channel:
        """
        获取 Channel，如果不存在则创建。
        注意：这里不再强制 wait_for_ready，利用 gRPC 的 Lazy connection 机制。
        """
        async with self._pool_lock:
            if endpoint in self._channels:
                channel = self._channels[endpoint]
                # 检查通道是否已彻底关闭
                # 注意：IDLE 或 TRANSIENT_FAILURE 是正常状态，会自动重连，不需要重新创建
                if channel.get_state(try_to_connect=True) != grpc.ChannelConnectivity.SHUTDOWN:
                    return channel
                else:
                    # 如果已 Shutdown，从池中移除，准备重建
                    del self._channels[endpoint]

            # 创建新通道 (非阻塞操作，仅仅是对象实例化)
            channel = grpc.aio.insecure_channel(
                endpoint,
                options=self._default_options
            )
            self._channels[endpoint] = channel
            return channel

    async def close_channel(self, endpoint: str):
        async with self._pool_lock:
            if endpoint in self._channels:
                await self._channels[endpoint].close()
                del self._channels[endpoint]

    async def close_all(self):
        async with self._pool_lock:
            tasks = [channel.close() for channel in self._channels.values()]
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
            self._channels.clear()


# ==========================================
# 3. 优化后的客户端基类
# ==========================================
class BaseGrpcClient(ABC):
    def __init__(self, endpoint: str, app_id: str, token: str):
        self.endpoint = endpoint
        self.pool = AsyncGrpcChannelPool()  # 获取单例
        self.interceptors = [
            AuthInterceptor(token_func=token, app_id=app_id)
        ]
        self._stub = None

    async def _get_stub(self):
        """
        惰性获取 Stub，带拦截器
        """
        if self._stub:
            return self._stub

        # 1. 从池中获取原生 Channel
        raw_channel = await self.pool.get_channel(self.endpoint)

        # 2. 包装拦截器 (重要：intercept_channel 会返回一个新的 Channel 对象包装器)
        intercepted_channel = raw_channel
        if self.interceptors:
            intercepted_channel = grpc.aio.intercept_channel(raw_channel, *self.interceptors)

        # 3. 创建 Stub
        self._stub = self.create_stub(intercepted_channel)
        return self._stub

    @abstractmethod
    def create_stub(self, channel) -> Any:
        pass

    async def wait_for_ready(self, timeout: float = 3.0):
        """可选：在应用启动时显式等待连接就绪"""
        try:
            channel = await self.pool.get_channel(self.endpoint)
            await asyncio.wait_for(channel.channel_ready(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.error(f"Connect to {self.endpoint} timed out")
            raise


# ==========================================
# 4. 具体业务客户端实现 (示例)
# ==========================================

# 假设这是 proto 生成的代码
# from pb.user import user_pb2_grpc, user_pb2

class AsyncUserClient(BaseGrpcClient):
    def create_stub(self, channel):
        # return user_pb2_grpc.UserStub(channel)
        # 模拟 Stub
        class MockStub:
            def __init__(self, chan): self.chan = chan

            async def GetUser(self, request):
                return f"User: {request.id}"

        return MockStub(channel)

    async def get_user_info(self, user_id: int):
        try:
            stub = await self._get_stub()

            # 模拟 Request 对象
            # req = user_pb2.GetUserRequest(id=user_id)
            class MockReq:
                id = user_id

            # 发起调用
            response = await stub.GetUser(MockReq())
            return response
        except grpc.aio.AioRpcError as e:
            logger.error(f"gRPC call failed: {e.code()} - {e.details()}")
            raise


# ==========================================
# 5. 使用示例
# ==========================================

async def main():
    # 模拟配置
    endpoint = "localhost:50051"
    app_id = "my_app_123"
    api_token = "secret_token_abc"

    # 1. 初始化客户端
    user_client = AsyncUserClient(endpoint, app_id, api_token)

    # (可选) 预热连接：确保服务可用，否则抛出异常
    try:
        # 启动时可以做一次检查，运行时不需要每次都查
        # 注意：这里需要你本地真有这个端口在监听，否则会超时
        # await user_client.wait_for_ready(timeout=2.0)
        pass
    except Exception as e:
        logger.warning(f"Initial connection check failed: {e}")

    # 2. 发起调用
    logger.info("Starting request...")
    try:
        result = await user_client.get_user_info(1001)
        logger.info(f"Result: {result}")
    except Exception as e:
        logger.error(f"Request Error: {e}")

    # 3. 模拟并发调用 (测试连接池锁性能)
    tasks = [user_client.get_user_info(i) for i in range(5)]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    logger.info(f"Batch results: {results}")

    # 4. 程序退出前清理
    await AsyncGrpcChannelPool().close_all()
    logger.info("Pool closed.")


if __name__ == '__main__':
    # 配置基本的 logging
    logging.basicConfig(level=logging.INFO)
    asyncio.run(main())
