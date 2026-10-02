"""Central configuration. Everything is overridable through environment variables."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = Path(os.environ.get("DQC_DATA_DIR", ROOT / "data"))
RAW_DIR = DATA_DIR / "raw"
REFERENCE_DIR = DATA_DIR / "reference"
FIXTURES_DIR = DATA_DIR / "fixtures"
REPORTS_DIR = Path(os.environ.get("DQC_REPORTS_DIR", ROOT / "reports"))
CONFIG_DIR = ROOT / "config"
MANIFEST_PATH = RAW_DIR / "manifest.json"

PG_DSN = os.environ.get("DQC_PG_DSN", "postgresql://dqc:dqc@localhost:5433/dqc")
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
