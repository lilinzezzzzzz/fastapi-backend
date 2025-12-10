import hashlib
import os
import socket
import uuid

from snowflake import SnowflakeGenerator

from pkg.loguru_logger import logger


def _get_auto_node_id() -> int:
    """基于机器信息自动生成 node_id (0-1023)"""
    try:
        mac = uuid.getnode()
        return mac % 1024
    except Exception as e:
        logger.warning(f"Failed to get mac address: {e}")
        hostname = socket.gethostname()
        return int(hashlib.md5(hostname.encode()).hexdigest(), 16) % 1024


class SnowflakeIDGenerator:
    """Snowflake ID 生成器工具类"""

    def __init__(self, node_id: int | None = None):
        if node_id is None:
            # 优先从环境变量读取，否则自动生成
            env_node_id = os.getenv("SNOWFLAKE_NODE_ID")
            node_id = int(env_node_id) if env_node_id else _get_auto_node_id()
        self._generator = SnowflakeGenerator(node_id)

    def generate(self) -> int:
        return next(self._generator)

    def generate_batch(self, count: int) -> list[int]:
        return [next(self._generator) for _ in range(count)]


snowflake_id_generator = SnowflakeIDGenerator()
