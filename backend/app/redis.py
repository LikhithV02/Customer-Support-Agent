"""Shared Redis state: rate limits, per-conversation turn locks, the global
in-flight-turn semaphore and per-customer daily token budgets.

Everything that must be consistent across pods lives here, which is what lets
the backend run as many stateless replicas. With `REDIS_URL` unset (dev/tests
only — rejected in prod) an in-process fakeredis is used instead.
"""

from __future__ import annotations

import re
import time
import uuid
from datetime import datetime, timezone

from redis.asyncio import Redis

from app.config import get_settings

_client: Redis | None = None


def get_redis() -> Redis:
    global _client
    if _client is None:
        settings = get_settings()
        if settings.redis_url:
            _client = Redis.from_url(
                settings.redis_url,
                decode_responses=True,
                max_connections=256,
                socket_timeout=5,
                socket_connect_timeout=5,
                health_check_interval=30,
            )
        else:
            from fakeredis import FakeAsyncRedis

            _client = FakeAsyncRedis(decode_responses=True)
    return _client


def set_redis(client: Redis | None) -> None:
    """Swap the client (tests)."""
    global _client
    _client = client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


# ---------------------------------------------------------------------------
# Fixed-window rate limiter ("10/minute", "5/second", "100/hour", "1000/day")
# ---------------------------------------------------------------------------

_PERIODS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}
_LIMIT_RE = re.compile(r"^\s*(\d+)\s*/\s*(second|minute|hour|day)s?\s*$")


def parse_limit(spec: str) -> tuple[int, int]:
    m = _LIMIT_RE.match(spec)
    if not m:
        raise ValueError(f"bad rate limit spec: {spec!r}")
    return int(m.group(1)), _PERIODS[m.group(2)]


async def hit_rate_limit(key: str, spec: str) -> tuple[bool, int]:
    """Count one hit. Returns (allowed, seconds_until_reset)."""
    limit, period = parse_limit(spec)
    window = int(time.time()) // period
    rkey = f"rl:{key}:{period}:{window}"
    r = get_redis()
    pipe = r.pipeline()
    pipe.incr(rkey)
    pipe.expire(rkey, period + 1)
    count, _ = await pipe.execute()
    reset_in = period - int(time.time()) % period
    return count <= limit, reset_in


# ---------------------------------------------------------------------------
# Per-conversation turn lock — one agent turn at a time per conversation
# ---------------------------------------------------------------------------

_RELEASE_LOCK = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""


async def acquire_turn_lock(conversation_id: str, ttl_s: float) -> str | None:
    token = uuid.uuid4().hex
    ok = await get_redis().set(
        f"lock:conv:{conversation_id}", token, nx=True, px=int(ttl_s * 1000)
    )
    return token if ok else None


async def release_turn_lock(conversation_id: str, token: str) -> None:
    await get_redis().eval(_RELEASE_LOCK, 1, f"lock:conv:{conversation_id}", token)


# ---------------------------------------------------------------------------
# Global in-flight turn semaphore (self-healing: entries expire)
# ---------------------------------------------------------------------------

_SEM_KEY = "sem:turns"
_ACQUIRE_SEM = """
local now = tonumber(ARGV[1])
redis.call('zremrangebyscore', KEYS[1], '-inf', now - tonumber(ARGV[2]))
if redis.call('zcard', KEYS[1]) < tonumber(ARGV[3]) then
  redis.call('zadd', KEYS[1], now, ARGV[4])
  return 1
end
return 0
"""


async def acquire_turn_slot(limit: int, ttl_s: float) -> str | None:
    token = uuid.uuid4().hex
    ok = await get_redis().eval(
        _ACQUIRE_SEM, 1, _SEM_KEY, time.time(), ttl_s, limit, token
    )
    return token if ok else None


async def release_turn_slot(token: str) -> None:
    await get_redis().zrem(_SEM_KEY, token)


async def turns_in_flight() -> int:
    return int(await get_redis().zcard(_SEM_KEY))


# ---------------------------------------------------------------------------
# Per-customer daily token budget
# ---------------------------------------------------------------------------

# The same counters also keep a global total across all customers, which the
# public demo uses as a spend cap (`DEMO_GLOBAL_DAILY_TOKEN_BUDGET`).
_GLOBAL = "__all__"


def _budget_key(customer_id: str) -> str:
    day = datetime.now(timezone.utc).strftime("%Y%m%d")
    return f"budget:{customer_id}:{day}"


async def customer_tokens_today(customer_id: str) -> int:
    return int(await get_redis().get(_budget_key(customer_id)) or 0)


async def global_tokens_today() -> int:
    return await customer_tokens_today(_GLOBAL)


async def add_customer_tokens(customer_id: str, tokens: int) -> None:
    pipe = get_redis().pipeline()
    for key in (_budget_key(customer_id), _budget_key(_GLOBAL)):
        pipe.incrby(key, tokens)
        pipe.expire(key, 2 * 86400)
    await pipe.execute()
