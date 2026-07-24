"""Treasury service (Phase 14) — accounts, pools, allocations, reservations,
internal ledger, and external transfer *instructions* only.

Boundary chain enforced end-to-end by this module:

    analysis -> recommendation -> approval -> reservation -> internal ledger
    -> external transfer instruction -> execution (FORBIDDEN) -> reconciliation

Every balance-affecting mutation writes an append-only
``treasury_ledger_entries`` row in the same transaction. No method in this
class can execute a real external transfer: :meth:`attempt_execute_transfer`
always raises :class:`TreasuryError` with code
``external_transfer_execution_forbidden`` — there is no code path that
returns success, and the model layer does not even define an executed
status (see ADR-030).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.treasury import (
    CapitalAllocation,
    CapitalAllocationStatus,
    CapitalAllocationTargetType,
    CapitalPool,
    CapitalReservation,
    ExternalTransferDirection,
    ExternalTransferInstruction,
    ExternalTransferStatus,
    TreasuryAccount,
    TreasuryAccountClassification,
    TreasuryLedgerEntry,
)
from app.services.audit_service import AuditService
from app.services.auth_service import AuthenticatedPrincipal


class TreasuryError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TreasuryService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    # --- accounts ---------------------------------------------------

    def list_accounts(self) -> list[TreasuryAccount]:
        return list(self.db.scalars(select(TreasuryAccount).order_by(TreasuryAccount.created_at)))

    def get_account(self, account_id: uuid.UUID) -> TreasuryAccount:
        row = self.db.get(TreasuryAccount, account_id)
        if row is None:
            raise TreasuryError("not_found", f"Treasury account {account_id} not found")
        return row

    def create_account(
        self,
        *,
        name: str,
        currency: str,
        classification: str,
        description: str | None,
        actor: AuthenticatedPrincipal,
    ) -> TreasuryAccount:
        try:
            TreasuryAccountClassification(classification)
        except ValueError as exc:
            raise TreasuryError(
                "invalid_classification", f"Unknown classification: {classification}"
            ) from exc
        existing = self.db.scalar(select(TreasuryAccount).where(TreasuryAccount.name == name))
        if existing is not None:
            raise TreasuryError("duplicate_name", f"Account '{name}' already exists")

        row = TreasuryAccount(
            name=name,
            currency=currency,
            classification=classification,
            balance=Decimal("0"),
            is_simulated=True,
            status="active",
            description=description,
        )
        self.db.add(row)
        self.db.flush()
        self.audit.append(
            action="treasury.account.create",
            resource_type="treasury_account",
            resource_id=str(row.id),
            actor_user_id=actor.user.id,
            payload={"name": name, "classification": classification},
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    def fund_account_simulated(
        self,
        account_id: uuid.UUID,
        *,
        amount: Decimal,
        note: str | None,
        actor: AuthenticatedPrincipal,
    ) -> TreasuryAccount:
        """Increase a simulated account balance via an internal ledger entry.

        This is never an external deposit — it is a simulated funding
        operation used to exercise allocation/reservation workflows without
        any real capital movement.
        """
        if amount <= 0:
            raise TreasuryError("invalid_amount", "amount must be positive")
        account = self.get_account(account_id)
        account.balance = account.balance + amount
        entry = TreasuryLedgerEntry(
            account_id=account.id,
            entry_type="deposit_simulated",
            amount=amount,
            balance_after=account.balance,
            reference_type="manual",
            note=note or "Simulated funding — not a real deposit",
            created_by_user_id=actor.user.id,
        )
        self.db.add(entry)
        self.db.flush()
        self.audit.append(
            action="treasury.account.fund_simulated",
            resource_type="treasury_account",
            resource_id=str(account.id),
            actor_user_id=actor.user.id,
            payload={"amount": str(amount)},
        )
        self.db.commit()
        self.db.refresh(account)
        return account

    # --- pools --------------------------------------------------------

    def list_pools(self, account_id: uuid.UUID | None = None) -> list[CapitalPool]:
        stmt = select(CapitalPool).order_by(CapitalPool.created_at)
        if account_id is not None:
            stmt = stmt.where(CapitalPool.account_id == account_id)
        return list(self.db.scalars(stmt))

    def get_pool(self, pool_id: uuid.UUID) -> CapitalPool:
        row = self.db.get(CapitalPool, pool_id)
        if row is None:
            raise TreasuryError("not_found", f"Capital pool {pool_id} not found")
        return row

    def create_pool(
        self,
        *,
        account_id: uuid.UUID,
        name: str,
        pool_type: str,
        actor: AuthenticatedPrincipal,
    ) -> CapitalPool:
        self.get_account(account_id)
        existing = self.db.scalar(
            select(CapitalPool).where(
                CapitalPool.account_id == account_id, CapitalPool.name == name
            )
        )
        if existing is not None:
            raise TreasuryError("duplicate_name", f"Pool '{name}' already exists on this account")
        row = CapitalPool(
            account_id=account_id, name=name, pool_type=pool_type, balance=Decimal("0")
        )
        self.db.add(row)
        self.db.flush()
        self.audit.append(
            action="treasury.pool.create",
            resource_type="capital_pool",
            resource_id=str(row.id),
            actor_user_id=actor.user.id,
            payload={"account_id": str(account_id), "name": name, "pool_type": pool_type},
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    # --- allocations ----------------------------------------------------

    def list_allocations(
        self, *, pool_id: uuid.UUID | None = None, status: str | None = None
    ) -> list[CapitalAllocation]:
        stmt = select(CapitalAllocation).order_by(CapitalAllocation.requested_at.desc())
        if pool_id is not None:
            stmt = stmt.where(CapitalAllocation.pool_id == pool_id)
        if status is not None:
            stmt = stmt.where(CapitalAllocation.status == status)
        return list(self.db.scalars(stmt))

    def get_allocation(self, allocation_id: uuid.UUID) -> CapitalAllocation:
        row = self.db.get(CapitalAllocation, allocation_id)
        if row is None:
            raise TreasuryError("not_found", f"Capital allocation {allocation_id} not found")
        return row

    def request_allocation(
        self,
        *,
        pool_id: uuid.UUID,
        target_type: str,
        target_id: str | None,
        amount: Decimal,
        max_amount: Decimal | None,
        notes: str | None,
        actor: AuthenticatedPrincipal,
    ) -> CapitalAllocation:
        self.get_pool(pool_id)
        try:
            CapitalAllocationTargetType(target_type)
        except ValueError as exc:
            raise TreasuryError(
                "invalid_target_type", f"Unknown target_type: {target_type}"
            ) from exc
        if amount <= 0:
            raise TreasuryError("invalid_amount", "amount must be positive")
        if max_amount is not None and max_amount < amount:
            raise TreasuryError("invalid_limit", "max_amount must be >= amount")

        row = CapitalAllocation(
            pool_id=pool_id,
            target_type=target_type,
            target_id=target_id,
            amount=amount,
            max_amount=max_amount,
            status=CapitalAllocationStatus.REQUESTED.value,
            notes=notes,
            requested_by_user_id=actor.user.id,
        )
        self.db.add(row)
        self.db.flush()
        self.audit.append(
            action="treasury.allocation.request",
            resource_type="capital_allocation",
            resource_id=str(row.id),
            actor_user_id=actor.user.id,
            payload={
                "pool_id": str(pool_id),
                "target_type": target_type,
                "target_id": target_id,
                "amount": str(amount),
            },
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    def approve_allocation(
        self, allocation_id: uuid.UUID, *, actor: AuthenticatedPrincipal
    ) -> CapitalAllocation:
        row = self.get_allocation(allocation_id)
        if row.status != CapitalAllocationStatus.REQUESTED.value:
            raise TreasuryError(
                "invalid_state", f"Allocation must be 'requested' to approve (is '{row.status}')"
            )
        row.status = CapitalAllocationStatus.APPROVED.value
        row.approved_by_user_id = actor.user.id
        row.approved_at = _utcnow()
        self.audit.append(
            action="treasury.allocation.approve",
            resource_type="capital_allocation",
            resource_id=str(row.id),
            actor_user_id=actor.user.id,
            payload={"amount": str(row.amount)},
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    def reject_allocation(
        self, allocation_id: uuid.UUID, *, reason: str, actor: AuthenticatedPrincipal
    ) -> CapitalAllocation:
        row = self.get_allocation(allocation_id)
        if row.status != CapitalAllocationStatus.REQUESTED.value:
            raise TreasuryError(
                "invalid_state", f"Allocation must be 'requested' to reject (is '{row.status}')"
            )
        row.status = CapitalAllocationStatus.REJECTED.value
        row.rejected_by_user_id = actor.user.id
        row.rejected_at = _utcnow()
        row.rejection_reason = reason
        self.audit.append(
            action="treasury.allocation.reject",
            resource_type="capital_allocation",
            resource_id=str(row.id),
            actor_user_id=actor.user.id,
            payload={"reason": reason},
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    def reserve_allocation(
        self, allocation_id: uuid.UUID, *, actor: AuthenticatedPrincipal
    ) -> CapitalAllocation:
        """Approved -> active. Moves capital from account into the pool and
        writes an internal ledger entry. This never touches an external
        account."""
        row = self.get_allocation(allocation_id)
        if row.status != CapitalAllocationStatus.APPROVED.value:
            raise TreasuryError(
                "invalid_state", f"Allocation must be 'approved' to reserve (is '{row.status}')"
            )
        pool = self.get_pool(row.pool_id)
        account = self.get_account(pool.account_id)
        if account.balance < row.amount:
            raise TreasuryError(
                "insufficient_balance",
                f"Account balance {account.balance} is less than allocation amount {row.amount}",
            )

        account.balance = account.balance - row.amount
        pool.balance = pool.balance + row.amount
        reservation = CapitalReservation(
            allocation_id=row.id,
            amount=row.amount,
            status="active",
            reserved_by_user_id=actor.user.id,
        )
        self.db.add(reservation)
        entry = TreasuryLedgerEntry(
            account_id=account.id,
            pool_id=pool.id,
            allocation_id=row.id,
            entry_type="allocation_reserved",
            amount=-row.amount,
            balance_after=account.balance,
            reference_type="capital_allocation",
            reference_id=str(row.id),
            note=f"Reserved for {row.target_type} target",
            created_by_user_id=actor.user.id,
        )
        self.db.add(entry)
        row.status = CapitalAllocationStatus.ACTIVE.value
        self.db.flush()
        self.audit.append(
            action="treasury.allocation.reserve",
            resource_type="capital_allocation",
            resource_id=str(row.id),
            actor_user_id=actor.user.id,
            payload={"amount": str(row.amount), "reservation_id": str(reservation.id)},
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    def release_allocation(
        self, allocation_id: uuid.UUID, *, actor: AuthenticatedPrincipal
    ) -> CapitalAllocation:
        """Active -> released. Returns capital to the account balance."""
        row = self.get_allocation(allocation_id)
        if row.status != CapitalAllocationStatus.ACTIVE.value:
            raise TreasuryError(
                "invalid_state", f"Allocation must be 'active' to release (is '{row.status}')"
            )
        reservation = self.db.scalar(
            select(CapitalReservation).where(
                CapitalReservation.allocation_id == row.id,
                CapitalReservation.status == "active",
            )
        )
        if reservation is None:
            raise TreasuryError("corrupt_state", "Active allocation has no active reservation")

        pool = self.get_pool(row.pool_id)
        account = self.get_account(pool.account_id)
        account.balance = account.balance + row.amount
        pool.balance = pool.balance - row.amount
        reservation.status = "released"
        reservation.released_at = _utcnow()
        reservation.released_by_user_id = actor.user.id
        entry = TreasuryLedgerEntry(
            account_id=account.id,
            pool_id=pool.id,
            allocation_id=row.id,
            entry_type="allocation_released",
            amount=row.amount,
            balance_after=account.balance,
            reference_type="capital_allocation",
            reference_id=str(row.id),
            note="Reservation released back to account",
            created_by_user_id=actor.user.id,
        )
        self.db.add(entry)
        row.status = CapitalAllocationStatus.RELEASED.value
        row.released_by_user_id = actor.user.id
        row.released_at = _utcnow()
        self.db.flush()
        self.audit.append(
            action="treasury.allocation.release",
            resource_type="capital_allocation",
            resource_id=str(row.id),
            actor_user_id=actor.user.id,
            payload={"amount": str(row.amount)},
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    # --- reservations (read) --------------------------------------------

    def list_reservations(self, allocation_id: uuid.UUID | None = None) -> list[CapitalReservation]:
        stmt = select(CapitalReservation).order_by(CapitalReservation.reserved_at.desc())
        if allocation_id is not None:
            stmt = stmt.where(CapitalReservation.allocation_id == allocation_id)
        return list(self.db.scalars(stmt))

    # --- ledger (read) ---------------------------------------------------

    def list_ledger_entries(
        self, *, account_id: uuid.UUID | None = None, limit: int = 100
    ) -> list[TreasuryLedgerEntry]:
        safe_limit = min(max(limit, 1), 500)
        stmt = select(TreasuryLedgerEntry).order_by(TreasuryLedgerEntry.created_at.desc())
        if account_id is not None:
            stmt = stmt.where(TreasuryLedgerEntry.account_id == account_id)
        stmt = stmt.limit(safe_limit)
        return list(self.db.scalars(stmt))

    # --- external transfer instructions (never executed) ----------------

    def list_external_transfers(
        self, *, account_id: uuid.UUID | None = None
    ) -> list[ExternalTransferInstruction]:
        stmt = select(ExternalTransferInstruction).order_by(
            ExternalTransferInstruction.created_at.desc()
        )
        if account_id is not None:
            stmt = stmt.where(ExternalTransferInstruction.account_id == account_id)
        return list(self.db.scalars(stmt))

    def get_external_transfer(self, instruction_id: uuid.UUID) -> ExternalTransferInstruction:
        row = self.db.get(ExternalTransferInstruction, instruction_id)
        if row is None:
            raise TreasuryError(
                "not_found", f"External transfer instruction {instruction_id} not found"
            )
        return row

    def create_external_transfer(
        self,
        *,
        account_id: uuid.UUID,
        direction: str,
        amount: Decimal,
        currency: str,
        destination_reference: str,
        actor: AuthenticatedPrincipal,
    ) -> ExternalTransferInstruction:
        self.get_account(account_id)
        try:
            ExternalTransferDirection(direction)
        except ValueError as exc:
            raise TreasuryError("invalid_direction", f"Unknown direction: {direction}") from exc
        if amount <= 0:
            raise TreasuryError("invalid_amount", "amount must be positive")

        row = ExternalTransferInstruction(
            account_id=account_id,
            direction=direction,
            amount=amount,
            currency=currency,
            destination_reference=destination_reference,
            status=ExternalTransferStatus.DRAFT.value,
            environment_label="simulated",
            created_by_user_id=actor.user.id,
        )
        self.db.add(row)
        self.db.flush()
        self.audit.append(
            action="treasury.external_transfer.create",
            resource_type="external_transfer_instruction",
            resource_id=str(row.id),
            actor_user_id=actor.user.id,
            payload={"direction": direction, "amount": str(amount)},
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    def propose_external_transfer(
        self, instruction_id: uuid.UUID, *, actor: AuthenticatedPrincipal
    ) -> ExternalTransferInstruction:
        row = self.get_external_transfer(instruction_id)
        if row.status != ExternalTransferStatus.DRAFT.value:
            raise TreasuryError(
                "invalid_state", f"Instruction must be 'draft' to propose (is '{row.status}')"
            )
        row.status = ExternalTransferStatus.PROPOSED.value
        row.proposed_by_user_id = actor.user.id
        row.proposed_at = _utcnow()
        self.audit.append(
            action="treasury.external_transfer.propose",
            resource_type="external_transfer_instruction",
            resource_id=str(row.id),
            actor_user_id=actor.user.id,
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    def cancel_external_transfer(
        self, instruction_id: uuid.UUID, *, reason: str | None, actor: AuthenticatedPrincipal
    ) -> ExternalTransferInstruction:
        row = self.get_external_transfer(instruction_id)
        cancellable_states = (
            ExternalTransferStatus.DRAFT.value,
            ExternalTransferStatus.PROPOSED.value,
        )
        if row.status not in cancellable_states:
            raise TreasuryError(
                "invalid_state", f"Instruction cannot be cancelled from state '{row.status}'"
            )
        row.status = ExternalTransferStatus.CANCELLED.value
        row.cancelled_by_user_id = actor.user.id
        row.cancelled_at = _utcnow()
        row.cancellation_reason = reason
        self.audit.append(
            action="treasury.external_transfer.cancel",
            resource_type="external_transfer_instruction",
            resource_id=str(row.id),
            actor_user_id=actor.user.id,
            payload={"reason": reason},
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    def attempt_execute_transfer(
        self, instruction_id: uuid.UUID, *, actor: AuthenticatedPrincipal
    ) -> None:
        """Always refuses. Records the attempt (fail-closed, auditable) and
        raises ``external_transfer_execution_forbidden``. There is no
        successful return from this method, ever, in this codebase."""
        row = self.get_external_transfer(instruction_id)
        row.execution_attempted_at = _utcnow()
        row.execution_attempt_count = row.execution_attempt_count + 1
        row.blocked_reason = (
            "External transfer execution is not implemented and is permanently "
            "forbidden in this system (see ADR-030 and AGENTS.md: no withdrawals "
            "of real money)."
        )
        self.audit.append(
            action="treasury.external_transfer.execute_attempt_blocked",
            resource_type="external_transfer_instruction",
            resource_id=str(row.id),
            actor_user_id=actor.user.id,
            payload={
                "attempt_count": row.execution_attempt_count,
                "blocked_reason": row.blocked_reason,
            },
        )
        self.db.commit()
        raise TreasuryError("external_transfer_execution_forbidden", row.blocked_reason)
