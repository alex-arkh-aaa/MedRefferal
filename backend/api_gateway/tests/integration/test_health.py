"""Integration-тесты для health и HTML-роутов."""


async def test_health(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "API Gateway is healthy"


async def test_api_health(client):
    r = await client.get("/api/health")
    assert r.status_code == 200
    assert "API Gateway API" in r.json()["status"]


async def test_root_returns_html(client):
    """GET / — публичный, отдаёт index.html."""
    r = await client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    assert "MedReferral" in r.text or "<!DOCTYPE html>" in r.text


async def test_index_returns_html(client):
    r = await client.get("/index")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


async def test_404_returns_html(client):
    """Несуществующий путь без токена → редирект на / (307)."""
    r = await client.get("/nonexistent-page-xyz", follow_redirects=False)
    assert r.status_code in (302, 307)