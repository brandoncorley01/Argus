"""Convenience entrypoint: `python -m workers.health_supervisor.main`.

Equivalent to running:

    arq workers.health_supervisor.worker.WorkerSettings

See workers/README.md for PYTHONPATH / Docker Compose setup.
"""

from __future__ import annotations

from arq import run_worker

from workers.health_supervisor.worker import WorkerSettings


def main() -> None:
    run_worker(WorkerSettings)  # type: ignore[arg-type]


if __name__ == "__main__":
    main()
