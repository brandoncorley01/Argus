FROM python:3.12-slim

WORKDIR /app

# Install API dependencies (shared by worker process).
COPY apps/api/pyproject.toml apps/api/README.md /app/apps/api/
COPY apps/api/app /app/apps/api/app
COPY workers /app/workers

RUN pip install --no-cache-dir \
    "fastapi>=0.115.0" \
    "uvicorn[standard]>=0.32.0" \
    "pydantic-settings>=2.6.0" \
    "sqlalchemy>=2.0.36" \
    "psycopg[binary]>=2.9.10" \
    "redis>=5.2.0" \
    "arq>=0.26.0" \
    "alembic>=1.14.0" \
    "argon2-cffi>=23.1.0"

ENV PYTHONPATH=/app/apps/api:/app
ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "arq", "workers.health_supervisor.worker.WorkerSettings"]
