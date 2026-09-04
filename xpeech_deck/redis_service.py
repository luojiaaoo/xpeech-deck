"""通用 Redis 存储。"""

from __future__ import annotations

from redis.asyncio import Redis
from redis.exceptions import RedisError

from .errors import ServiceUnavailableError


class RedisStore:
    """封装 Redis 连接及统一的不可用错误。"""

    def __init__(self, url: str, password: str = "") -> None:
        self._client = Redis.from_url(
            url,
            password=password or None,
            decode_responses=True,
        )

    async def set(self, key: str, value: str, ttl_seconds: int | None = None) -> None:
        try:
            await self._client.set(
                key,
                value,
                ex=ttl_seconds,
            )
        except RedisError as exc:
            raise ServiceUnavailableError("Redis 服务不可用") from exc

    async def get(self, key: str) -> str | None:
        try:
            return await self._client.get(key)
        except RedisError as exc:
            raise ServiceUnavailableError("Redis 服务不可用") from exc

    async def close(self) -> None:
        await self._client.aclose()
