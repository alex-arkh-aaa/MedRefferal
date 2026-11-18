import pytest
from tests.conftest import make_token


async def test_excluded_path_no_rate_limit(client, fake_redis):
    """/health исключён из rate limiting."""
    fake_redis.flushall()
    for _ in range(5):
        r = await client.get("/health")
        assert r.status_code == 200
    # В Redis не должно быть ключей для /health
    keys = fake_redis.keys("*")
    assert not any("/health" in k for k in keys)
