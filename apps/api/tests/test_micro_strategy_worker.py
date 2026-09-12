"""Dedicated Micro worker topology and safety boundaries."""

from workers.health_supervisor.worker import WorkerSettings as MainWorkerSettings
from workers.micro_strategy.worker import (
    WorkerSettings as MicroWorkerSettings,
    run_micro_strategy_cycle,
)


def test_micro_worker_has_dedicated_serial_queue() -> None:
    assert MicroWorkerSettings.queue_name == "arq:queue:micro_strategy"
    assert MicroWorkerSettings.max_jobs == 1
    assert MicroWorkerSettings.expires_extra_ms == 90_000
    assert MicroWorkerSettings.functions == [run_micro_strategy_cycle]


def test_micro_cycle_is_not_duplicated_on_main_worker() -> None:
    assert run_micro_strategy_cycle not in MainWorkerSettings.functions
    assert MainWorkerSettings.expires_extra_ms == 120_000
