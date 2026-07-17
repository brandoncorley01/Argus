from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Header, Request, Response, status
from sqlalchemy.orm import Session, selectinload

from app.api.deps import (
    RequireFounder,
    _client_ip,
    auth_http_error,
    clear_session_cookie,
    get_auth_service,
    get_current_principal,
    require_csrf,
    set_session_cookie,
)
from app.core.settings import Settings, get_settings
from app.db.session import get_db
from app.models import User
from app.schemas.auth import (
    AssignRoleRequest,
    AssignRoleResponse,
    CreateUserRequest,
    CreateUserResponse,
    CurrentUserResponse,
    LoginRequest,
    LoginResponse,
)
from app.services.auth_service import AuthenticatedPrincipal, AuthError, AuthService

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    auth: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> LoginResponse:
    try:
        user, tokens = auth.login(
            identifier=body.identifier,
            password=body.password,
            ip_address=_client_ip(request),
            user_agent=request.headers.get("user-agent"),
            request_id=request_id,
        )
    except AuthError as exc:
        raise auth_http_error(exc) from exc

    set_session_cookie(response, tokens, settings)
    roles = auth.user_roles(user)
    return LoginResponse(
        user_id=user.id,
        username=user.username,
        roles=roles,
        csrf_token=tokens.csrf_token,
        expires_at=tokens.expires_at,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    principal: AuthenticatedPrincipal = Depends(require_csrf),
    auth: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> None:
    try:
        auth.logout(principal=principal, request_id=request_id)
    except AuthError as exc:
        raise auth_http_error(exc) from exc
    clear_session_cookie(response, settings)


@router.get("/me", response_model=CurrentUserResponse)
def me(principal: AuthenticatedPrincipal = Depends(get_current_principal)) -> CurrentUserResponse:
    return CurrentUserResponse(
        id=principal.user.id,
        username=principal.user.username,
        email=principal.user.email,
        is_active=principal.user.is_active,
        roles=sorted(principal.roles, key=lambda role: role.value),
        session_expires_at=principal.session.expires_at,
    )


@router.post("/users", response_model=CreateUserResponse, status_code=status.HTTP_201_CREATED)
def create_user(
    body: CreateUserRequest,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    auth: AuthService = Depends(get_auth_service),
    db: Session = Depends(get_db),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> CreateUserResponse:
    try:
        user = auth.create_user(
            actor=principal,
            username=body.username,
            password=body.password,
            email=body.email,
            roles=body.roles,
            request_id=request_id,
        )
    except AuthError as exc:
        raise auth_http_error(exc) from exc

    refreshed = db.get(User, user.id, options=(selectinload(User.roles),))
    assert refreshed is not None
    return CreateUserResponse(
        id=refreshed.id,
        username=refreshed.username,
        email=refreshed.email,
        roles=[role.role for role in refreshed.roles],
    )


@router.post("/users/{user_id}/roles", response_model=AssignRoleResponse)
def assign_role(
    user_id: uuid.UUID,
    body: AssignRoleRequest,
    principal: AuthenticatedPrincipal = Depends(RequireFounder),
    auth: AuthService = Depends(get_auth_service),
    request_id: str | None = Header(default=None, alias="X-Request-ID"),
) -> AssignRoleResponse:
    try:
        row = auth.assign_role(
            actor=principal, user_id=user_id, role=body.role, request_id=request_id
        )
    except AuthError as exc:
        raise auth_http_error(exc) from exc
    return AssignRoleResponse(user_id=row.user_id, role=row.role)
