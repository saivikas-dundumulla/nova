from __future__ import annotations

from functools import lru_cache

from fastapi import Depends, Header, HTTPException, status

from app.auth.base import Authenticator, AuthError, User
from app.auth.stub import EnvUserAuthenticator


@lru_cache(maxsize=1)
def get_authenticator() -> Authenticator:
    """DI seam — swap the concrete implementation here (e.g. Entra OIDC) later."""
    return EnvUserAuthenticator()


async def get_current_user(
    authorization: str | None = Header(default=None),
    auth: Authenticator = Depends(get_authenticator),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = authorization.split(" ", 1)[1].strip()
    try:
        return await auth.resolve_token(token)
    except AuthError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        ) from e
