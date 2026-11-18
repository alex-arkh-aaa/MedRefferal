"""Unit-тесты для app/security.py (gateway)."""
import pytest
from app.security import (
    get_password_hash,
    verify_password,
    decode_token,
    verify_token,
)


# ==================== Хеширование ====================

def test_hash_returns_string():
    h = get_password_hash("secret")
    assert isinstance(h, str)
    assert h.startswith("$argon2")


def test_hash_unique():
    assert get_password_hash("x") != get_password_hash("x")


def test_verify_correct():
    h = get_password_hash("secret")
    assert verify_password("secret", h) is True


def test_verify_wrong():
    h = get_password_hash("secret")
    assert verify_password("wrong", h) is False


# ==================== decode_token ====================

def test_decode_valid():
    from tests.conftest import make_token
    token = make_token({"sub": "a@b.c", "user_id": 1, "role": "agent"})
    payload = decode_token(token)
    assert payload is not None
    assert payload["sub"] == "a@b.c"
    assert payload["user_id"] == 1
    assert payload["role"] == "agent"


def test_decode_garbage():
    assert decode_token("not-a-jwt") is None


def test_decode_wrong_secret():
    from tests.conftest import make_token
    token = make_token({"sub": "a@b.c"}, secret="another-secret")
    assert decode_token(token) is None


def test_decode_expired():
    import time
    from tests.conftest import make_token
    # exp в прошлом
    token = make_token({"sub": "a@b.c", "exp": int(time.time()) - 100})
    assert decode_token(token) is None


# ==================== verify_token ====================

def test_verify_token_valid():
    from tests.conftest import make_token
    token = make_token({"sub": "a@b.c"})
    assert verify_token(token) is True


def test_verify_token_invalid():
    assert verify_token("garbage") is False