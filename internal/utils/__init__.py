from internal.infra.redis_session import get_redis
from pkg.cache_tool.client import new_cache_client

cache_client = new_cache_client(session_provider=get_redis)
