from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, selectinload

from app.models import (
    ConfigurationDocument,
    ConfigurationVersion,
    InstitutionalIdentity,
    PolicyDocument,
    PolicyKind,
    PolicyVersion,
    VersionLifecycleStatus,
)
from app.services.audit_service import AuditError, AuditService
from app.services.auth_service import AuthenticatedPrincipal, AuthError, InstitutionalRole
from app.services.payload_integrity import (
    PayloadValidationError,
    hash_payload,
    validate_payload_for_schema,
    verify_payload_hash,
)
from app.services.version_lifecycle import assert_transition

GOVERNANCE_CRITICAL_KINDS = frozenset(
    {
        PolicyKind.CONSTITUTION,
        PolicyKind.OPERATING,
        PolicyKind.GOVERNANCE,
        PolicyKind.TREASURY,
        PolicyKind.RESEARCH,
        PolicyKind.SECURITY,
        PolicyKind.AUDIT,
        PolicyKind.AUTHENTICATION,
        PolicyKind.FEATURE_GOVERNANCE,
    }
)

IDENTITY_FIELD_BY_KIND: dict[PolicyKind, str] = {
    PolicyKind.CONSTITUTION: "active_constitution_version",
    PolicyKind.OPERATING: "active_operating_policy_version",
    PolicyKind.GOVERNANCE: "active_governance_version",
    PolicyKind.TREASURY: "active_treasury_policy_version",
    PolicyKind.RESEARCH: "active_research_framework_version",
}


class GovernanceError(RuntimeError):
    """Domain error for configuration/policy governance operations."""


def _utcnow() -> datetime:
    return datetime.now(UTC)


class GovernanceService:
    def __init__(self, session: Session) -> None:
        self._db = session
        self._audit = AuditService(session)

    def _require(
        self,
        actor: AuthenticatedPrincipal,
        *roles: InstitutionalRole,
        action: str,
        request_id: str | None,
    ) -> None:
        if actor.roles.isdisjoint(set(roles)):
            try:
                self._audit.append(
                    action="authz.denied",
                    resource_type="governance",
                    actor_user_id=actor.user.id,
                    request_id=request_id,
                    payload={"action": action, "roles": [r.value for r in actor.roles]},
                )
                self._db.commit()
            except AuditError:
                self._db.rollback()
            raise AuthError("Forbidden")

    def _lock_document_row(self, table: str, document_id: uuid.UUID) -> None:
        self._db.execute(
            text(f"SELECT id FROM {table} WHERE id = :id FOR UPDATE"),
            {"id": str(document_id)},
        )

    def _get_institutional_identity(self) -> InstitutionalIdentity | None:
        return self._db.scalars(
            select(InstitutionalIdentity).order_by(InstitutionalIdentity.created_at.asc()).limit(1)
        ).first()

    def _next_version_number(self, model: type[Any], document_id: uuid.UUID) -> int:
        current = self._db.scalar(
            select(func.coalesce(func.max(model.version_number), 0)).where(
                model.document_id == document_id
            )
        )
        return int(current or 0) + 1

    def _commit_with_audits(self, events: list[dict[str, Any]]) -> None:
        try:
            for event in events:
                self._audit.append(**event)
            self._db.commit()
        except AuditError:
            self._db.rollback()
            raise GovernanceError(
                "Audit persistence failed; operation aborted (fail-closed)"
            ) from None
        except Exception:
            self._db.rollback()
            raise

    # --- Configuration documents ---

    def create_configuration_document(
        self,
        *,
        actor: AuthenticatedPrincipal,
        document_key: str,
        name: str,
        description: str | None,
        schema_identifier: str,
        request_id: str | None = None,
    ) -> ConfigurationDocument:
        self._require(
            actor,
            InstitutionalRole.FOUNDER,
            action="configuration_document.create",
            request_id=request_id,
        )
        doc = ConfigurationDocument(
            document_key=document_key.strip(),
            name=name.strip(),
            description=description,
            schema_identifier=schema_identifier.strip(),
            created_by_user_id=actor.user.id,
        )
        self._db.add(doc)
        self._db.flush()
        self._commit_with_audits(
            [
                {
                    "action": "configuration_document.created",
                    "resource_type": "configuration_document",
                    "resource_id": str(doc.id),
                    "actor_user_id": actor.user.id,
                    "request_id": request_id,
                    "payload": {"document_key": doc.document_key},
                }
            ]
        )
        return doc

    def create_configuration_version(
        self,
        *,
        actor: AuthenticatedPrincipal,
        document_id: uuid.UUID,
        payload: dict[str, Any],
        change_summary: str | None = None,
        request_id: str | None = None,
    ) -> ConfigurationVersion:
        self._require(
            actor,
            InstitutionalRole.FOUNDER,
            InstitutionalRole.OPERATOR,
            action="configuration_version.create",
            request_id=request_id,
        )
        doc = self._db.get(ConfigurationDocument, document_id)
        if doc is None or doc.is_retired:
            raise GovernanceError("Configuration document not found")
        try:
            validate_payload_for_schema(doc.schema_identifier, payload)
        except PayloadValidationError as exc:
            raise GovernanceError(str(exc)) from exc

        payload_hash = hash_payload(payload)
        latest = self._db.scalars(
            select(ConfigurationVersion)
            .where(ConfigurationVersion.document_id == document_id)
            .order_by(ConfigurationVersion.version_number.desc())
            .limit(1)
        ).first()
        if latest is not None and latest.payload_hash == payload_hash:
            raise GovernanceError("Identical payload to latest version is not allowed")

        version_number = self._next_version_number(ConfigurationVersion, document_id)
        row = ConfigurationVersion(
            document_id=document_id,
            version_number=version_number,
            version_label=f"v{version_number}",
            status=VersionLifecycleStatus.DRAFT,
            content=payload,
            payload_hash=payload_hash,
            change_summary=change_summary,
            previous_version_id=latest.id if latest else None,
            created_by_user_id=actor.user.id,
        )
        self._db.add(row)
        self._db.flush()
        self._commit_with_audits(
            [
                {
                    "action": "configuration_version.created",
                    "resource_type": "configuration_version",
                    "resource_id": str(row.id),
                    "actor_user_id": actor.user.id,
                    "request_id": request_id,
                    "payload": {
                        "document_key": doc.document_key,
                        "version_number": version_number,
                        "payload_hash": payload_hash,
                        "status": row.status.value,
                    },
                }
            ]
        )
        return row

    def update_configuration_draft(
        self,
        *,
        actor: AuthenticatedPrincipal,
        version_id: uuid.UUID,
        payload: dict[str, Any],
        change_summary: str | None = None,
        request_id: str | None = None,
    ) -> ConfigurationVersion:
        self._require(
            actor,
            InstitutionalRole.FOUNDER,
            InstitutionalRole.OPERATOR,
            action="configuration_version.update_draft",
            request_id=request_id,
        )
        row = self._db.scalars(
            select(ConfigurationVersion)
            .options(selectinload(ConfigurationVersion.document))
            .where(ConfigurationVersion.id == version_id)
        ).first()
        if row is None:
            raise GovernanceError("Configuration version not found")
        if row.status != VersionLifecycleStatus.DRAFT:
            raise GovernanceError("Only DRAFT versions may be edited")
        try:
            validate_payload_for_schema(row.document.schema_identifier, payload)
        except PayloadValidationError as exc:
            raise GovernanceError(str(exc)) from exc
        row.content = payload
        row.payload_hash = hash_payload(payload)
        if change_summary is not None:
            row.change_summary = change_summary
        self._db.add(row)
        self._commit_with_audits(
            [
                {
                    "action": "configuration_version.created",
                    "resource_type": "configuration_version",
                    "resource_id": str(row.id),
                    "actor_user_id": actor.user.id,
                    "request_id": request_id,
                    "payload": {
                        "document_key": row.document.document_key,
                        "version_number": row.version_number,
                        "payload_hash": row.payload_hash,
                        "status": row.status.value,
                        "draft_updated": True,
                    },
                }
            ]
        )
        return row

    def transition_configuration_version(
        self,
        *,
        actor: AuthenticatedPrincipal,
        version_id: uuid.UUID,
        new_status: VersionLifecycleStatus,
        rejection_reason: str | None = None,
        request_id: str | None = None,
    ) -> ConfigurationVersion:
        row = self._db.scalars(
            select(ConfigurationVersion)
            .options(selectinload(ConfigurationVersion.document))
            .where(ConfigurationVersion.id == version_id)
        ).first()
        if row is None:
            raise GovernanceError("Configuration version not found")

        if new_status in {
            VersionLifecycleStatus.APPROVED,
            VersionLifecycleStatus.ACTIVE,
            VersionLifecycleStatus.RETIRED,
        }:
            self._require(
                actor,
                InstitutionalRole.FOUNDER,
                action=f"configuration_version.{new_status.value.lower()}",
                request_id=request_id,
            )
        elif new_status == VersionLifecycleStatus.REJECTED:
            self._require(
                actor,
                InstitutionalRole.FOUNDER,
                action="configuration_version.reject",
                request_id=request_id,
            )
        else:
            self._require(
                actor,
                InstitutionalRole.FOUNDER,
                InstitutionalRole.OPERATOR,
                action=f"configuration_version.{new_status.value.lower()}",
                request_id=request_id,
            )

        if new_status == VersionLifecycleStatus.ACTIVE:
            return self.activate_configuration_version(
                actor=actor, version_id=version_id, request_id=request_id
            )

        try:
            assert_transition(row.status, new_status)
        except ValueError as exc:
            raise GovernanceError(str(exc)) from exc

        previous = row.status
        now = _utcnow()
        row.status = new_status
        if new_status == VersionLifecycleStatus.UNDER_REVIEW:
            row.submitted_at = now
            row.submitted_by_user_id = actor.user.id
            action = "configuration_version.submitted"
        elif new_status == VersionLifecycleStatus.APPROVED:
            row.approved_at = now
            row.approved_by_user_id = actor.user.id
            action = "configuration_version.approved"
        elif new_status == VersionLifecycleStatus.REJECTED:
            if not rejection_reason:
                raise GovernanceError("rejection_reason is required")
            row.rejected_at = now
            row.rejected_by_user_id = actor.user.id
            row.rejection_reason = rejection_reason
            action = "configuration_version.rejected"
        elif new_status == VersionLifecycleStatus.RETIRED:
            row.retired_at = now
            row.retired_by_user_id = actor.user.id
            action = "configuration_version.retired"
        elif new_status == VersionLifecycleStatus.DRAFT:
            action = "configuration_version.created"
        else:
            action = "configuration_version.submitted"

        self._db.add(row)
        self._commit_with_audits(
            [
                {
                    "action": action,
                    "resource_type": "configuration_version",
                    "resource_id": str(row.id),
                    "actor_user_id": actor.user.id,
                    "request_id": request_id,
                    "payload": {
                        "document_key": row.document.document_key,
                        "version_number": row.version_number,
                        "payload_hash": row.payload_hash,
                        "previous_status": previous.value,
                        "new_status": new_status.value,
                    },
                }
            ]
        )
        return row

    def activate_configuration_version(
        self,
        *,
        actor: AuthenticatedPrincipal,
        version_id: uuid.UUID,
        request_id: str | None = None,
    ) -> ConfigurationVersion:
        self._require(
            actor,
            InstitutionalRole.FOUNDER,
            action="configuration_version.activate",
            request_id=request_id,
        )
        row = self._db.scalars(
            select(ConfigurationVersion)
            .options(selectinload(ConfigurationVersion.document))
            .where(ConfigurationVersion.id == version_id)
        ).first()
        if row is None:
            raise GovernanceError("Configuration version not found")

        self._lock_document_row("configuration_documents", row.document_id)

        if row.status != VersionLifecycleStatus.APPROVED:
            raise GovernanceError("Only APPROVED versions may be activated")
        if not verify_payload_hash(row.content, row.payload_hash):
            self._commit_with_audits(
                [
                    {
                        "action": "configuration_integrity.failed",
                        "resource_type": "configuration_version",
                        "resource_id": str(row.id),
                        "actor_user_id": actor.user.id,
                        "request_id": request_id,
                        "payload": {"payload_hash": row.payload_hash},
                    }
                ]
            )
            raise GovernanceError("Payload hash mismatch; activation blocked")

        try:
            assert_transition(row.status, VersionLifecycleStatus.ACTIVE)
        except ValueError as exc:
            raise GovernanceError(str(exc)) from exc

        now = _utcnow()
        current_active = self._db.scalars(
            select(ConfigurationVersion).where(
                ConfigurationVersion.document_id == row.document_id,
                ConfigurationVersion.status == VersionLifecycleStatus.ACTIVE,
            )
        ).first()

        events: list[dict[str, Any]] = []
        if current_active is not None:
            current_active.status = VersionLifecycleStatus.SUPERSEDED
            current_active.superseded_at = now
            current_active.superseded_by_user_id = actor.user.id
            self._db.add(current_active)
            self._db.flush()
            events.append(
                {
                    "action": "configuration_version.superseded",
                    "resource_type": "configuration_version",
                    "resource_id": str(current_active.id),
                    "actor_user_id": actor.user.id,
                    "request_id": request_id,
                    "payload": {
                        "document_key": row.document.document_key,
                        "version_number": current_active.version_number,
                        "payload_hash": current_active.payload_hash,
                        "previous_status": VersionLifecycleStatus.ACTIVE.value,
                        "new_status": VersionLifecycleStatus.SUPERSEDED.value,
                    },
                }
            )

        row.status = VersionLifecycleStatus.ACTIVE
        row.activated_at = now
        row.activated_by_user_id = actor.user.id
        self._db.add(row)
        events.append(
            {
                "action": "configuration_version.activated",
                "resource_type": "configuration_version",
                "resource_id": str(row.id),
                "actor_user_id": actor.user.id,
                "request_id": request_id,
                "config_version_id": row.id,
                "payload": {
                    "document_key": row.document.document_key,
                    "version_number": row.version_number,
                    "payload_hash": row.payload_hash,
                    "previous_status": VersionLifecycleStatus.APPROVED.value,
                    "new_status": VersionLifecycleStatus.ACTIVE.value,
                },
            }
        )
        self._db.flush()
        self._commit_with_audits(events)
        return row

    def get_active_configuration(self, document_id: uuid.UUID) -> ConfigurationVersion | None:
        return self._db.scalars(
            select(ConfigurationVersion).where(
                ConfigurationVersion.document_id == document_id,
                ConfigurationVersion.status == VersionLifecycleStatus.ACTIVE,
            )
        ).first()

    def compare_configuration_versions(
        self, left_id: uuid.UUID, right_id: uuid.UUID
    ) -> dict[str, Any]:
        left = self._db.get(ConfigurationVersion, left_id)
        right = self._db.get(ConfigurationVersion, right_id)
        if left is None or right is None:
            raise GovernanceError("Configuration version not found")
        left_keys = set(left.content.keys())
        right_keys = set(right.content.keys())
        return {
            "left_id": str(left.id),
            "right_id": str(right.id),
            "left_hash": left.payload_hash,
            "right_hash": right.payload_hash,
            "added_keys": sorted(right_keys - left_keys),
            "removed_keys": sorted(left_keys - right_keys),
            "changed_keys": sorted(
                key
                for key in left_keys & right_keys
                if left.content.get(key) != right.content.get(key)
            ),
            "identical": left.payload_hash == right.payload_hash,
        }

    # --- Policy documents ---

    def create_policy_document(
        self,
        *,
        actor: AuthenticatedPrincipal,
        document_key: str,
        name: str,
        policy_kind: PolicyKind,
        description: str | None,
        schema_identifier: str,
        request_id: str | None = None,
    ) -> PolicyDocument:
        self._require(
            actor,
            InstitutionalRole.FOUNDER,
            action="policy_document.create",
            request_id=request_id,
        )
        doc = PolicyDocument(
            document_key=document_key.strip(),
            name=name.strip(),
            policy_kind=policy_kind,
            description=description,
            schema_identifier=schema_identifier.strip(),
            created_by_user_id=actor.user.id,
        )
        self._db.add(doc)
        self._db.flush()
        self._commit_with_audits(
            [
                {
                    "action": "policy_document.created",
                    "resource_type": "policy_document",
                    "resource_id": str(doc.id),
                    "actor_user_id": actor.user.id,
                    "request_id": request_id,
                    "payload": {
                        "document_key": doc.document_key,
                        "policy_kind": policy_kind.value,
                    },
                }
            ]
        )
        return doc

    def create_policy_version(
        self,
        *,
        actor: AuthenticatedPrincipal,
        document_id: uuid.UUID,
        payload: dict[str, Any],
        change_summary: str | None = None,
        request_id: str | None = None,
    ) -> PolicyVersion:
        doc = self._db.get(PolicyDocument, document_id)
        if doc is None or doc.is_retired:
            raise GovernanceError("Policy document not found")
        if doc.policy_kind in GOVERNANCE_CRITICAL_KINDS:
            self._require(
                actor,
                InstitutionalRole.FOUNDER,
                action="policy_version.create",
                request_id=request_id,
            )
        else:
            self._require(
                actor,
                InstitutionalRole.FOUNDER,
                InstitutionalRole.OPERATOR,
                action="policy_version.create",
                request_id=request_id,
            )
        try:
            validate_payload_for_schema(doc.schema_identifier, payload)
        except PayloadValidationError as exc:
            raise GovernanceError(str(exc)) from exc
        payload_hash = hash_payload(payload)
        latest = self._db.scalars(
            select(PolicyVersion)
            .where(PolicyVersion.document_id == document_id)
            .order_by(PolicyVersion.version_number.desc())
            .limit(1)
        ).first()
        if latest is not None and latest.payload_hash == payload_hash:
            raise GovernanceError("Identical payload to latest version is not allowed")
        version_number = self._next_version_number(PolicyVersion, document_id)
        row = PolicyVersion(
            document_id=document_id,
            version_number=version_number,
            version_label=f"v{version_number}",
            status=VersionLifecycleStatus.DRAFT,
            content=payload,
            payload_hash=payload_hash,
            change_summary=change_summary,
            previous_version_id=latest.id if latest else None,
            created_by_user_id=actor.user.id,
        )
        self._db.add(row)
        self._db.flush()
        self._commit_with_audits(
            [
                {
                    "action": "policy_version.created",
                    "resource_type": "policy_version",
                    "resource_id": str(row.id),
                    "actor_user_id": actor.user.id,
                    "request_id": request_id,
                    "payload": {
                        "document_key": doc.document_key,
                        "version_number": version_number,
                        "payload_hash": payload_hash,
                        "status": row.status.value,
                    },
                }
            ]
        )
        return row

    def update_policy_draft(
        self,
        *,
        actor: AuthenticatedPrincipal,
        version_id: uuid.UUID,
        payload: dict[str, Any],
        change_summary: str | None = None,
        request_id: str | None = None,
    ) -> PolicyVersion:
        row = self._db.scalars(
            select(PolicyVersion)
            .options(selectinload(PolicyVersion.document))
            .where(PolicyVersion.id == version_id)
        ).first()
        if row is None:
            raise GovernanceError("Policy version not found")
        if row.document.policy_kind in GOVERNANCE_CRITICAL_KINDS:
            self._require(
                actor,
                InstitutionalRole.FOUNDER,
                action="policy_version.update_draft",
                request_id=request_id,
            )
        else:
            self._require(
                actor,
                InstitutionalRole.FOUNDER,
                InstitutionalRole.OPERATOR,
                action="policy_version.update_draft",
                request_id=request_id,
            )
        if row.status != VersionLifecycleStatus.DRAFT:
            raise GovernanceError("Only DRAFT versions may be edited")
        try:
            validate_payload_for_schema(row.document.schema_identifier, payload)
        except PayloadValidationError as exc:
            raise GovernanceError(str(exc)) from exc
        row.content = payload
        row.payload_hash = hash_payload(payload)
        if change_summary is not None:
            row.change_summary = change_summary
        self._db.add(row)
        self._commit_with_audits(
            [
                {
                    "action": "policy_version.created",
                    "resource_type": "policy_version",
                    "resource_id": str(row.id),
                    "actor_user_id": actor.user.id,
                    "request_id": request_id,
                    "payload": {
                        "document_key": row.document.document_key,
                        "version_number": row.version_number,
                        "payload_hash": row.payload_hash,
                        "status": row.status.value,
                        "draft_updated": True,
                    },
                }
            ]
        )
        return row

    def transition_policy_version(
        self,
        *,
        actor: AuthenticatedPrincipal,
        version_id: uuid.UUID,
        new_status: VersionLifecycleStatus,
        rejection_reason: str | None = None,
        request_id: str | None = None,
    ) -> PolicyVersion:
        row = self._db.scalars(
            select(PolicyVersion)
            .options(selectinload(PolicyVersion.document))
            .where(PolicyVersion.id == version_id)
        ).first()
        if row is None:
            raise GovernanceError("Policy version not found")

        if new_status == VersionLifecycleStatus.ACTIVE:
            return self.activate_policy_version(
                actor=actor, version_id=version_id, request_id=request_id
            )

        if (
            new_status
            in {
                VersionLifecycleStatus.APPROVED,
                VersionLifecycleStatus.REJECTED,
                VersionLifecycleStatus.RETIRED,
            }
            or row.document.policy_kind in GOVERNANCE_CRITICAL_KINDS
        ):
            self._require(
                actor,
                InstitutionalRole.FOUNDER,
                action=f"policy_version.{new_status.value.lower()}",
                request_id=request_id,
            )
        else:
            self._require(
                actor,
                InstitutionalRole.FOUNDER,
                InstitutionalRole.OPERATOR,
                action=f"policy_version.{new_status.value.lower()}",
                request_id=request_id,
            )

        try:
            assert_transition(row.status, new_status)
        except ValueError as exc:
            raise GovernanceError(str(exc)) from exc

        previous = row.status
        now = _utcnow()
        row.status = new_status
        if new_status == VersionLifecycleStatus.UNDER_REVIEW:
            row.submitted_at = now
            row.submitted_by_user_id = actor.user.id
            action = "policy_version.submitted"
        elif new_status == VersionLifecycleStatus.APPROVED:
            row.approved_at = now
            row.approved_by_user_id = actor.user.id
            action = "policy_version.approved"
        elif new_status == VersionLifecycleStatus.REJECTED:
            if not rejection_reason:
                raise GovernanceError("rejection_reason is required")
            row.rejected_at = now
            row.rejected_by_user_id = actor.user.id
            row.rejection_reason = rejection_reason
            action = "policy_version.rejected"
        elif new_status == VersionLifecycleStatus.RETIRED:
            row.retired_at = now
            row.retired_by_user_id = actor.user.id
            action = "policy_version.retired"
        else:
            action = "policy_version.submitted"

        self._db.add(row)
        self._commit_with_audits(
            [
                {
                    "action": action,
                    "resource_type": "policy_version",
                    "resource_id": str(row.id),
                    "actor_user_id": actor.user.id,
                    "request_id": request_id,
                    "payload": {
                        "document_key": row.document.document_key,
                        "version_number": row.version_number,
                        "payload_hash": row.payload_hash,
                        "previous_status": previous.value,
                        "new_status": new_status.value,
                    },
                }
            ]
        )
        return row

    def activate_policy_version(
        self,
        *,
        actor: AuthenticatedPrincipal,
        version_id: uuid.UUID,
        request_id: str | None = None,
    ) -> PolicyVersion:
        self._require(
            actor,
            InstitutionalRole.FOUNDER,
            action="policy_version.activate",
            request_id=request_id,
        )
        row = self._db.scalars(
            select(PolicyVersion)
            .options(selectinload(PolicyVersion.document))
            .where(PolicyVersion.id == version_id)
        ).first()
        if row is None:
            raise GovernanceError("Policy version not found")
        self._lock_document_row("policy_documents", row.document_id)
        if row.status != VersionLifecycleStatus.APPROVED:
            raise GovernanceError("Only APPROVED versions may be activated")
        if not verify_payload_hash(row.content, row.payload_hash):
            self._commit_with_audits(
                [
                    {
                        "action": "policy_integrity.failed",
                        "resource_type": "policy_version",
                        "resource_id": str(row.id),
                        "actor_user_id": actor.user.id,
                        "request_id": request_id,
                        "payload": {"payload_hash": row.payload_hash},
                    }
                ]
            )
            raise GovernanceError("Payload hash mismatch; activation blocked")

        now = _utcnow()
        current_active = self._db.scalars(
            select(PolicyVersion).where(
                PolicyVersion.document_id == row.document_id,
                PolicyVersion.status == VersionLifecycleStatus.ACTIVE,
            )
        ).first()
        events: list[dict[str, Any]] = []
        if current_active is not None:
            current_active.status = VersionLifecycleStatus.SUPERSEDED
            current_active.superseded_at = now
            current_active.superseded_by_user_id = actor.user.id
            self._db.add(current_active)
            self._db.flush()
            events.append(
                {
                    "action": "policy_version.superseded",
                    "resource_type": "policy_version",
                    "resource_id": str(current_active.id),
                    "actor_user_id": actor.user.id,
                    "request_id": request_id,
                    "payload": {
                        "document_key": row.document.document_key,
                        "version_number": current_active.version_number,
                        "payload_hash": current_active.payload_hash,
                        "previous_status": VersionLifecycleStatus.ACTIVE.value,
                        "new_status": VersionLifecycleStatus.SUPERSEDED.value,
                    },
                }
            )

        row.status = VersionLifecycleStatus.ACTIVE
        row.activated_at = now
        row.activated_by_user_id = actor.user.id
        self._db.add(row)

        # Institutional Identity: version_label is authoritative display pointer.
        field = IDENTITY_FIELD_BY_KIND.get(row.document.policy_kind)
        if field is not None:
            identity = self._get_institutional_identity()
            if identity is not None:
                setattr(identity, field, row.version_label)
                self._db.add(identity)

        events.append(
            {
                "action": "policy_version.activated",
                "resource_type": "policy_version",
                "resource_id": str(row.id),
                "actor_user_id": actor.user.id,
                "request_id": request_id,
                "policy_version_id": row.id,
                "payload": {
                    "document_key": row.document.document_key,
                    "version_number": row.version_number,
                    "payload_hash": row.payload_hash,
                    "previous_status": VersionLifecycleStatus.APPROVED.value,
                    "new_status": VersionLifecycleStatus.ACTIVE.value,
                    "identity_field_updated": field,
                },
            }
        )
        self._db.flush()
        self._commit_with_audits(events)
        return row

    def get_active_policy(self, document_id: uuid.UUID) -> PolicyVersion | None:
        return self._db.scalars(
            select(PolicyVersion).where(
                PolicyVersion.document_id == document_id,
                PolicyVersion.status == VersionLifecycleStatus.ACTIVE,
            )
        ).first()

    def compare_policy_versions(self, left_id: uuid.UUID, right_id: uuid.UUID) -> dict[str, Any]:
        left = self._db.get(PolicyVersion, left_id)
        right = self._db.get(PolicyVersion, right_id)
        if left is None or right is None:
            raise GovernanceError("Policy version not found")
        left_keys = set(left.content.keys())
        right_keys = set(right.content.keys())
        return {
            "left_id": str(left.id),
            "right_id": str(right.id),
            "left_hash": left.payload_hash,
            "right_hash": right.payload_hash,
            "added_keys": sorted(right_keys - left_keys),
            "removed_keys": sorted(left_keys - right_keys),
            "changed_keys": sorted(
                key
                for key in left_keys & right_keys
                if left.content.get(key) != right.content.get(key)
            ),
            "identical": left.payload_hash == right.payload_hash,
        }
