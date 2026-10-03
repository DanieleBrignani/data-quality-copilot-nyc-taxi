"""Central configuration. Everything is overridable through environment variables."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

import yaml

# DQC_ROOT is needed when the package is installed (not editable), e.g. inside the Docker image
ROOT = Path(os.environ.get("DQC_ROOT", Path(__file__).resolve().parents[2]))
DATA_DIR = Path(os.environ.get("DQC_DATA_DIR", ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
REFERENCE_DIR = DATA_DIR / "reference"
FIXTURES_DIR = DATA_DIR / "fixtures"
REPORTS_DIR = Path(os.environ.get("DQC_REPORTS_DIR", ROOT / "reports"))
CONFIG_DIR = ROOT / "config"
MANIFEST_PATH = RAW_DIR / "manifest.json"



def _load_dotenv(path: Path) -> None:
    """Minimal .env reader (KEY=VALUE lines). Real environment variables always win."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(ROOT / ".env")


def role_dsn(user: str | None = None, password_env: str = "DQC_PG_PASSWORD", database: str | None = None) -> str | None:
    """Connection string built from the environment. No credential has a default: an unset password
    yields None and the caller fails with an explicit message instead of trying a guessable one."""
    password = os.environ.get(password_env)
    if not password:
        return None
    user = user or os.environ.get("DQC_PG_USER", "dqc")
    host, port = os.environ.get("DQC_PG_HOST", "localhost"), os.environ.get("DQC_PG_PORT", "5433")
    database = database or os.environ.get("DQC_PG_DB", "dqc")
    return f"postgresql://{quote(user, safe='')}:{quote(password, safe='')}@{host}:{port}/{database}"


PG_DSN = os.environ.get("DQC_PG_DSN") or role_dsn()
PUSHGATEWAY = os.environ.get("DQC_PUSHGATEWAY", "")  # e.g. localhost:9091; empty = disabled

TLC_BASE_URL = "https://d37ci6vzurychx.cloudfront.net/trip-data"
TLC_ZONES_URL = "https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv"


@lru_cache
def load_yaml(name: str) -> dict:
    with open(CONFIG_DIR / name, encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def rules_config() -> dict:
    return load_yaml("rules.yaml")


def thresholds() -> dict:
    return load_yaml("thresholds.yaml")
