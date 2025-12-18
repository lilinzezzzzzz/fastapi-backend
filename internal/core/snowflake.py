from pkg.snowflake import SnowflakeIDGenerator

_snowflake_id_generator: SnowflakeIDGenerator | None = None


def init_snowflake_id_generator(node_id: int = 1):
    global _snowflake_id_generator
    _snowflake_id_generator = SnowflakeIDGenerator(node_id)


def generate_snowflake_id() -> int:
    if _snowflake_id_generator is None:
        raise Exception("Snowflake ID Generator is not initialized")

    return _snowflake_id_generator.generate()


def generate_snowflake_id_batch(count: int) -> list[int]:
    if _snowflake_id_generator is None:
        raise Exception("Snowflake ID Generator is not initialized")

    return _snowflake_id_generator.generate_batch(count)
