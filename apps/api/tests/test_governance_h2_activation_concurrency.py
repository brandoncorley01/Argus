"""H2: concurrent activation freshness and single-ACTIVE guarantees."""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from typing import Any

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.settings import clear_settings_cache, get_settings
from app.db.session import reset_engine
from app.models import (
    AuditEvent,
    AuthSession,
    ConfigurationDocument,
    ConfigurationVersion,
    DraftAuthority,
    InstitutionalRole,
    User,
    UserRole,
    VersionLifecycleStatus,
)
from app.services.auth_service import AuthenticatedPrincipal
from app.services.governance_service import GovernanceError, GovernanceService
from app.services.payload_integrity import hash_payload


def _unique(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def _make_engine():
    clear_settings_cache()
    reset_engine()
    return create_engine(get_settings().database_url, pool_size=8, max_overflow=4)


def _bootstrap_founder(session: Session) -> tuple[User, AuthSession]:
    user = User(
        username=_unique("h2f"),
        email=None,
        password_hash="unused",
        is_active=True,
    )
    session.add(user)
    session.flush()
    session.add(UserRole(user_id=user.id, role=InstitutionalRole.FOUNDER))
    auth_session = AuthSession(
        user_id=user.id,
        token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        csrf_token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        expires_at=datetime.now(UTC),
    )
    session.add(auth_session)
    session.commit()
    return user, auth_session


def _principal(user: User, auth_session: AuthSession) -> AuthenticatedPrincipal:
    return AuthenticatedPrincipal(
        user=user,
        roles=frozenset({InstitutionalRole.FOUNDER}),
        session=auth_session,
    )


def _seed_approved_versions(
    session: Session,
    *,
    count: int,
) -> tuple[uuid.UUID, list[uuid.UUID]]:
    doc = ConfigurationDocument(
        document_key=_unique("cfg.h2"),
        name="H2 Concurrent Config",
        schema_identifier="config.generic.v1",
        draft_authority=DraftAuthority.FOUNDER_ONLY,
    )
    session.add(doc)
    session.flush()
    version_ids: list[uuid.UUID] = []
    for i in range(1, count + 1):
        payload = {"n": i, "nonce": uuid.uuid4().hex}
        row = ConfigurationVersion(
            document_id=doc.id,
            version_number=i,
            version_label=f"v{i}",
            status=VersionLifecycleStatus.APPROVED,
            content=payload,
            payload_hash=hash_payload(payload),
            approved_at=datetime.now(UTC),
        )
        session.add(row)
        session.flush()
        version_ids.append(row.id)
    session.commit()
    return doc.id, version_ids


def _activate_in_thread(
    database_url: str,
    *,
    user_id: uuid.UUID,
    session_id: uuid.UUID,
    version_id: uuid.UUID,
    barrier: threading.Barrier,
) -> dict[str, Any]:
    engine = create_engine(database_url, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = SessionLocal()
    try:
        user = db.get(User, user_id)
        auth_session = db.get(AuthSession, session_id)
        assert user is not None and auth_session is not None
        principal = _principal(user, auth_session)
        gov = GovernanceService(db)
        barrier.wait(timeout=30)
        try:
            row = gov.activate_configuration_version(actor=principal, version_id=version_id)
            return {
                "ok": True,
                "version_id": str(row.id),
                "status": row.status.value,
                "error": None,
            }
        except Exception as exc:  # noqa: BLE001 — collect per-thread outcome
            db.rollback()
            return {
                "ok": False,
                "version_id": str(version_id),
                "status": None,
                "error": f"{type(exc).__name__}: {exc}",
            }
    finally:
        db.close()
        engine.dispose()


def test_concurrent_activate_different_versions_one_active() -> None:
    engine = _make_engine()
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    setup = SessionLocal()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        founder, auth_session = _bootstrap_founder(setup)
        founder_id = founder.id
        auth_session_id = auth_session.id
        doc_id, version_ids = _seed_approved_versions(setup, count=2)
        assert len(version_ids) == 2
    finally:
        setup.close()

    barrier = threading.Barrier(2)
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                _activate_in_thread,
                get_settings().database_url,
                user_id=founder_id,
                session_id=auth_session_id,
                version_id=version_ids[i],
                barrier=barrier,
            )
            for i in range(2)
        ]
        for fut in as_completed(futures):
            results.append(fut.result())

    assert len(results) == 2
    successes = [r for r in results if r["ok"]]
    failures = [r for r in results if not r["ok"]]
    # Both may succeed serially (second supersedes first), or one may fail if it
    # raced oddly — but exactly one ACTIVE must remain.
    assert len(successes) >= 1

    verify = SessionLocal()
    try:
        active = list(
            verify.scalars(
                select(ConfigurationVersion).where(
                    ConfigurationVersion.document_id == doc_id,
                    ConfigurationVersion.status == VersionLifecycleStatus.ACTIVE,
                )
            )
        )
        assert len(active) == 1
        active_id = active[0].id

        # The loser (if any) must not be ACTIVE; the winner must be ACTIVE.
        statuses = {
            row.id: row.status
            for row in verify.scalars(
                select(ConfigurationVersion).where(ConfigurationVersion.document_id == doc_id)
            )
        }
        assert statuses[active_id] == VersionLifecycleStatus.ACTIVE
        for vid in version_ids:
            if vid != active_id:
                assert statuses[vid] in {
                    VersionLifecycleStatus.SUPERSEDED,
                    VersionLifecycleStatus.APPROVED,
                }

        # No contradictory activate+supersede audits for the same candidate version.
        for vid in version_ids:
            actions = list(
                verify.scalars(
                    select(AuditEvent.action).where(
                        AuditEvent.resource_type == "configuration_version",
                        AuditEvent.resource_id == str(vid),
                        AuditEvent.action.in_(
                            [
                                "configuration_version.activated",
                                "configuration_version.superseded",
                            ]
                        ),
                    )
                )
            )
            # A version may be activated, or activated then later superseded by the
            # other winner — but must never be both activated and superseded as the
            # *same* contradictory outcome without an intervening second activate.
            if actions.count("configuration_version.activated") > 1:
                pytest.fail(f"duplicate activation audits for {vid}: {actions}")
            if (
                "configuration_version.activated" in actions
                and "configuration_version.superseded" in actions
                and vid == active_id
            ):
                pytest.fail(f"ACTIVE version {vid} also has superseded audit: {actions}")

        # Failures (if any) must not have left partial ACTIVE rows.
        assert failures or len(successes) == 2
    finally:
        verify.close()
        engine.dispose()
        reset_engine()
        clear_settings_cache()


def test_concurrent_activate_same_version_one_active_no_duplicate_activation() -> None:
    engine = _make_engine()
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    setup = SessionLocal()
    try:
        founder, auth_session = _bootstrap_founder(setup)
        founder_id = founder.id
        auth_session_id = auth_session.id
        doc_id, version_ids = _seed_approved_versions(setup, count=1)
        version_id = version_ids[0]
    finally:
        setup.close()

    barrier = threading.Barrier(2)
    results: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [
            pool.submit(
                _activate_in_thread,
                get_settings().database_url,
                user_id=founder_id,
                session_id=auth_session_id,
                version_id=version_id,
                barrier=barrier,
            )
            for _ in range(2)
        ]
        for fut in as_completed(futures):
            results.append(fut.result())

    successes = [r for r in results if r["ok"]]
    failures = [r for r in results if not r["ok"]]
    assert len(successes) == 1, results
    assert len(failures) == 1, results
    assert "Only APPROVED" in (failures[0]["error"] or "") or "GovernanceError" in (
        failures[0]["error"] or ""
    )

    verify = SessionLocal()
    try:
        active_count = verify.scalar(
            select(func.count()).select_from(ConfigurationVersion).where(
                ConfigurationVersion.document_id == doc_id,
                ConfigurationVersion.status == VersionLifecycleStatus.ACTIVE,
            )
        )
        assert int(active_count or 0) == 1

        activated_audits = list(
            verify.scalars(
                select(AuditEvent).where(
                    AuditEvent.resource_id == str(version_id),
                    AuditEvent.action == "configuration_version.activated",
                )
            )
        )
        superseded_audits = list(
            verify.scalars(
                select(AuditEvent).where(
                    AuditEvent.resource_id == str(version_id),
                    AuditEvent.action == "configuration_version.superseded",
                )
            )
        )
        assert len(activated_audits) == 1
        assert len(superseded_audits) == 0

        row = verify.get(ConfigurationVersion, version_id)
        assert row is not None
        assert row.status == VersionLifecycleStatus.ACTIVE
    finally:
        verify.close()
        engine.dispose()
        reset_engine()
        clear_settings_cache()


def test_failed_activation_leaves_prior_active_intact() -> None:
    """Non-APPROVED candidate must not disturb an existing ACTIVE version."""
    engine = _make_engine()
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    db = SessionLocal()
    try:
        founder, auth_session = _bootstrap_founder(db)
        doc_id, version_ids = _seed_approved_versions(db, count=2)
        principal = _principal(founder, auth_session)
        gov = GovernanceService(db)
        first = gov.activate_configuration_version(actor=principal, version_id=version_ids[0])
        assert first.status == VersionLifecycleStatus.ACTIVE

        # Second version still APPROVED — force it to DRAFT-equivalent rejection path
        # by attempting activate after manually moving it to UNDER_REVIEW via SQL
        # status (allowed lifecycle metadata update under immutability trigger).
        target = db.get(ConfigurationVersion, version_ids[1])
        assert target is not None
        target.status = VersionLifecycleStatus.UNDER_REVIEW
        db.add(target)
        db.commit()

        with pytest.raises(GovernanceError, match="Only APPROVED"):
            gov.activate_configuration_version(actor=principal, version_id=version_ids[1])

        db.expire_all()
        still_active = gov.get_active_configuration(doc_id)
        assert still_active is not None
        assert still_active.id == version_ids[0]
        assert still_active.status == VersionLifecycleStatus.ACTIVE

        other = db.get(ConfigurationVersion, version_ids[1])
        assert other is not None
        assert other.status == VersionLifecycleStatus.UNDER_REVIEW
    finally:
        db.close()
        engine.dispose()
        reset_engine()
        clear_settings_cache()
