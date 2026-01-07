import hashlib
import socket
import uuid

from snowflake import SnowflakeGenerator

from pkg.toolkit.logger import logger


def auto_snowflake_node_id() -> int:
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

    def __init__(self, node_id: int):
        if not node_id:
            raise ValueError("node_id cannot be empty")
        self._generator = SnowflakeGenerator(node_id)

    def generate(self) -> int:
        return next(self._generator)

    def generate_batch(self, count: int) -> list[int]:
        return [next(self._generator) for _ in range(count)]


snowflake_id_generator = SnowflakeIDGenerator(node_id=auto_snowflake_node_id())
