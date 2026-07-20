from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from alembic import command
from app.core.settings import clear_settings_cache, get_settings
from app.db.session import reset_engine

API_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TABLES = {
    "alembic_version",
    "institutional_identities",
    "users",
    "user_roles",
    "auth_sessions",
    "login_attempts",
    "audit_events",
    "configuration_documents",
    "configuration_versions",
    "policy_documents",
    "policy_versions",
    "feature_registry_entries",
    "department_capabilities",
    "system_states",
    "operating_mode_history",
    "operating_mode_idempotency",
    "service_health_events",
    "incidents",
    "registered_services",
    "worker_identities",
    "worker_instances",
    "health_heartbeats",
    "health_heartbeat_idempotency",
    "service_health_projections",
    "institutional_health_state",
    "health_supervisor_leases",
    "incident_lifecycle_events",
    "protective_action_recommendations",
    "market_providers",
    "market_provider_health",
    "market_instruments",
    "market_ingestion_runs",
    "market_observations",
    "market_ohlcv_bars",
    "market_news_items",
    "market_economic_events",
    "market_research_items",
    "market_quality_findings",
    "market_ingestion_idempotency",
    "strategy_documents",
    "strategy_versions",
    "strategy_lifecycle_events",
    "research_datasets",
    "research_runs",
    "research_run_results",
    "strategy_validation_reports",
    "strategy_comparisons",
    "execution_providers",
    "execution_provider_health",
    "paper_portfolios",
    "paper_sessions",
    "paper_orders",
    "paper_order_events",
    "paper_fills",
    "paper_positions",
    "paper_cash_ledger",
    "paper_risk_limits",
    "paper_risk_breaches",
    "paper_replay_checkpoints",
    "paper_reports",
    "live_activation_state",
    "live_activation_transitions",
    "credential_references",
    "kill_switches",
    "micro_capital_policies",
    "reconciliation_runs",
    "reconciliation_discrepancies",
}


def _alembic_config() -> Config:
    return Config(str(API_ROOT / "alembic.ini"))


def test_migration_upgrade_downgrade_reupgrade_cycle() -> None:
    clear_settings_cache()
    reset_engine()
    cfg = _alembic_config()
    engine = create_engine(get_settings().database_url)

    command.downgrade(cfg, "base")
    command.upgrade(cfg, "head")

    insp = inspect(engine)
    tables = set(insp.get_table_names())
    assert EXPECTED_TABLES.issubset(tables)

    with engine.connect() as conn:
        version = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "f2a3b4c5d6e7"

    command.downgrade(cfg, "base")
    insp_after_down = inspect(engine)
    remaining = set(insp_after_down.get_table_names()) - {"alembic_version"}
    # After base, application tables should be gone.
    assert not (EXPECTED_TABLES - {"alembic_version"}).intersection(remaining)

    command.upgrade(cfg, "head")
    insp_final = inspect(engine)
    assert EXPECTED_TABLES.issubset(set(insp_final.get_table_names()))

    reset_engine()
    clear_settings_cache()
