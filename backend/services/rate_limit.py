"""Rate-limit dependency helper.

We intentionally avoid the `@limiter.limit(...)` decorator pattern because it
breaks FastAPI's Pydantic body resolution on JSON-body endpoints (a known
recurring bug in past iterations). Instead we expose a Dependency that wraps
SlowAPI's underlying limits engine:

    @router.post("/x", dependencies=[Depends(rate_limit("10/minute"))])
    async def x(body: SomeModel): ...

Backed by SlowAPI's in-memory storage (default) or Redis if `RATE_LIMIT_REDIS=1`
is set. The exception type raised on overrun is `slowapi.errors.RateLimitExceeded`
so the existing exception handler registered in server.py continues to work.
"""
from __future__ import annotations

import os
from typing import Callable, Dict

from fastapi import Request
from limits import parse_many
from limits.aio.storage import MemoryStorage as AsyncMemoryStorage
from limits.aio.strategies import MovingWindowRateLimiter
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# Singleton attached to app.state.limiter (legacy compatibility with
# routes/auth_routes.py which still imports `limiter` from there).
limiter = Limiter(key_func=get_remote_address)

# Independent moving-window limiter for the Dependency path so we don't have
# to dig into SlowAPI internals.
_storage = AsyncMemoryStorage()
_strategy = MovingWindowRateLimiter(_storage)

# parse_many results cached per spec to avoid re-parsing on every request.
_parsed_cache: Dict[str, list] = {}


def _key(request: Request, scope: str) -> str:
    return f"{scope}:{get_remote_address(request)}"


def rate_limit(spec: str, scope: str = "default") -> Callable:
    """Return a FastAPI dependency enforcing `spec` (e.g. '10/minute').

    `scope` lets you isolate quotas across endpoints (login vs register vs match).
    """
    parsed = _parsed_cache.setdefault(spec, list(parse_many(spec)))

    async def _dep(request: Request) -> None:
        for item in parsed:
            ok = await _strategy.hit(item, _key(request, scope), cost=1)
            if not ok:
                raise RateLimitExceeded(item)
    return _dep


# Convenience pre-built deps for common scopes (so usage stays terse).
def login_limit():  return rate_limit(os.environ.get("RL_LOGIN", "20/minute"), "login")
def register_limit(): return rate_limit(os.environ.get("RL_REGISTER", "10/minute"), "register")
def match_limit():  return rate_limit(os.environ.get("RL_MATCH", "30/minute"), "match")
def forgot_limit():  return rate_limit(os.environ.get("RL_FORGOT", "5/minute"), "forgot")
