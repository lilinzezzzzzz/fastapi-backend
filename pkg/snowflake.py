from snowflake import SnowflakeGenerator


class SnowflakeIDGenerator:
    _instance: "SnowflakeIDGenerator | None" = None
    _generator: SnowflakeGenerator | None = None

    def __new__(cls, node_id: int = 1):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._generator = SnowflakeGenerator(node_id)
        return cls._instance

    def generate(self) -> int:
        return next(self._generator)

    def generate_batch(self, count: int) -> list[int]:
        return [next(self._generator) for _ in range(count)]


"""
用法示例:
snowflake_id_generator = SnowflakeIDGenerator()


def generate_snowflake_id() -> int:
    return snowflake_id_generator.generate()
"""
