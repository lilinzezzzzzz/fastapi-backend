from collections.abc import Callable
from contextlib import AbstractAsyncContextManager

from redis.asyncio import Redis

SessionProvider = Callable[[], AbstractAsyncContextManager[Redis]]
