from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.security import (
    DUMMY_PASSWORD_HASH,
    generate_token,
    hash_password,
    hash_token,
    tokens_match,
    verify_password,
)
from app.core.settings import Settings, get_settings
from app.models import AuthSession, InstitutionalRole, LoginAttempt, User, UserRole
from app.services.audit_service import AuditError, AuditService


class AuthError(RuntimeError):
    """Authentication or authorization failure (safe for clients)."""


@dataclass(frozen=True)
class SessionTokens:
    session_token: str
    csrf_token: str
    expires_at: datetime


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    user: User
    session: AuthSession
    roles: frozenset[InstitutionalRole]


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AuthService:
    def __init__(self, session: Session, settings: Settings | None = None) -> None:
        self._db = session
        self._settings = settings or get_settings()
        self._audit = AuditService(session)

    def _normalize_identifier(self, identifier: str) -> str:
        return identifier.strip().lower()

    def _find_user_by_identifier(self, identifier: str) -> User | None:
        normalized = self._normalize_identifier(identifier)
        stmt = (
            select(User)
            .options(selectinload(User.roles))
            .where(
                or_(
                    func.lower(User.username) == normalized,
                    func.lower(User.email) == normalized,
                )
            )
        )
        return self._db.scalars(stmt).first()

    def _count_recent_failures(self, identifier: str, ip_address: str) -> int:
        window_start = _utcnow() - timedelta(minutes=self._settings.login_failure_window_minutes)
        stmt = select(func.count()).select_from(LoginAttempt).where(
            LoginAttempt.identifier == self._normalize_identifier(identifier),
            LoginAttempt.ip_address == ip_address,
            LoginAttempt.successful.is_(False),
            LoginAttempt.attempted_at >= window_start,
        )
        return int(self._db.scalar(stmt) or 0)

    def _record_attempt(
        self, *, identifier: str, ip_address: str, successful: bool
    ) -> None:
        self._db.add(
            LoginAttempt(
                identifier=self._normalize_identifier(identifier),
                ip_address=ip_address or "unknown",
                successful=successful,
                attempted_at=_utcnow(),
            )
        )

    def _is_locked(self, identifier: str, ip_address: str) -> bool:
        failures = self._count_recent_failures(identifier, ip_address)
        return failures >= self._settings.login_max_failures

    def login(
        self,
        *,
        identifier: str,
        password: str,
        ip_address: str = "unknown",
        user_agent: str | None = None,
        request_id: str | None = None,
    ) -> tuple[User, SessionTokens]:
        if self._is_locked(identifier, ip_address):
            try:
                self._audit.append(
                    action="auth.login.lockout",
                    resource_type="auth",
                    request_id=request_id,
                    payload={"identifier_present": bool(identifier), "ip_address": ip_address},
                )
                self._db.commit()
            except AuditError:
                self._db.rollback()
            raise AuthError("Invalid credentials")

        user = self._find_user_by_identifier(identifier)
        password_ok = False
        if user is not None and user.is_active:
            password_ok = verify_password(password, user.password_hash)
        else:
            verify_password(password, DUMMY_PASSWORD_HASH)

        if user is None or not user.is_active or not password_ok:
            self._record_attempt(identifier=identifier, ip_address=ip_address, successful=False)
            try:
                self._audit.append(
                    action="auth.login.failure",
                    resource_type="auth",
                    actor_user_id=user.id if user is not None else None,
                    request_id=request_id,
                    payload={"reason": "invalid_credentials"},
                )
                self._db.commit()
            except AuditError:
                self._db.rollback()
            raise AuthError("Invalid credentials")

        tokens = self._create_session(
            user=user, ip_address=ip_address, user_agent=user_agent
        )
        self._record_attempt(identifier=identifier, ip_address=ip_address, successful=True)
        try:
            self._audit.append(
                action="auth.login.success",
                resource_type="user",
                resource_id=str(user.id),
                actor_user_id=user.id,
                request_id=request_id,
            )
            self._db.commit()
        except AuditError:
            self._db.rollback()
            raise AuthError("Authentication subsystem unavailable") from None

        return user, tokens

    def _create_session(
        self, *, user: User, ip_address: str, user_agent: str | None
    ) -> SessionTokens:
        session_token = generate_token()
        csrf_token = generate_token()
        expires_at = _utcnow() + timedelta(hours=self._settings.session_ttl_hours)
        row = AuthSession(
            user_id=user.id,
            token_hash=hash_token(session_token),
            csrf_token_hash=hash_token(csrf_token),
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=(user_agent or "")[:512] or None,
            last_seen_at=_utcnow(),
        )
        self._db.add(row)
        self._db.flush()
        return SessionTokens(
            session_token=session_token, csrf_token=csrf_token, expires_at=expires_at
        )

    def resolve_session(self, *, session_token: str | None) -> AuthenticatedPrincipal | None:
        if not session_token:
            return None
        token_hash = hash_token(session_token)
        stmt = (
            select(AuthSession)
            .options(selectinload(AuthSession.user).selectinload(User.roles))
            .where(AuthSession.token_hash == token_hash)
        )
        row = self._db.scalars(stmt).first()
        if row is None:
            return None

        now = _utcnow()
        if row.revoked_at is not None:
            return None
        if row.expires_at <= now:
            row.revoked_at = now
            try:
                self._audit.append(
                    action="auth.session.expired",
                    resource_type="auth_session",
                    resource_id=str(row.id),
                    actor_user_id=row.user_id,
                    payload={"reason": "expired"},
                )
                self._db.commit()
            except AuditError:
                self._db.rollback()
            return None

        if not row.user.is_active:
            return None

        roles = frozenset(role.role for role in row.user.roles)
        row.last_seen_at = now
        self._db.add(row)
        try:
            self._db.commit()
        except Exception:
            self._db.rollback()
            raise AuthError("Authentication subsystem unavailable") from None
        return AuthenticatedPrincipal(user=row.user, session=row, roles=roles)

    def validate_csrf(self, principal: AuthenticatedPrincipal, csrf_token: str | None) -> None:
        if not csrf_token or not tokens_match(
            hash_token(csrf_token), principal.session.csrf_token_hash
        ):
            try:
                self._audit.append(
                    action="auth.csrf.rejected",
                    resource_type="auth_session",
                    resource_id=str(principal.session.id),
                    actor_user_id=principal.user.id,
                )
                self._db.commit()
            except AuditError:
                self._db.rollback()
            raise AuthError("CSRF validation failed")

    def logout(
        self,
        *,
        principal: AuthenticatedPrincipal,
        request_id: str | None = None,
        reason: str = "logout",
    ) -> None:
        principal.session.revoked_at = _utcnow()
        try:
            self._audit.append(
                action="auth.logout",
                resource_type="auth_session",
                resource_id=str(principal.session.id),
                actor_user_id=principal.user.id,
                request_id=request_id,
                payload={"reason": reason},
            )
            self._db.commit()
        except AuditError:
            self._db.rollback()
            raise AuthError("Authentication subsystem unavailable") from None

    def create_user(
        self,
        *,
        actor: AuthenticatedPrincipal,
        username: str,
        password: str,
        email: str | None,
        roles: list[InstitutionalRole],
        request_id: str | None = None,
    ) -> User:
        if InstitutionalRole.FOUNDER not in actor.roles:
            self._deny(actor, action="user.create", request_id=request_id)
        if not roles:
            raise AuthError("At least one role is required")
        if InstitutionalRole.FOUNDER in roles and not self._settings.allow_additional_founders:
            if self._founder_exists():
                raise AuthError("Additional Founder accounts are disabled")

        user = User(
            username=username.strip(),
            email=email.strip().lower() if email else None,
            password_hash=hash_password(password),
            is_active=True,
        )
        self._db.add(user)
        self._db.flush()
        for role in roles:
            self._db.add(UserRole(user_id=user.id, role=role))
        try:
            self._audit.append(
                action="auth.user.create",
                resource_type="user",
                resource_id=str(user.id),
                actor_user_id=actor.user.id,
                request_id=request_id,
                payload={
                    "username": user.username,
                    "roles": [role.value for role in roles],
                },
            )
            if InstitutionalRole.FOUNDER in roles:
                self._audit.append(
                    action="auth.founder.create",
                    resource_type="user",
                    resource_id=str(user.id),
                    actor_user_id=actor.user.id,
                    request_id=request_id,
                )
            self._db.commit()
        except AuditError:
            self._db.rollback()
            raise AuthError("Authentication subsystem unavailable") from None
        self._db.refresh(user)
        return user

    def assign_role(
        self,
        *,
        actor: AuthenticatedPrincipal,
        user_id: uuid.UUID,
        role: InstitutionalRole,
        request_id: str | None = None,
    ) -> UserRole:
        if InstitutionalRole.FOUNDER not in actor.roles:
            self._deny(actor, action="user.role.assign", request_id=request_id)
        target = self._db.scalars(
            select(User).options(selectinload(User.roles)).where(User.id == user_id)
        ).first()
        if target is None:
            raise AuthError("User not found")
        if role == InstitutionalRole.FOUNDER and not self._settings.allow_additional_founders:
            if self._founder_exists() and not any(
                r.role == InstitutionalRole.FOUNDER for r in target.roles
            ):
                raise AuthError("Additional Founder accounts are disabled")

        existing = self._db.scalars(
            select(UserRole).where(UserRole.user_id == user_id, UserRole.role == role)
        ).first()
        if existing is not None:
            return existing

        row = UserRole(user_id=user_id, role=role)
        self._db.add(row)
        try:
            self._audit.append(
                action="auth.role.assign",
                resource_type="user",
                resource_id=str(user_id),
                actor_user_id=actor.user.id,
                request_id=request_id,
                payload={"role": role.value},
            )
            self._db.commit()
        except AuditError:
            self._db.rollback()
            raise AuthError("Authentication subsystem unavailable") from None
        return row

    def bootstrap_founder(
        self,
        *,
        username: str,
        password: str,
        email: str | None = None,
    ) -> User:
        if self._founder_exists() and not self._settings.allow_additional_founders:
            raise AuthError("A Founder account already exists")
        user = User(
            username=username.strip(),
            email=email.strip().lower() if email else None,
            password_hash=hash_password(password),
            is_active=True,
        )
        self._db.add(user)
        self._db.flush()
        self._db.add(UserRole(user_id=user.id, role=InstitutionalRole.FOUNDER))
        try:
            self._audit.append(
                action="auth.founder.bootstrap",
                resource_type="user",
                resource_id=str(user.id),
                actor_user_id=user.id,
                payload={"username": user.username},
            )
            self._audit.append(
                action="auth.founder.create",
                resource_type="user",
                resource_id=str(user.id),
                actor_user_id=user.id,
            )
            self._db.commit()
        except AuditError:
            self._db.rollback()
            raise AuthError("Authentication subsystem unavailable") from None
        return user

    def _founder_exists(self) -> bool:
        stmt = select(UserRole.id).where(UserRole.role == InstitutionalRole.FOUNDER).limit(1)
        return self._db.scalars(stmt).first() is not None

    def _deny(
        self, actor: AuthenticatedPrincipal, *, action: str, request_id: str | None
    ) -> None:
        try:
            self._audit.append(
                action="authz.denied",
                resource_type="authz",
                actor_user_id=actor.user.id,
                request_id=request_id,
                payload={"action": action, "roles": [r.value for r in actor.roles]},
            )
            self._db.commit()
        except AuditError:
            self._db.rollback()
        raise AuthError("Forbidden")

    def require_roles(
        self,
        principal: AuthenticatedPrincipal,
        *required: InstitutionalRole,
        action: str,
        request_id: str | None = None,
    ) -> None:
        if not required:
            return
        if principal.roles.isdisjoint(set(required)):
            self._deny(principal, action=action, request_id=request_id)

    def user_roles(self, user: User) -> list[InstitutionalRole]:
        return [role.role for role in user.roles]
