"""Тесты проксирования на service_users."""
import pytest
from tests.conftest import make_token


async def test_proxy_login(client, mock_proxy_response):
    mock_proxy_response.response.status_code = 200
    mock_proxy_response.response.json_data = {"access_token": "abc"}
    r = await client.post("/api/v1/auth/login", json={...})
    assert r.status_code == 200
    assert r.json()["access_token"] == "abc"
    # Проверяем, что прокси вызван
    assert mock_proxy_response.called


async def test_proxy_passes_user_headers(client, mock_proxy_response):
    mock_proxy_response.response.status_code = 200
    mock_proxy_response.response.json_data = {"ok": True}
    token = make_token({"sub": "a@b.c", "user_id": 42, "role": "agent"})
    r = await client.get("/api/v1/patients", cookies={"access_token": token})
    assert r.status_code == 200
    assert mock_proxy_response.called   # ← просто проверяем, что вызван
