import grpc
from typing import Optional, List


class GrpcChannelManager:
    """
    gRPC 通道管理器（实例版）
    每个实例对应一个具体的下游服务地址。
    """
    # 全局注册表：用于记录所有创建的 Manager 实例，方便统一关闭
    _instances: List["GrpcChannelManager"] = []

    def __init__(self, host: str, port: int, service_name: str = "Unknown"):
        self.host = host
        self.port = port
        self.service_name = service_name
        self._channel: grpc.aio.Channel | None= None

        # ✅ 初始化时自动注册到全局列表
        GrpcChannelManager._instances.append(self)

    def get_channel(self) -> grpc.aio.Channel:
        """
        获取 Channel。
        ✅ 无需再传参数，直接使用实例内部的配置。
        """
        if self._channel is None:
            target = f"{self.host}:{self.port}"
            print(f"🔌 [gRPC] Connecting to {self.service_name} at {target}...")

            self._channel = grpc.aio.insecure_channel(
                target,
                options=[
                    ("grpc.max_send_message_length", 10 * 1024 * 1024),
                    ("grpc.keepalive_time_ms", 10000),
                    ("grpc.keepalive_timeout_ms", 5000),
                    ("grpc.keepalive_permit_without_calls", 1),
                ]
            )
        return self._channel

    async def close(self):
        """关闭当前实例的连接"""
        if self._channel:
            print(f"🛑 [gRPC] Closing connection to {self.service_name}...")
            await self._channel.close()
            self._channel = None

    @classmethod
    async def close_all(cls):
        """
        ♻️ 静态方法：遍历所有注册的实例并关闭
        供 FastAPI 生命周期使用
        """
        print(f"🧹 Closing all {len(cls._instances)} gRPC managers...")
        for manager in cls._instances:
            await manager.close()


"""
class UserGrpcClient:
    def __init__(self):
        # 获取单例 Channel
        self.channel = GrpcChannelManager.get_channel()
        # 创建 Stub
        self.stub = user_pb2_grpc.UserServiceStub(self.channel)

    async def get_user_info(self, user_id: int):
        # 调用远程 GetUser 方法
        request = user_pb2.GetUserRequest(id=user_id)
        
        # 可以在这里注入通用的 Metadata，比如 trace_id 或 token
        metadata = (("x-client-id", "fastapi-app"),)
        
        response = await self.stub.GetUser(
            request, 
            timeout=settings.GRPC_TIMEOUT,
            metadata=metadata
        )
        
        # 将 Proto Message 转换为 Python Dict 或 Pydantic Model 返回，解耦 Proto
        return {
            "id": response.id,
            "username": response.username,
            "email": response.email
        }

"""
