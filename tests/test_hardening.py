"""Security and resilience: no credential defaults, authenticated writes, download retries."""

from __future__ import annotations

import re
import urllib.error
from pathlib import Path

import pytest

from dqc import config, db, ingest

ROOT = Path(__file__).resolve().parents[1]


def test_no_database_password_has_a_default(monkeypatch):
    monkeypatch.delenv("DQC_PG_PASSWORD", raising=False)
    monkeypatch.delenv("DQC_READER_PASSWORD", raising=False)
    assert config.role_dsn() is None
    assert config.role_dsn("dqc_reader", "DQC_READER_PASSWORD") is None


def test_role_dsn_quotes_special_characters(monkeypatch):
    monkeypatch.setenv("DQC_PG_PASSWORD", "p@ss/w:rd")
    assert "p%40ss%2Fw%3Ard@" in config.role_dsn()


def test_connect_without_credentials_fails_with_an_explicit_message(monkeypatch):
    monkeypatch.setattr(config, "PG_DSN", None)
    with pytest.raises(RuntimeError, match="DQC_PG_PASSWORD"), db.connect():
        pass


def test_repository_contains_no_hardcoded_credentials():
    """Guards against a credential being committed again (CI-only throwaway values are allowed)."""
    patterns = [r"postgresql://\w+:\w+@", r"PASSWORD\s+'[^']+'", r"(?m)^\s*POSTGRES_PASSWORD:\s*(?!\$|ci-ephemeral)\S+",
                r"(?m)^\s*\w*ADMIN_PASSWORD:\s*(?!\$)\S+", r"sk-ant-[A-Za-z0-9]"]
    skip_dirs = {".git", "data", "reports", "models", "__pycache__", ".pytest_cache", ".ruff_cache", "target", "logs"}
    offenders = []
    for path in ROOT.rglob("*"):
        if (not path.is_file() or skip_dirs & set(path.parts) or path.name in (".env", "test_hardening.py")
                or path.suffix not in {".py", ".yml", ".yaml", ".sql", ".sh", ".toml", ".md", ".example", ""}):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        offenders += [f"{path.relative_to(ROOT)}: {p}" for p in patterns if re.search(p, text)]
    assert offenders == []


# ---------------------------------------------------------------- API authentication
@pytest.fixture
def client(monkeypatch):
    from fastapi.testclient import TestClient

    import api.main as api_main
    monkeypatch.setattr(api_main, "q", lambda *a, **k: [])
    return TestClient(api_main.app)


WRITES = [("patch", "/quarantine/1/review", {"status": "false_positive", "reviewer": "t"}),
          ("post", "/copilot/explain", None),
          ("patch", "/copilot/suggestions/1", {"status": "accepted", "reviewer": "t"})]


@pytest.mark.parametrize("method,url,body", WRITES)
def test_write_endpoints_are_disabled_when_no_key_is_configured(client, monkeypatch, method, url, body):
    monkeypatch.delenv("DQC_API_KEY", raising=False)
    assert getattr(client, method)(url, json=body).status_code == 503


@pytest.mark.parametrize("method,url,body", WRITES)
def test_write_endpoints_reject_a_missing_or_wrong_key(client, monkeypatch, method, url, body):
    monkeypatch.setenv("DQC_API_KEY", "correct-key")
    assert getattr(client, method)(url, json=body).status_code == 401
    assert getattr(client, method)(url, json=body, headers={"X-API-Key": "wrong"}).status_code == 401


def test_read_endpoints_need_no_key(client, monkeypatch):
    monkeypatch.delenv("DQC_API_KEY", raising=False)
    assert client.get("/rules").status_code == 200


# ---------------------------------------------------------------- download retries
def _http_error(code):
    return urllib.error.HTTPError("http://x", code, "err", {}, None)


def test_transient_download_failures_are_retried_with_backoff(monkeypatch, tmp_path):
    calls, sleeps = [], []
    outcomes = [urllib.error.URLError("reset"), _http_error(503), {"last_modified": None, "etag": None}]

    def once(url, dest):
        calls.append(url)
        out = outcomes[len(calls) - 1]
        if isinstance(out, Exception):
            raise out
        return out

    monkeypatch.setattr(ingest, "_download_once", once)
    monkeypatch.setattr(ingest.time, "sleep", sleeps.append)
    assert ingest._download("http://x", tmp_path / "f", attempts=4, backoff_s=1.0) == outcomes[2]
    assert len(calls) == 3 and sleeps == [1.0, 2.0]          # exponential


def test_client_errors_are_not_retried(monkeypatch, tmp_path):
    calls = []

    def once(url, dest):
        calls.append(url)
        raise _http_error(404)

    monkeypatch.setattr(ingest, "_download_once", once)
    monkeypatch.setattr(ingest.time, "sleep", lambda s: None)
    with pytest.raises(urllib.error.HTTPError):
        ingest._download("http://x", tmp_path / "f")
    assert len(calls) == 1


def test_download_gives_up_after_the_last_attempt(monkeypatch, tmp_path):
    monkeypatch.setattr(ingest, "_download_once", lambda url, dest: (_ for _ in ()).throw(urllib.error.URLError("down")))
    monkeypatch.setattr(ingest.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError, match="after 3 attempts"):
        ingest._download("http://x", tmp_path / "f", attempts=3)
