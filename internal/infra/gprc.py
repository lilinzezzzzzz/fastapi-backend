from pkg.grpc import GrpcChannel

grpc_channel: GrpcChannel | None = None
channels: list[GrpcChannel] = []


def init_grpc_channel(*, host: str, port: int):
    """
    初始化gRPC 通道
    """
    global grpc_channel
    grpc_channel = GrpcChannel(host, port)
    channels.append(grpc_channel)


async def close_grpc_channel():
    """
    关闭gRPC通道
    """
    for channel in channels:
        await channel.close()
