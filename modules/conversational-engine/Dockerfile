# Multi-stage build, Python 3.12-slim base.
FROM python:3.12-slim AS builder
WORKDIR /build
RUN pip install --no-cache-dir uv
COPY pyproject.toml ./
COPY src ./src
COPY README.md ./
RUN uv pip install --system --no-cache .

FROM python:3.12-slim
WORKDIR /app
RUN useradd --create-home --uid 10001 appuser
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY src ./src
COPY alembic.ini ./
COPY alembic ./alembic
ENV PYTHONPATH=/app/src
USER appuser
EXPOSE 8081
CMD ["uvicorn", "conversational_engine.main:app", "--host", "0.0.0.0", "--port", "8081"]
