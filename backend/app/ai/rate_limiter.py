import asyncio
import random
from typing import Callable, Awaitable

MAX_RETRIES = 3
BASE_DELAY = 1.0


async def with_backoff(
    fn: Callable[[], Awaitable[str]],
    is_retryable: Callable[[Exception], bool] | None = None,
) -> str:
    is_retryable = is_retryable or _default_retryable
    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            return await fn()
        except Exception as exc:
            last_exc = exc
            if not is_retryable(exc) or attempt == MAX_RETRIES - 1:
                raise
            delay = BASE_DELAY * (2**attempt) + random.uniform(0, 0.5)
            await asyncio.sleep(delay)
    raise last_exc  # type: ignore[misc]


def _default_retryable(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(k in msg for k in ("429", "rate", "quota", "timeout", "503", "502"))
