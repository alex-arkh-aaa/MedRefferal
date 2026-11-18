import time
import pytest
from datetime import datetime, timedelta, timezone
from jose import jwt
import os

from app.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    decode_token,
    verify_token,
    get_current_user_id,
)
from fastapi import HTTPException


# ==================== Хеширование паролей ====================

def test_get_password_hash_returns_string():
    h = get_password_hash("secret123")
    assert isinstance(h, str)
    assert h != "secret123"
    assert h.startswith("$argon2")


def test_get_password_hash_is_unique_per_call():
    """Argon2 использует соль — два хеша одного пароля разные."""
    h1 = get_password_hash("secret123")
    h2 = get_password_hash("secret123")
    assert h1 != h2


def test_verify_password_correct():
    h = get_password_hash("secret123")
    assert verify_password("secret123", h) is True


def test_verify_password_wrong():
    h = get_password_hash("secret123")
    assert verify_password("wrong-password", h) is False


def test_verify_password_empty():
    h = get_password_hash("secret123")
    assert verify_password("", h) is False


# ==================== JWT ====================

def test_create_access_token_returns_string():
    token = create_access_token({"sub": "a@b.c", "user_id": 1}, expires_delta=60)
    assert isinstance(token, str)
    assert token.count(".") == 2  # JWT = header.payload.signature


def test_create_access_token_contains_payload():
    token = create_access_token(
        {"sub": "a@b.c", "user_id": 42, "role": "agent"}, expires_delta=60
    )
    payload = decode_token(token)
    assert payload is not None
    assert payload["sub"] == "a@b.c"
    assert payload["user_id"] == 42
    assert payload["role"] == "agent"
    assert "exp" in payload


def test_decode_token_invalid_returns_none():
    assert decode_token("not-a-jwt") is None
    assert decode_token("aaa.bbb.ccc") is None


def test_decode_token_wrong_secret_returns_none():
    """Токен, подписанный другим секретом, не должен декодироваться."""
    bad = jwt.encode(
        {"sub": "a@b.c"},
        "another-secret",
        algorithm="HS256",
    )
    assert decode_token(bad) is None


def test_verify_token_true_for_valid():
    token = create_access_token({"sub": "a@b.c"}, expires_delta=60)
    assert verify_token(token) is True


def test_verify_token_false_for_invalid():
    assert verify_token("garbage") is False


def test_token_expired():
    """Токен с expires_delta=-1 минута уже истёк."""
    token = create_access_token({"sub": "a@b.c"}, expires_delta=-1)
    assert decode_token(token) is None
    assert verify_token(token) is False


# ==================== get_current_user_id ====================

def test_get_current_user_id_ok():
    token = create_access_token({"sub": "1", "user_id": 7}, expires_delta=60)
    # ВАЖНО: get_current_user_id читает payload["sub"], а не user_id
    # В твоём коде sub — это email. Проверим, что int("7") не падает,
    # если sub — число. Но у тебя sub=email. См. примечание ниже.
    # Поэтому этот тест проверим на токене, где sub — число.
    token = create_access_token({"sub": "7"}, expires_delta=60)
    assert get_current_user_id(token) == 7


def test_get_current_user_id_no_sub_raises():
    token = create_access_token({"user_id": 7}, expires_delta=60)
    with pytest.raises(HTTPException) as exc:
        get_current_user_id(token)
    assert exc.value.status_code == 401


def test_get_current_user_id_invalid_token_raises():
    with pytest.raises(HTTPException) as exc:
        get_current_user_id("garbage")
    assert exc.value.status_code == 401