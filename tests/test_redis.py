"""公开 Redis 临时键值接口测试。"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from xpeech_deck.app import OAUTH_CONTEXT_KEY_PREFIX, OAUTH_CONTEXT_TTL_SECONDS
from xpeech_deck.redis_service import RedisStore

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class FakeRedisClient:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}

    async def set(self, key: str, value: str, *, ex: int) -> bool:
        self.values[key] = value
        self.expirations[key] = ex
        return True

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def aclose(self) -> None:
        pass


@pytest.fixture
def fake_redis(app, settings):
    store = RedisStore(settings.redis_url, settings.redis_password)
    client = FakeRedisClient()
    store._client = client
    app.state.redis = store
    return client


def test_public_redis_write_and_read_need_no_token(client, fake_redis):
    write_response = client.put(
        "/api/public/redis/oauth2context/oauth-state",
        json={"value": "temporary-value"},
    )

    assert write_response.status_code == 200
    assert write_response.json() == {
        "key": "oauth-state",
        "expires_in": OAUTH_CONTEXT_TTL_SECONDS,
    }
    storage_key = f"{OAUTH_CONTEXT_KEY_PREFIX}oauth-state"
    assert fake_redis.values[storage_key] == "temporary-value"
    assert fake_redis.expirations[storage_key] == 60

    read_response = client.get("/api/public/redis/oauth2context/oauth-state")
    assert read_response.status_code == 200
    assert read_response.json() == {
        "key": "oauth-state",
        "value": "temporary-value",
    }


def test_public_redis_read_returns_404_when_key_is_absent(client, fake_redis):
    response = client.get("/api/public/redis/oauth2context/missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "Redis key 不存在或已过期"}


def test_redis_compose_defaults_match_example_config():
    example = tomllib.loads(
        (PROJECT_ROOT / "conf.toml.example").read_text(encoding="utf-8")
    )
    compose = (PROJECT_ROOT / "compose.redis.yaml").read_text(encoding="utf-8")

    assert example["redis_url"] == "redis://localhost:6379/0"
    assert '"127.0.0.1:6379:6379"' in compose
    assert f'${{REDIS_PASSWORD:-{example["redis_password"]}}}' in compose
