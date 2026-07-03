from __future__ import annotations

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel

Role = Literal["enduser", "ombuds"]


class User(BaseModel):
    id: str
    username: str
    role: Role
    email: str | None = None


class AuthError(Exception):
    """Raised when authentication fails or a token cannot be resolved."""


@runtime_checkable
class Authenticator(Protocol):
    async def authenticate(self, username: str, password: str) -> User: ...
    async def issue_token(self, user: User) -> str: ...
    async def resolve_token(self, token: str) -> User: ...
