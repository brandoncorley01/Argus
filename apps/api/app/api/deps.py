from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from app.core.settings import Settings, get_settings
from app.db.session import get_db
from app.models import InstitutionalRole
from app.services.auth_service import (
    AuthenticatedPrincipal,
    AuthError,
    AuthService,
    SessionTokens,
)


def get_auth_service(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> AuthService:
    return AuthService(db, settings)


def _client_ip(request: Request) -> str:
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def set_session_cookie(response: Response, tokens: SessionTokens, settings: Settings) -> None:
    max_age = max(int((tokens.expires_at - datetime.now(UTC)).total_seconds()), 0)
    response.set_cookie(
        key=settings.session_cookie_name,
        value=tokens.session_token,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite=settings.session_cookie_samesite,  # type: ignore[arg-type]
        path=settings.session_cookie_path,
        max_age=max_age,
    )


def clear_session_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        key=settings.session_cookie_name,
        path=settings.session_cookie_path,
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite=settings.session_cookie_samesite,  # type: ignore[arg-type]
    )


def get_optional_principal(
    request: Request,
    auth: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
) -> AuthenticatedPrincipal | None:
    token = request.cookies.get(settings.session_cookie_name)
    try:
        return auth.resolve_session(session_token=token)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication subsystem unavailable",
        ) from exc


def get_current_principal(
    principal: Annotated[AuthenticatedPrincipal | None, Depends(get_optional_principal)],
) -> AuthenticatedPrincipal:
    if principal is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )
    return principal


def require_csrf(
    request: Request,
    principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
    auth: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_settings),
    csrf_header: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> AuthenticatedPrincipal:
    if request.method.upper() in {"GET", "HEAD", "OPTIONS", "TRACE"}:
        return principal
    header_name = settings.csrf_header_name
    token = csrf_header
    if token is None:
        # Allow configured alternate header lookup via headers map.
        token = request.headers.get(header_name)
    try:
        auth.validate_csrf(principal, token)
    except AuthError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return principal


class RoleChecker:
    def __init__(self, *roles: InstitutionalRole, action: str) -> None:
        self._roles = roles
        self._action = action

    def __call__(
        self,
        principal: Annotated[AuthenticatedPrincipal, Depends(require_csrf)],
        auth: AuthService = Depends(get_auth_service),
        request_id: str | None = Header(default=None, alias="X-Request-ID"),
    ) -> AuthenticatedPrincipal:
        # GET routes should use require_roles_read instead; mutating defaults to CSRF.
        try:
            auth.require_roles(principal, *self._roles, action=self._action, request_id=request_id)
        except AuthError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        return principal


class RoleCheckerRead:
    """RBAC for safe methods (no CSRF)."""

    def __init__(self, *roles: InstitutionalRole, action: str) -> None:
        self._roles = roles
        self._action = action

    def __call__(
        self,
        principal: Annotated[AuthenticatedPrincipal, Depends(get_current_principal)],
        auth: AuthService = Depends(get_auth_service),
        request_id: str | None = Header(default=None, alias="X-Request-ID"),
    ) -> AuthenticatedPrincipal:
        try:
            auth.require_roles(principal, *self._roles, action=self._action, request_id=request_id)
        except AuthError as exc:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
        return principal


RequireFounder = RoleChecker(InstitutionalRole.FOUNDER, action="founder.only")
RequireFounderRead = RoleCheckerRead(InstitutionalRole.FOUNDER, action="founder.only")
RequireOperatorRead = RoleCheckerRead(
    InstitutionalRole.FOUNDER, InstitutionalRole.OPERATOR, action="operator.read"
)
RequireAnyAuthenticatedRead = RoleCheckerRead(
    InstitutionalRole.FOUNDER,
    InstitutionalRole.OPERATOR,
    InstitutionalRole.VIEWER,
    action="authenticated.read",
)


def auth_http_error(exc: AuthError) -> HTTPException:
    detail = str(exc)
    if detail == "Forbidden":
        return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=detail)
    if detail == "User not found":
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=detail)
    if detail == "Authentication subsystem unavailable":
        return HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=detail)
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")


def parse_uuid(value: str) -> uuid.UUID:
    return uuid.UUID(value)
