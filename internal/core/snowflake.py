from pkg.snowflake import SnowflakeIDGenerator

snowflake_id_generator: SnowflakeIDGenerator | None = None


def init_snowflake_id_generator(node_id: int = 1):
    global snowflake_id_generator
    snowflake_id_generator = SnowflakeIDGenerator(node_id)


def generate_snowflake_id() -> int:
    if snowflake_id_generator is None:
        raise Exception("Snowflake ID Generator is not initialized")

    return snowflake_id_generator.generate()


def generate_snowflake_id_batch(count: int) -> list[int]:
    if snowflake_id_generator is None:
        raise Exception("Snowflake ID Generator is not initialized")

    return snowflake_id_generator.generate_batch(count)
