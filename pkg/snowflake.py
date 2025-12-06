from snowflake import SnowflakeGenerator


class SnowflakeIDGenerator:
    """Snowflake ID 生成器工具类，在 lifespan 中初始化后通过全局变量使用"""

    def __init__(self, node_id: int = 1):
        self._generator = SnowflakeGenerator(node_id)

    def generate(self) -> int:
        return next(self._generator)

    def generate_batch(self, count: int) -> list[int]:
        return [next(self._generator) for _ in range(count)]
