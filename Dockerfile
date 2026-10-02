FROM python:3.13-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1

COPY pyproject.toml ./
COPY src ./src
RUN pip install ".[dashboard,copilot,orchestration]"

COPY config ./config
COPY infra/postgres ./infra/postgres
COPY api ./api
COPY dashboard ./dashboard

EXPOSE 8000 8501
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
