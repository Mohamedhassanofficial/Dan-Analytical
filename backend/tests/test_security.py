"""Security primitives — password hashing + JWT round-trip."""
from __future__ import annotations

import time

import pytest
from jose import JWTError

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)


def test_password_hash_and_verify():
    h = hash_password("correct-horse-battery-staple")
    assert h != "correct-horse-battery-staple"
    assert verify_password("correct-horse-battery-staple", h)
    assert not verify_password("wrong-password", h)


def test_access_token_round_trip():
    tok = create_access_token(user_id=42, is_admin=True)
    payload = decode_token(tok)
    assert payload.sub == "42"
    assert payload.typ == "access"
    assert payload.is_admin is True


def test_refresh_token_round_trip():
    tok = create_refresh_token(user_id=7, is_admin=False)
    payload = decode_token(tok)
    assert payload.sub == "7"
    assert payload.typ == "refresh"
    assert payload.is_admin is False


def test_invalid_token_raises():
    with pytest.raises(JWTError):
        decode_token("not-a-real-jwt")


def test_jti_is_unique():
    """Same user, two tokens → different jti."""
    t1 = create_access_token(user_id=1)
    t2 = create_access_token(user_id=1)
    assert decode_token(t1).jti != decode_token(t2).jti
