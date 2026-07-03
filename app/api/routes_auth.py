from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.audit.logger import get_audit
from app.auth.base import Authenticator, AuthError, User
from app.auth.deps import get_authenticator, get_current_user

router = APIRouter(prefix="", tags=["auth"])


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str
    user: User


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    auth: Authenticator = Depends(get_authenticator),
) -> LoginResponse:
    audit = get_audit()
    try:
        user = await auth.authenticate(body.username, body.password)
    except AuthError as e:
        audit.emit("login_failed", user_id=body.username, message="invalid credentials")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(e)) from e

    token = await auth.issue_token(user)
    audit.emit("login", user_id=user.id, role=user.role, status="ok")
    return LoginResponse(token=token, user=user)


@router.post("/logout")
async def logout(user: User = Depends(get_current_user)) -> dict[str, str]:
    get_audit().emit("logout", user_id=user.id, role=user.role, status="ok")
    return {"status": "ok"}


@router.get("/me", response_model=User)
async def me(user: User = Depends(get_current_user)) -> User:
    return user
