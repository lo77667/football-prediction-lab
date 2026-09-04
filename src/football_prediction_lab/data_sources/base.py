import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any


class RateLimitExceeded(Exception):
    pass


def rate_limited(calls: int, period: float):
    """Simple async rate limiter decorator allowing `calls` per `period` seconds."""
    interval = period / calls

    def decorator(func: Callable[..., Awaitable]):
        last_called = {"time": 0.0}
        lock = asyncio.Lock()

        async def wrapper(*args, **kwargs):
            async with lock:
                now = time.monotonic()
                elapsed = now - last_called["time"]
                if elapsed < interval:
                    wait = interval - elapsed
                    await asyncio.sleep(wait)
                last_called["time"] = time.monotonic()
            return await func(*args, **kwargs)

        return wrapper

    return decorator


@dataclass
class DataSource:
    name: str

    async def fetch(self, *args, **kwargs) -> dict[str, Any]:
        raise NotImplementedError
