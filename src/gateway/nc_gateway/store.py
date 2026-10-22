"""Session store a rate limiter nad Redisem (kontrakt NC-007 kap. 3 a 4.6).

* Klíč záznamu ``nc:bff:sess:<sha256(sid) hex>``, hodnota šifrovaná
  :class:`~nc_gateway.crypto.SessionCipher` s AAD = klíč záznamu (záznam nejde
  přesunout pod jiné ``sid``).
* Index uživatele ``nc:bff:user:<user_id>`` = set hashů jeho sessions.
* Zámek obnovy tokenu ``nc:bff:lock:<hash>``.
* Rate limit ``nc:bff:rl:<scope>:<id>:<okno>`` (pevné okno, INCR + EXPIRE).

Jakákoli chyba Redisu se převede na :class:`StoreUnavailableError` → 503.
Žádná paměťová náhrada neexistuje (fail closed).
"""

from __future__ import annotations

import hashlib
import json
import logging
import math
import secrets
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from typing import Any, Final, Literal

from redis.asyncio import Redis
from redis.exceptions import RedisError, WatchError

from nc_gateway.crypto import DecryptionError, SessionCipher

logger = logging.getLogger("nc_gateway.store")

SESSION_PREFIX: Final = "nc:bff:sess:"
USER_INDEX_PREFIX: Final = "nc:bff:user:"
LOCK_PREFIX: Final = "nc:bff:lock:"
RATE_PREFIX: Final = "nc:bff:rl:"

_RELEASE_LOCK_LUA: Final = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""


class StoreUnavailableError(RuntimeError):
    """Redis není dostupný – gateway odpoví 503."""


async def _guard[T](operation: Awaitable[T]) -> T:
    try:
        return await operation
    except (TimeoutError, RedisError, OSError) as exc:
        raise StoreUnavailableError(type(exc).__name__) from exc


def sid_hash(sid: str) -> str:
    return hashlib.sha256(sid.encode("ascii")).hexdigest()


def session_ref(hashed: str) -> str:
    """Zkrácený odkaz na session pro audit (prvních 16 hex sha256(sid))."""
    return hashed[:16]


@dataclass
class SessionRecord:
    accessToken: str
    refreshToken: str
    userId: str
    organizationId: str
    role: str
    csrfSecret: str
    createdAt: float
    lastSeenAt: float
    ipHash: str
    uaHash: str
    coreSessionId: str | None = None

    def to_bytes(self) -> bytes:
        return json.dumps(asdict(self), separators=(",", ":")).encode("utf-8")

    @classmethod
    def from_bytes(cls, raw: bytes) -> SessionRecord:
        data = json.loads(raw.decode("utf-8"))
        if not isinstance(data, dict):
            raise ValueError("session record")
        return cls(**data)


@dataclass
class LoadResult:
    status: Literal["ok", "missing", "expired"]
    hashed: str
    record: SessionRecord | None = None
    expiry_reason: str | None = None


class SessionStore:
    def __init__(
        self,
        redis: Redis,
        cipher: SessionCipher,
        *,
        idle_timeout: int,
        absolute_timeout: int,
        clock: Callable[[], float],
    ) -> None:
        self._redis = redis
        self._cipher = cipher
        self._idle = idle_timeout
        self._absolute = absolute_timeout
        self._clock = clock

    @staticmethod
    def record_key(hashed: str) -> str:
        return f"{SESSION_PREFIX}{hashed}"

    @staticmethod
    def user_key(user_id: str) -> str:
        return f"{USER_INDEX_PREFIX}{user_id}"

    def _ttl(self, record: SessionRecord, now: float) -> int:
        remaining_absolute = record.createdAt + self._absolute - now
        return max(1, math.ceil(min(self._idle, remaining_absolute)))

    def expires_at(self, record: SessionRecord) -> float:
        return record.createdAt + self._absolute

    def idle_expires_at(self, record: SessionRecord) -> float:
        return min(record.lastSeenAt + self._idle, self.expires_at(record))

    async def create(self, record: SessionRecord) -> tuple[str, str]:
        """Uloží novou session pod **nové** náhodné ``sid``. Vrátí (sid, hash)."""
        sid = secrets.token_urlsafe(32)
        hashed = sid_hash(sid)
        await self.save(hashed, record)
        user_key = self.user_key(record.userId)
        await _guard(self._redis.sadd(user_key, hashed))
        await _guard(self._redis.expire(user_key, self._absolute))
        return sid, hashed

    async def save(self, hashed: str, record: SessionRecord) -> None:
        key = self.record_key(hashed)
        token = self._cipher.encrypt(record.to_bytes(), key.encode("ascii"))
        await _guard(self._redis.set(key, token, ex=self._ttl(record, self._clock())))

    async def load(self, sid: str) -> LoadResult:
        hashed = sid_hash(sid)
        key = self.record_key(hashed)
        raw: Any = await _guard(self._redis.get(key))
        if raw is None:
            return LoadResult("missing", hashed)
        try:
            token = raw.decode("ascii") if isinstance(raw, bytes) else str(raw)
            plaintext, kid = self._cipher.decrypt(token, key.encode("ascii"))
            record = SessionRecord.from_bytes(plaintext)
        except (DecryptionError, ValueError, TypeError, UnicodeDecodeError) as exc:
            # Nečitelný záznam (např. odebraný klíč) = neplatná session.
            logger.warning("session_record_unreadable", extra={"reason": type(exc).__name__})
            await _guard(self._redis.delete(key))
            return LoadResult("missing", hashed)
        now = self._clock()
        if now - record.createdAt >= self._absolute:
            await self.delete(hashed, record.userId)
            return LoadResult("expired", hashed, record, "absolute")
        if now - record.lastSeenAt >= self._idle:
            await self.delete(hashed, record.userId)
            return LoadResult("expired", hashed, record, "idle")
        if kid != self._cipher.primary_kid:
            await self.update(hashed, lambda _record: None)  # přešifrovat aktuálním klíčem
        return LoadResult("ok", hashed, record)

    async def update(self, hashed: str, mutate: Callable[[SessionRecord], None]) -> SessionRecord | None:
        """Atomická úprava záznamu (WATCH/MULTI). Vrátí aktuální záznam, nebo ``None``.

        Souběžné požadavky téže session (např. ``touch`` a obnova tokenu)
        se tak nepřepisují – zastaralý ``touch`` nemůže vrátit do Redisu
        starý refresh token (core by jeho reuse vyhodnotil jako krádež).
        """
        key = self.record_key(hashed)

        async def attempt() -> SessionRecord | None:
            async with self._redis.pipeline(transaction=True) as pipe:
                while True:
                    try:
                        await pipe.watch(key)
                        raw: Any = await pipe.get(key)
                        if raw is None:
                            await pipe.reset()  # type: ignore[no-untyped-call]
                            return None
                        token = raw.decode("ascii") if isinstance(raw, bytes) else str(raw)
                        try:
                            plaintext, _ = self._cipher.decrypt(token, key.encode("ascii"))
                            record = SessionRecord.from_bytes(plaintext)
                        except (DecryptionError, ValueError, TypeError):
                            await pipe.reset()  # type: ignore[no-untyped-call]
                            return None  # nečitelný záznam = neplatná session
                        mutate(record)
                        sealed = self._cipher.encrypt(record.to_bytes(), key.encode("ascii"))
                        pipe.multi()  # type: ignore[no-untyped-call]
                        pipe.set(key, sealed, ex=self._ttl(record, self._clock()))
                        await pipe.execute()
                        return record
                    except WatchError:
                        continue

        return await _guard(attempt())

    async def touch(self, hashed: str) -> SessionRecord | None:
        now = self._clock()

        def mutate(record: SessionRecord) -> None:
            record.lastSeenAt = now

        return await self.update(hashed, mutate)

    async def delete(self, hashed: str, user_id: str | None) -> None:
        await _guard(self._redis.delete(self.record_key(hashed)))
        if user_id:
            await _guard(self._redis.srem(self.user_key(user_id), hashed))

    async def delete_all_for_user(self, user_id: str) -> int:
        user_key = self.user_key(user_id)
        members: Any = await _guard(self._redis.smembers(user_key))
        hashes = [m.decode("ascii") if isinstance(m, bytes) else str(m) for m in members]
        if hashes:
            await _guard(self._redis.delete(*(self.record_key(h) for h in hashes)))
        await _guard(self._redis.delete(user_key))
        return len(hashes)

    async def acquire_lock(self, hashed: str, ttl_ms: int = 10_000) -> str | None:
        token = secrets.token_hex(16)
        acquired = await _guard(self._redis.set(f"{LOCK_PREFIX}{hashed}", token, nx=True, px=ttl_ms))
        return token if acquired else None

    async def release_lock(self, hashed: str, token: str) -> None:
        await _guard(self._redis.eval(_RELEASE_LOCK_LUA, 1, f"{LOCK_PREFIX}{hashed}", token))

    async def lock_held(self, hashed: str) -> bool:
        return bool(await _guard(self._redis.exists(f"{LOCK_PREFIX}{hashed}")))


@dataclass
class RateDecision:
    allowed: bool
    retry_after: int


class RateLimiter:
    def __init__(self, redis: Redis, clock: Callable[[], float]) -> None:
        self._redis = redis
        self._clock = clock

    def _key(self, scope: str, ident: str, window: int) -> tuple[str, int]:
        now = self._clock()
        index = int(now // window)
        retry_after = max(1, math.ceil((index + 1) * window - now))
        return f"{RATE_PREFIX}{scope}:{ident}:{index}", retry_after

    async def hit(self, scope: str, ident: str, limit: int, window: int) -> RateDecision:
        """Započítá jeden požadavek a řekne, zda je v limitu."""
        key, retry_after = self._key(scope, ident, window)
        pipe = self._redis.pipeline(transaction=True)
        pipe.incr(key)
        pipe.expire(key, window + 1)
        results: list[Any] = await _guard(pipe.execute())
        return RateDecision(int(results[0]) <= limit, retry_after)

    async def exceeded(self, scope: str, ident: str, limit: int, window: int) -> RateDecision:
        """Jen přečte čítač (pro limit neúspěchů – započítává se zvlášť)."""
        key, retry_after = self._key(scope, ident, window)
        value: Any = await _guard(self._redis.get(key))
        count = int(value) if value is not None else 0
        return RateDecision(count < limit, retry_after)

    async def record(self, scope: str, ident: str, window: int) -> None:
        key, _ = self._key(scope, ident, window)
        pipe = self._redis.pipeline(transaction=True)
        pipe.incr(key)
        pipe.expire(key, window + 1)
        await _guard(pipe.execute())
