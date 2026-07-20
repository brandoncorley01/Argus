"""Strategy Laboratory service — research governance, no live execution."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.strategy_laboratory import (
    ResearchDataset,
    ResearchRun,
    ResearchRunKind,
    ResearchRunResult,
    ResearchRunStatus,
    StrategyComparison,
    StrategyDocument,
    StrategyLifecycleEvent,
    StrategyLifecycleStatus,
    StrategyVersion,
    ValidationReport,
)
from app.services.audit_service import AuditService
from app.services.strategy_engine import (
    STRATEGY_REGISTRY,
    ExecutionAssumptions,
    StrategyEngineError,
    bars_from_dicts,
    get_strategy,
    hash_request,
    hash_result,
    run_bar_backtest,
    run_monte_carlo,
    run_optimization,
    run_sensitivity,
    run_walk_forward,
)


class StrategyLabError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


# draft → under_review → approved|rejected
# approved → suspended|retired|archived
_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    StrategyLifecycleStatus.DRAFT.value: {StrategyLifecycleStatus.UNDER_REVIEW.value},
    StrategyLifecycleStatus.UNDER_REVIEW.value: {
        StrategyLifecycleStatus.APPROVED.value,
        StrategyLifecycleStatus.REJECTED.value,
    },
    StrategyLifecycleStatus.APPROVED.value: {
        StrategyLifecycleStatus.SUSPENDED.value,
        StrategyLifecycleStatus.RETIRED.value,
        StrategyLifecycleStatus.ARCHIVED.value,
    },
    StrategyLifecycleStatus.SUSPENDED.value: {
        StrategyLifecycleStatus.APPROVED.value,
        StrategyLifecycleStatus.RETIRED.value,
        StrategyLifecycleStatus.ARCHIVED.value,
    },
    StrategyLifecycleStatus.REJECTED.value: {StrategyLifecycleStatus.ARCHIVED.value},
    StrategyLifecycleStatus.RETIRED.value: {StrategyLifecycleStatus.ARCHIVED.value},
    StrategyLifecycleStatus.ARCHIVED.value: set(),
}


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _content_hash_for_version(
    strategy_class: str,
    parameters: dict[str, Any],
    parameter_schema: dict[str, Any],
    code_ref: str,
) -> str:
    return hash_request(
        {
            "strategy_class": strategy_class,
            "parameters": parameters,
            "parameter_schema": parameter_schema,
            "code_ref": code_ref,
        }
    )


class StrategyLaboratoryService:
    def __init__(self, db: Session) -> None:
        self.db = db
        self.audit = AuditService(db)

    # ── Documents ──────────────────────────────────────────────────────────

    def list_documents(self) -> list[StrategyDocument]:
        return list(
            self.db.scalars(
                select(StrategyDocument).order_by(StrategyDocument.created_at.desc())
            )
        )

    def get_document(self, document_id: uuid.UUID) -> StrategyDocument:
        row = self.db.get(StrategyDocument, document_id)
        if row is None:
            raise StrategyLabError("document_not_found", f"Unknown document: {document_id}")
        return row

    def create_document(
        self,
        *,
        strategy_key: str,
        name: str,
        owner_user_id: uuid.UUID,
        description: str | None = None,
        tags: list[Any] | None = None,
        request_id: str | None = None,
    ) -> StrategyDocument:
        existing = self.db.scalar(
            select(StrategyDocument).where(StrategyDocument.strategy_key == strategy_key)
        )
        if existing:
            raise StrategyLabError(
                "duplicate_strategy_key",
                f"Strategy key already exists: {strategy_key}",
            )
        row = StrategyDocument(
            strategy_key=strategy_key,
            name=name,
            description=description,
            owner_user_id=owner_user_id,
            status=StrategyLifecycleStatus.DRAFT.value,
            tags=tags or [],
        )
        self.db.add(row)
        self.db.flush()
        self._lifecycle_event(
            document_id=row.id,
            version_id=None,
            event_type="document.created",
            from_status=None,
            to_status=row.status,
            actor_user_id=owner_user_id,
            reason=None,
        )
        self.audit.append(
            action="strategy_document.created",
            resource_type="strategy_document",
            resource_id=str(row.id),
            actor_user_id=owner_user_id,
            request_id=request_id,
            payload={"strategy_key": strategy_key, "name": name},
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    # ── Versions ───────────────────────────────────────────────────────────

    def list_versions(self, document_id: uuid.UUID) -> list[StrategyVersion]:
        self.get_document(document_id)
        return list(
            self.db.scalars(
                select(StrategyVersion)
                .where(StrategyVersion.document_id == document_id)
                .order_by(StrategyVersion.version_number.asc())
            )
        )

    def get_version(self, version_id: uuid.UUID) -> StrategyVersion:
        row = self.db.get(StrategyVersion, version_id)
        if row is None:
            raise StrategyLabError("version_not_found", f"Unknown version: {version_id}")
        return row

    def create_version(
        self,
        *,
        document_id: uuid.UUID,
        version_label: str,
        strategy_class: str,
        parameters: dict[str, Any],
        created_by_user_id: uuid.UUID,
        parameter_schema: dict[str, Any] | None = None,
        code_ref: str | None = None,
        change_summary: str | None = None,
        request_id: str | None = None,
    ) -> StrategyVersion:
        doc = self.get_document(document_id)
        if strategy_class not in STRATEGY_REGISTRY:
            raise StrategyLabError(
                "unknown_strategy_class",
                f"Strategy class not in research registry: {strategy_class}",
            )
        # Validate params by instantiating strategy once
        try:
            get_strategy(strategy_class)
        except StrategyEngineError as exc:
            raise StrategyLabError(exc.code, exc.message) from exc

        parameter_schema = parameter_schema or {}
        code_ref = code_ref or f"builtin:{strategy_class}"
        next_num = (
            self.db.scalar(
                select(func.coalesce(func.max(StrategyVersion.version_number), 0)).where(
                    StrategyVersion.document_id == document_id
                )
            )
            or 0
        ) + 1

        content_hash = _content_hash_for_version(
            strategy_class, parameters, parameter_schema, code_ref
        )
        row = StrategyVersion(
            document_id=document_id,
            version_number=next_num,
            version_label=version_label,
            status=StrategyLifecycleStatus.DRAFT.value,
            strategy_class=strategy_class,
            parameter_schema=parameter_schema,
            parameters=parameters,
            code_ref=code_ref,
            content_hash=content_hash,
            change_summary=change_summary,
            is_immutable=False,
            created_by_user_id=created_by_user_id,
        )
        self.db.add(row)
        self.db.flush()
        self._lifecycle_event(
            document_id=doc.id,
            version_id=row.id,
            event_type="version.created",
            from_status=None,
            to_status=row.status,
            actor_user_id=created_by_user_id,
            reason=None,
        )
        self.audit.append(
            action="strategy_version.created",
            resource_type="strategy_version",
            resource_id=str(row.id),
            actor_user_id=created_by_user_id,
            request_id=request_id,
            payload={
                "document_id": str(document_id),
                "version_number": next_num,
                "strategy_class": strategy_class,
                "content_hash": content_hash,
            },
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    def update_version_parameters(
        self,
        *,
        version_id: uuid.UUID,
        parameters: dict[str, Any],
        actor_user_id: uuid.UUID,
        request_id: str | None = None,
    ) -> StrategyVersion:
        row = self.get_version(version_id)
        if row.is_immutable or row.status != StrategyLifecycleStatus.DRAFT.value:
            raise StrategyLabError(
                "version_immutable",
                "Cannot mutate parameters after version is immutable / left draft",
            )
        row.parameters = parameters
        row.content_hash = _content_hash_for_version(
            row.strategy_class, parameters, row.parameter_schema, row.code_ref
        )
        self.db.flush()
        self.audit.append(
            action="strategy_version.parameters_updated",
            resource_type="strategy_version",
            resource_id=str(row.id),
            actor_user_id=actor_user_id,
            request_id=request_id,
            payload={"content_hash": row.content_hash},
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    def submit_version(
        self,
        *,
        version_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        request_id: str | None = None,
    ) -> StrategyVersion:
        return self._transition_version(
            version_id=version_id,
            to_status=StrategyLifecycleStatus.UNDER_REVIEW.value,
            actor_user_id=actor_user_id,
            reason=None,
            request_id=request_id,
            freeze=True,
            stamp_field="submitted_at",
        )

    def approve_version(
        self,
        *,
        version_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        request_id: str | None = None,
    ) -> StrategyVersion:
        return self._transition_version(
            version_id=version_id,
            to_status=StrategyLifecycleStatus.APPROVED.value,
            actor_user_id=actor_user_id,
            reason=None,
            request_id=request_id,
            stamp_field="approved_at",
        )

    def reject_version(
        self,
        *,
        version_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        reason: str,
        request_id: str | None = None,
    ) -> StrategyVersion:
        if not reason or not reason.strip():
            raise StrategyLabError("reason_required", "Rejection requires a reason")
        row = self._transition_version(
            version_id=version_id,
            to_status=StrategyLifecycleStatus.REJECTED.value,
            actor_user_id=actor_user_id,
            reason=reason.strip(),
            request_id=request_id,
            stamp_field="rejected_at",
        )
        row.rejection_reason = reason.strip()
        self.db.flush()
        self.db.commit()
        self.db.refresh(row)
        return row

    def suspend_version(
        self,
        *,
        version_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        reason: str,
        request_id: str | None = None,
    ) -> StrategyVersion:
        if not reason or not reason.strip():
            raise StrategyLabError("reason_required", "Suspension requires a reason")
        row = self._transition_version(
            version_id=version_id,
            to_status=StrategyLifecycleStatus.SUSPENDED.value,
            actor_user_id=actor_user_id,
            reason=reason.strip(),
            request_id=request_id,
            stamp_field="suspended_at",
        )
        row.suspension_reason = reason.strip()
        self.db.flush()
        self.db.commit()
        self.db.refresh(row)
        return row

    def retire_version(
        self,
        *,
        version_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        request_id: str | None = None,
    ) -> StrategyVersion:
        return self._transition_version(
            version_id=version_id,
            to_status=StrategyLifecycleStatus.RETIRED.value,
            actor_user_id=actor_user_id,
            reason=None,
            request_id=request_id,
            stamp_field="retired_at",
        )

    def archive_version(
        self,
        *,
        version_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        request_id: str | None = None,
    ) -> StrategyVersion:
        return self._transition_version(
            version_id=version_id,
            to_status=StrategyLifecycleStatus.ARCHIVED.value,
            actor_user_id=actor_user_id,
            reason=None,
            request_id=request_id,
        )

    def _transition_version(
        self,
        *,
        version_id: uuid.UUID,
        to_status: str,
        actor_user_id: uuid.UUID,
        reason: str | None,
        request_id: str | None,
        freeze: bool = False,
        stamp_field: str | None = None,
    ) -> StrategyVersion:
        row = self.get_version(version_id)
        allowed = _ALLOWED_TRANSITIONS.get(row.status, set())
        if to_status not in allowed:
            raise StrategyLabError(
                "invalid_transition",
                f"Cannot transition version from {row.status} to {to_status}",
            )
        from_status = row.status
        row.status = to_status
        if freeze:
            row.is_immutable = True
        if stamp_field:
            setattr(row, stamp_field, _utcnow())

        doc = self.get_document(row.document_id)
        doc.status = to_status
        doc.updated_at = _utcnow()

        self.db.flush()
        self._lifecycle_event(
            document_id=row.document_id,
            version_id=row.id,
            event_type=f"version.{to_status}",
            from_status=from_status,
            to_status=to_status,
            actor_user_id=actor_user_id,
            reason=reason,
        )
        self.audit.append(
            action=f"strategy_version.{to_status}",
            resource_type="strategy_version",
            resource_id=str(row.id),
            actor_user_id=actor_user_id,
            request_id=request_id,
            payload={
                "from_status": from_status,
                "to_status": to_status,
                "reason": reason,
                "is_immutable": row.is_immutable,
            },
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    def _lifecycle_event(
        self,
        *,
        document_id: uuid.UUID,
        version_id: uuid.UUID | None,
        event_type: str,
        from_status: str | None,
        to_status: str | None,
        actor_user_id: uuid.UUID | None,
        reason: str | None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        self.db.add(
            StrategyLifecycleEvent(
                document_id=document_id,
                version_id=version_id,
                event_type=event_type,
                from_status=from_status,
                to_status=to_status,
                actor_user_id=actor_user_id,
                reason=reason,
                payload=payload or {},
            )
        )

    # ── Datasets ───────────────────────────────────────────────────────────

    def list_datasets(self) -> list[ResearchDataset]:
        return list(
            self.db.scalars(
                select(ResearchDataset).order_by(ResearchDataset.created_at.desc())
            )
        )

    def get_dataset(self, dataset_id: uuid.UUID) -> ResearchDataset:
        row = self.db.get(ResearchDataset, dataset_id)
        if row is None:
            raise StrategyLabError("dataset_not_found", f"Unknown dataset: {dataset_id}")
        return row

    def register_dataset(
        self,
        *,
        dataset_key: str,
        name: str,
        provenance: str,
        source_kind: str,
        bars: list[dict[str, Any]],
        actor_user_id: uuid.UUID,
        metadata_json: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> ResearchDataset:
        existing = self.db.scalar(
            select(ResearchDataset).where(ResearchDataset.dataset_key == dataset_key)
        )
        if existing:
            raise StrategyLabError(
                "duplicate_dataset_key",
                f"Dataset key already exists: {dataset_key}",
            )
        if not provenance or not provenance.strip():
            raise StrategyLabError("provenance_required", "Dataset provenance is required")
        content_hash = hash_request({"bars": bars})
        meta = dict(metadata_json or {})
        meta["bars"] = bars
        meta["synthetic_research_fixture"] = meta.get(
            "synthetic_research_fixture", source_kind == "synthetic"
        )
        row = ResearchDataset(
            dataset_key=dataset_key,
            name=name,
            provenance=provenance.strip(),
            source_kind=source_kind,
            content_hash=content_hash,
            bar_count=len(bars),
            metadata_json=meta,
        )
        self.db.add(row)
        self.db.flush()
        self.audit.append(
            action="research_dataset.registered",
            resource_type="research_dataset",
            resource_id=str(row.id),
            actor_user_id=actor_user_id,
            request_id=request_id,
            payload={
                "dataset_key": dataset_key,
                "content_hash": content_hash,
                "bar_count": len(bars),
                "provenance": provenance.strip(),
            },
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    def _load_bars(self, dataset: ResearchDataset) -> list[Any]:
        raw = (dataset.metadata_json or {}).get("bars")
        if not raw:
            raise StrategyLabError(
                "dataset_empty",
                f"Dataset {dataset.id} has no bars for research execution",
            )
        return bars_from_dicts(raw)

    # ── Research runs ──────────────────────────────────────────────────────

    def list_runs(
        self,
        *,
        strategy_version_id: uuid.UUID | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[ResearchRun]:
        stmt = select(ResearchRun).order_by(ResearchRun.created_at.desc())
        if strategy_version_id is not None:
            stmt = stmt.where(ResearchRun.strategy_version_id == strategy_version_id)
        stmt = stmt.limit(limit).offset(offset)
        return list(self.db.scalars(stmt))

    def get_run(self, run_id: uuid.UUID) -> ResearchRun:
        row = self.db.get(ResearchRun, run_id)
        if row is None:
            raise StrategyLabError("run_not_found", f"Unknown run: {run_id}")
        return row

    def get_result(self, run_id: uuid.UUID) -> ResearchRunResult:
        row = self.db.scalar(
            select(ResearchRunResult).where(ResearchRunResult.run_id == run_id)
        )
        if row is None:
            raise StrategyLabError("result_not_found", f"No result for run: {run_id}")
        return row

    def create_run(
        self,
        *,
        kind: str,
        strategy_version_id: uuid.UUID,
        dataset_id: uuid.UUID,
        created_by_user_id: uuid.UUID,
        execution_assumptions: dict[str, Any] | None = None,
        parameters: dict[str, Any] | None = None,
        budget: dict[str, Any] | None = None,
        random_seed: int = 42,
        request_id: str | None = None,
        execute: bool = True,
    ) -> ResearchRun:
        if kind not in {k.value for k in ResearchRunKind}:
            raise StrategyLabError("invalid_run_kind", f"Unsupported run kind: {kind}")
        if kind == ResearchRunKind.COMPARISON.value:
            raise StrategyLabError(
                "invalid_run_kind",
                "Use the comparisons API for strategy comparisons",
            )

        version = self.get_version(strategy_version_id)
        dataset = self.get_dataset(dataset_id)
        assumptions = execution_assumptions or {}
        params = parameters or dict(version.parameters)
        budget = budget or {}

        request_payload = {
            "kind": kind,
            "strategy_version_id": str(strategy_version_id),
            "dataset_id": str(dataset_id),
            "dataset_content_hash": dataset.content_hash,
            "version_content_hash": version.content_hash,
            "execution_assumptions": assumptions,
            "parameters": params,
            "budget": budget,
            "random_seed": random_seed,
        }
        req_hash = hash_request(request_payload)

        run = ResearchRun(
            kind=kind,
            status=ResearchRunStatus.QUEUED.value,
            strategy_version_id=strategy_version_id,
            dataset_id=dataset_id,
            request_hash=req_hash,
            random_seed=random_seed,
            execution_assumptions=assumptions,
            parameters=params,
            budget=budget,
            cancel_requested=False,
            created_by_user_id=created_by_user_id,
        )
        self.db.add(run)
        self.db.flush()
        self.audit.append(
            action="research_run.created",
            resource_type="research_run",
            resource_id=str(run.id),
            actor_user_id=created_by_user_id,
            request_id=request_id,
            payload={"kind": kind, "request_hash": req_hash},
        )
        self.db.commit()
        self.db.refresh(run)

        if execute:
            run = self.execute_run(run_id=run.id, request_id=request_id)
        return run

    def cancel_run(
        self,
        *,
        run_id: uuid.UUID,
        actor_user_id: uuid.UUID,
        request_id: str | None = None,
    ) -> ResearchRun:
        run = self.get_run(run_id)
        if run.status in {
            ResearchRunStatus.SUCCEEDED.value,
            ResearchRunStatus.FAILED.value,
            ResearchRunStatus.CANCELLED.value,
        }:
            raise StrategyLabError(
                "run_not_cancellable",
                f"Run already finished with status {run.status}",
            )
        run.cancel_requested = True
        if run.status == ResearchRunStatus.QUEUED.value:
            run.status = ResearchRunStatus.CANCELLED.value
            run.finished_at = _utcnow()
        self.db.flush()
        self.audit.append(
            action="research_run.cancel_requested",
            resource_type="research_run",
            resource_id=str(run.id),
            actor_user_id=actor_user_id,
            request_id=request_id,
            payload={"status": run.status},
        )
        self.db.commit()
        self.db.refresh(run)
        return run

    def execute_run(
        self,
        *,
        run_id: uuid.UUID,
        request_id: str | None = None,
    ) -> ResearchRun:
        run = self.get_run(run_id)
        self.db.refresh(run)
        if run.cancel_requested:
            run.status = ResearchRunStatus.CANCELLED.value
            run.finished_at = _utcnow()
            self.db.commit()
            self.db.refresh(run)
            return run

        version = self.get_version(run.strategy_version_id)
        dataset = self.get_dataset(run.dataset_id)
        bars = self._load_bars(dataset)

        run.status = ResearchRunStatus.RUNNING.value
        run.started_at = _utcnow()
        self.db.flush()
        self.db.commit()

        # Re-check cancel after marking running (small fixtures execute sync)
        self.db.refresh(run)
        if run.cancel_requested:
            run.status = ResearchRunStatus.CANCELLED.value
            run.finished_at = _utcnow()
            self.db.commit()
            self.db.refresh(run)
            return run

        try:
            assumptions = ExecutionAssumptions(**(run.execution_assumptions or {}))
            result_payload = self._dispatch_engine(
                kind=run.kind,
                bars=bars,
                strategy_class=version.strategy_class,
                params=run.parameters or {},
                assumptions=assumptions,
                seed=run.random_seed,
                budget=run.budget or {},
            )
            result_hash = hash_result(
                {
                    "metrics": result_payload.get("metrics", {}),
                    "equity_curve": result_payload.get("equity_curve", []),
                    "trades": result_payload.get("trades", []),
                    "diagnostics": result_payload.get("diagnostics", {}),
                    "in_sample_metrics": result_payload.get("in_sample_metrics", {}),
                    "out_of_sample_metrics": result_payload.get(
                        "out_of_sample_metrics", {}
                    ),
                }
            )
            result = ResearchRunResult(
                run_id=run.id,
                is_immutable=True,
                metrics=result_payload.get("metrics", {}),
                equity_curve=result_payload.get("equity_curve", []),
                trades=result_payload.get("trades", []),
                diagnostics=result_payload.get("diagnostics", {}),
                in_sample_metrics=result_payload.get("in_sample_metrics", {}),
                out_of_sample_metrics=result_payload.get("out_of_sample_metrics", {}),
                result_hash=result_hash,
            )
            self.db.add(result)
            run.status = ResearchRunStatus.SUCCEEDED.value
            run.finished_at = _utcnow()
            self.db.flush()
            self.audit.append(
                action="research_run.completed",
                resource_type="research_run",
                resource_id=str(run.id),
                actor_user_id=run.created_by_user_id,
                request_id=request_id,
                payload={
                    "status": run.status,
                    "result_hash": result_hash,
                    "request_hash": run.request_hash,
                },
            )
            self.db.commit()
        except (StrategyEngineError, StrategyLabError, TypeError, ValueError) as exc:
            code = getattr(exc, "code", "execution_error")
            message = getattr(exc, "message", str(exc))
            run.status = ResearchRunStatus.FAILED.value
            run.error_summary = f"{code}: {message}"
            run.finished_at = _utcnow()
            self.db.flush()
            self.audit.append(
                action="research_run.failed",
                resource_type="research_run",
                resource_id=str(run.id),
                actor_user_id=run.created_by_user_id,
                request_id=request_id,
                payload={"error": run.error_summary},
            )
            self.db.commit()

        self.db.refresh(run)
        return run

    def _dispatch_engine(
        self,
        *,
        kind: str,
        bars: list[Any],
        strategy_class: str,
        params: dict[str, Any],
        assumptions: ExecutionAssumptions,
        seed: int,
        budget: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            if kind == ResearchRunKind.BACKTEST.value:
                bt = run_bar_backtest(bars, strategy_class, params, assumptions, seed)
                return {
                    "metrics": bt.metrics,
                    "equity_curve": bt.equity_curve,
                    "trades": bt.trades,
                    "diagnostics": bt.diagnostics,
                    "in_sample_metrics": {},
                    "out_of_sample_metrics": {},
                }
            if kind == ResearchRunKind.WALK_FORWARD.value:
                return run_walk_forward(
                    bars,
                    strategy_class,
                    params,
                    assumptions,
                    seed,
                    train_frac=float(budget.get("train_frac", 0.6)),
                    val_frac=float(budget.get("val_frac", 0.2)),
                    test_frac=float(budget.get("test_frac", 0.2)),
                )
            if kind == ResearchRunKind.OPTIMIZATION.value:
                max_trials = budget.get("max_trials")
                param_grid = budget.get("param_grid") or params.get("param_grid") or {}
                return run_optimization(
                    bars,
                    strategy_class,
                    assumptions,
                    param_grid=param_grid,
                    max_trials=int(max_trials) if max_trials is not None else 0,
                    seed=seed,
                )
            if kind == ResearchRunKind.MONTE_CARLO.value:
                # First run a backtest to get equity, then shuffle returns
                bt = run_bar_backtest(bars, strategy_class, params, assumptions, seed)
                equity = [pt["equity"] for pt in bt.equity_curve]
                n_sims = int(budget.get("n_sims", 100))
                mc = run_monte_carlo(equity, n_sims=n_sims, seed=seed)
                mc["diagnostics"] = {
                    **mc["diagnostics"],
                    "base_backtest_metrics": bt.metrics,
                }
                return mc
            if kind == ResearchRunKind.SENSITIVITY.value:
                param_name = budget.get("param_name") or params.get("param_name")
                deltas = budget.get("deltas") or params.get("deltas") or []
                if not param_name:
                    raise StrategyLabError(
                        "param_name_required",
                        "Sensitivity runs require budget.param_name",
                    )
                return run_sensitivity(
                    bars,
                    strategy_class,
                    params,
                    assumptions,
                    param_name=str(param_name),
                    deltas=[float(d) for d in deltas],
                    seed=seed,
                )
            raise StrategyLabError("invalid_run_kind", f"Unsupported run kind: {kind}")
        except StrategyEngineError as exc:
            raise StrategyLabError(exc.code, exc.message) from exc

    # ── Validation reports ─────────────────────────────────────────────────

    def list_validation_reports(
        self, strategy_version_id: uuid.UUID | None = None
    ) -> list[ValidationReport]:
        stmt = select(ValidationReport).order_by(ValidationReport.created_at.desc())
        if strategy_version_id is not None:
            stmt = stmt.where(ValidationReport.strategy_version_id == strategy_version_id)
        return list(self.db.scalars(stmt))

    def create_validation_report(
        self,
        *,
        strategy_version_id: uuid.UUID,
        title: str,
        verdict: str,
        summary: str,
        created_by_user_id: uuid.UUID,
        run_id: uuid.UUID | None = None,
        evidence: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> ValidationReport:
        self.get_version(strategy_version_id)
        if run_id is not None:
            self.get_run(run_id)
        row = ValidationReport(
            strategy_version_id=strategy_version_id,
            run_id=run_id,
            title=title,
            verdict=verdict,
            summary=summary,
            evidence=evidence or {},
            created_by_user_id=created_by_user_id,
        )
        self.db.add(row)
        self.db.flush()
        self.audit.append(
            action="strategy_validation_report.created",
            resource_type="strategy_validation_report",
            resource_id=str(row.id),
            actor_user_id=created_by_user_id,
            request_id=request_id,
            payload={"verdict": verdict, "title": title},
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    # ── Comparisons ────────────────────────────────────────────────────────

    def list_comparisons(self) -> list[StrategyComparison]:
        return list(
            self.db.scalars(
                select(StrategyComparison).order_by(StrategyComparison.created_at.desc())
            )
        )

    def create_comparison(
        self,
        *,
        dataset_id: uuid.UUID,
        version_ids: list[uuid.UUID],
        execution_assumptions: dict[str, Any],
        created_by_user_id: uuid.UUID,
        request_id: str | None = None,
    ) -> StrategyComparison:
        if len(version_ids) < 2:
            raise StrategyLabError(
                "comparison_requires_versions",
                "Comparison requires at least two strategy versions",
            )
        dataset = self.get_dataset(dataset_id)
        assumptions_hash = hash_request(execution_assumptions or {})
        bars = self._load_bars(dataset)
        assumptions = ExecutionAssumptions(**(execution_assumptions or {}))

        results: dict[str, Any] = {"versions": {}}
        for vid in version_ids:
            version = self.get_version(vid)
            bt = run_bar_backtest(
                bars,
                version.strategy_class,
                version.parameters or {},
                assumptions,
                seed=42,
            )
            results["versions"][str(vid)] = {
                "strategy_class": version.strategy_class,
                "content_hash": version.content_hash,
                "metrics": bt.metrics,
                "result_hash": hash_result(
                    {
                        "metrics": bt.metrics,
                        "equity_curve": bt.equity_curve,
                        "trades": bt.trades,
                    }
                ),
            }

        row = StrategyComparison(
            dataset_id=dataset_id,
            version_ids=[str(v) for v in version_ids],
            assumptions_hash=assumptions_hash,
            results=results,
            created_by_user_id=created_by_user_id,
        )
        self.db.add(row)
        self.db.flush()
        self.audit.append(
            action="strategy_comparison.created",
            resource_type="strategy_comparison",
            resource_id=str(row.id),
            actor_user_id=created_by_user_id,
            request_id=request_id,
            payload={
                "dataset_id": str(dataset_id),
                "assumptions_hash": assumptions_hash,
                "version_ids": [str(v) for v in version_ids],
            },
        )
        self.db.commit()
        self.db.refresh(row)
        return row

    @staticmethod
    def registered_strategy_classes() -> list[str]:
        return sorted(STRATEGY_REGISTRY.keys())
