import grpc


class GrpcChannel:
    """
    gRPC 通道管理器
    职责：仅负责维护 Host:Port 的物理连接生命周期。
    """

    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self._channel: grpc.aio.Channel | None = None

    def get_channel(self) -> grpc.aio.Channel:
        if self._channel is None:
            target = f"{self.host}:{self.port}"
            # 日志现在更客观，只描述连接动作
            print(f"🔌 [gRPC] Connecting to {target}...")

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
        if self._channel:
            target = f"{self.host}:{self.port}"
            print(f"🛑 [gRPC] Closing connection to {target}...")
            await self._channel.close()
            self._channel = None


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
