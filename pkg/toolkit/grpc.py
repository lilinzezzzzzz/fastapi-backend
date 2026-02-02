import grpc

from pkg.logger import logger


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
            logger.info(f"🔌 [gRPC] Connecting to {target}...")

            self._channel = grpc.aio.insecure_channel(
                target,
                options=[
                    ("grpc.max_send_message_length", 10 * 1024 * 1024),
                    ("grpc.keepalive_time_ms", 10000),
                    ("grpc.keepalive_timeout_ms", 5000),
                    ("grpc.keepalive_permit_without_calls", 1),
                ],
            )
        return self._channel

    async def close(self):
        if self._channel:
            target = f"{self.host}:{self.port}"
            logger.info(f"🛑 [gRPC] Closing connection to {target}...")
            await self._channel.close()
            self._channel = None
