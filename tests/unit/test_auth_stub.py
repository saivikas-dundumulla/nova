from __future__ import annotations

import pytest

from app.auth.base import AuthError
from app.auth.stub import EnvUserAuthenticator
from tests.conftest import TEST_PASSWORD


@pytest.mark.asyncio
async def test_authenticate_success():
    auth = EnvUserAuthenticator()
    user = await auth.authenticate("enduser1", TEST_PASSWORD)
    assert user.username == "enduser1"
    assert user.role == "enduser"


@pytest.mark.asyncio
async def test_authenticate_bad_password():
    auth = EnvUserAuthenticator()
    with pytest.raises(AuthError):
        await auth.authenticate("enduser1", "wrong")


@pytest.mark.asyncio
async def test_authenticate_unknown_user():
    auth = EnvUserAuthenticator()
    with pytest.raises(AuthError):
        await auth.authenticate("nope", TEST_PASSWORD)


@pytest.mark.asyncio
async def test_token_roundtrip():
    auth = EnvUserAuthenticator()
    user = await auth.authenticate("ombuds1", TEST_PASSWORD)
    token = await auth.issue_token(user)
    resolved = await auth.resolve_token(token)
    assert resolved.id == user.id
    assert resolved.role == "ombuds"


@pytest.mark.asyncio
async def test_resolve_token_bad_signature():
    auth = EnvUserAuthenticator()
    with pytest.raises(AuthError):
        await auth.resolve_token("not.a.real.token")
