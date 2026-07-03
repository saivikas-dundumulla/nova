from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast

from jose import JWTError, jwt
from passlib.hash import bcrypt

from app.auth.base import AuthError, Role, User
from app.config.settings import Settings, get_settings


class EnvUserAuthenticator:
    """Stub `Authenticator` — reads users from `Settings.auth_users` and issues short-lived JWTs.

    Swap for an OIDC-backed implementation without touching the rest of the app; the
    Authenticator Protocol in `app.auth.base` is the seam.
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._s = settings or get_settings()

    async def authenticate(self, username: str, password: str) -> User:
        users = self._s.auth_users
        record = users.get(username)
        if record is None or not bcrypt.verify(password, record.password_hash):
            raise AuthError("invalid credentials")
        if record.role not in ("enduser", "ombuds"):
            raise AuthError(f"unsupported role: {record.role}")
        return User(
            id=username,
            username=username,
            role=cast(Role, record.role),
            email=record.email,
        )

    async def issue_token(self, user: User) -> str:
        now = datetime.now(UTC)
        payload = {
            "sub": user.id,
            "username": user.username,
            "role": user.role,
            "email": user.email,
            "iat": int(now.timestamp()),
            "exp": int((now + timedelta(minutes=self._s.session_ttl_minutes)).timestamp()),
        }
        return jwt.encode(payload, self._s.session_jwt_secret, algorithm=self._s.session_jwt_alg)

    async def resolve_token(self, token: str) -> User:
        try:
            payload = jwt.decode(
                token,
                self._s.session_jwt_secret,
                algorithms=[self._s.session_jwt_alg],
            )
        except JWTError as e:
            raise AuthError(f"invalid token: {e}") from e
        role = payload.get("role")
        if role not in ("enduser", "ombuds"):
            raise AuthError(f"invalid role in token: {role}")
        return User(
            id=str(payload["sub"]),
            username=str(payload.get("username") or payload["sub"]),
            role=cast(Role, role),
            email=payload.get("email"),
        )
