import importlib

import pytest
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials

import auth


def credentials(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def test_api_token_is_read_from_environment(monkeypatch):
    original_token = auth.API_TOKEN
    monkeypatch.setenv("API_TOKEN", "configured-api-token")

    importlib.reload(auth)

    try:
        assert auth.API_TOKEN == "configured-api-token"
    finally:
        auth.API_TOKEN = original_token


def test_configured_api_token_is_required(monkeypatch):
    monkeypatch.setattr(auth, "API_TOKEN", "configured-api-token")

    user = auth.get_current_user(credentials("configured-api-token"))

    assert user.user_id == "local-dev-user"
    with pytest.raises(HTTPException) as error:
        auth.get_current_user(credentials("local-dev-token"))
    assert error.value.status_code == 401


def test_missing_api_token_rejects_requests(monkeypatch):
    monkeypatch.setattr(auth, "API_TOKEN", "")

    with pytest.raises(HTTPException) as error:
        auth.get_current_user(None)

    assert error.value.status_code == 401
