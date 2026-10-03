FROM python:3.13-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 DQC_ROOT=/app

# 1) dependencies only (cached unless pyproject.toml changes): install against a stub package
COPY pyproject.toml ./
RUN mkdir -p src/dqc && touch src/dqc/__init__.py \
    && pip install ".[dashboard,copilot,orchestration]"

# 2) the real package, without touching the dependency layer
COPY src ./src
RUN pip install --no-deps --force-reinstall .

COPY config ./config
COPY infra/postgres ./infra/postgres
COPY api ./api
COPY dashboard ./dashboard

# run as an unprivileged user
RUN useradd --create-home --uid 10001 app && chown -R app:app /app
USER app

EXPOSE 8000 8501
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
