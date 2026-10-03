"""Checks that every number in README.md is backed by a file produced by a repository command.

    python scripts/verify_readme_numbers.py        # exit 1 if any number has no source

Sources (and the command that regenerates each):
    reports/results.json, benchmark.json, failure_demo.json, *_review.json   scripts/reproduce.sh
    reports/evidence.json                                                    python -m dqc evidence
    reports/recovery_check.json                                              scripts/restore_check.sh
    reports/test_counts.json                                                 this script (runs pytest --collect-only)
    data/raw/manifest.json                                                   python -m dqc ingest
    models/*.json                                                            python -m dqc ml train
    config/*.yaml, ci/quality_baseline.json                                  versioned configuration

A number is "verified" when one of the usual renderings of a source value equals it (rounded, as a
percentage, with thousands separators, in MB/GB). Numbers that are definitions rather than
measurements (a threshold stated in prose, a domain fact, a port) must be listed in STATED with a reason.

Limit of this check: the matcher is permissive. A short number (one or two digits) will almost always
find some source value that renders the same way, so the check is strong for distinctive figures
(counts, percentages with decimals) and weak for small integers. It catches numbers that no command
produces; it does not prove that each number sits next to the right claim.
Writes reports/readme_numbers_audit.md.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]

# Definitions, domain facts and identifiers — not measurements. Each needs a reason.
STATED = {
    "30": "section title 'In 30 seconds' / minimum pair support",
    "2": "generic small count in prose (two models, 2 points tolerance from config)",
    "3": "generic small count in prose",
    "4": "four monthly partitions (manifest)",
    "5": "5-fold cross-fitting / 5 Jan 2025 / five budgets",
    "6": "six failure fixtures; TLC passenger limit",
    "7": "seed 7 (src/dqc/ml/review.py) / TLC child age rule",
    "10": "10 search configurations (SEARCH_CONFIGS) / fare x10 corruption",
    "1": "generic small count in prose",
    "0": "generic zero in prose",
    "100": "100 trees (config) / 100% wording",
    "24": "24 h duration rule (config/rules.yaml: 86400 s)",
    "90": "90 mph rule (config/rules.yaml)",
    "70": "TLC JFK flat fare, a published tariff",
    "2016": "year TLC removed coordinates from trip files",
    "265": "zones in the official TLC lookup",
    "264": "TLC zone id 'Unknown'",
    "263": "TLC zone ids",
    "8000": "port", "8502": "port", "9091": "port", "3001": "port", "8501": "port", "5433": "port", "9090": "port",
    "3000": "port",
    "200": "200 mi rule / 200k training sample (config)",
    "500": "top-500 persisted records (config top_n_persist)",
    "14.4": "14,367,509 rows rounded to millions",
    "3.5": "≈3.5M rows per month (manifest row counts)",
    "60": "≈60 MB per monthly file (manifest size_bytes)",
    "13": "13 error types in the benchmark (benchmark.json error_types)",
    "14": "14 candidates per model (models/*.json selection)",
    "40": "40 reviewed records per method (review json sample_size)",
    "38": "38 of 40 genuine issues = likely_data_error + flex_fare_semantics (review json)",
    "29": "29 of 40 plausible legitimate (anomaly_review.json)",
    "11": "seed 11 (src/dqc/anomaly_review.py)",
    "42": "seed 42",
    "59": "random forest artifact / selected artifact size ratio (models/fare_model_v2.json)",
    "60×": "same ratio, rounded",
    "1.25": "retraining threshold RETRAIN_MAE_RATIO (src/dqc/ml/residual.py)",
    "0.5": "review budget ALPHA = 0.005 (src/dqc/ml/residual.py)",
    "99.5": "1 - ALPHA quantile",
    "1%": "selection tolerance SELECTION_TOLERANCE (src/dqc/ml/residual.py)",
    "300": "300 bootstrap resamples (src/dqc/benchmark.py) / 300k backtest sample",
    "50,000": "CI sample size SAMPLE_ROWS (src/dqc/gate.py)",
    "2,000": "failure-demo base size N_BASE (src/dqc/failure_demo.py)",
    "25,000": "injected fare in the invalid_amount fixture (src/dqc/failure_demo.py)",
    "1,000": "fare cap (config/rules.yaml)",
    "1,500": "total cap (config/rules.yaml)",
    "4,363": "labelled errors in the benchmark (benchmark.json injected_error_rows)",
}


def flatten(obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from flatten(v, f"{prefix}.{k}" if prefix else str(k))
    elif isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            yield from flatten(v, f"{prefix}[{i}]")
    elif isinstance(obj, bool) or obj is None:
        return
    elif isinstance(obj, (int, float)):
        yield prefix, float(obj)
    elif isinstance(obj, str):
        for m in re.finditer(r"-?\d{1,3}(?:,\d{3})+(?:\.\d+)?|-?\d+(?:\.\d+)?", obj):
            yield prefix, float(m.group().replace(",", ""))


def renderings(v: float) -> set[str]:
    out = set()
    for x in (v, abs(v), v * 100, abs(v) * 100, v / 1e6, v / 1e9, v / 1e3):
        for d in range(0, 5):
            r = round(x, d)
            s = f"{r:.{d}f}"
            out.add(s)
            out.add(f"{r:,.{d}f}")
            if d and s.rstrip("0").rstrip(".") != s:
                out.add(s.rstrip("0").rstrip("."))
    return out


def test_counts() -> dict:
    def collect(*args):
        r = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", *args],
                           cwd=ROOT, capture_output=True, text=True)
        m = re.search(r"(\d+)(?:/\d+)? tests? collected", r.stdout + r.stderr)
        return int(m.group(1)) if m else None
    total, db = collect(), collect("-m", "db")
    out = {"pytest_total": total, "pytest_db": db, "pytest_unit": total - db if total and db is not None else None}
    for name, pattern in (("dbt_build.log", r"PASS=(\d+)"), ("soda_scan.log", r"(\d+)/(\d+) checks PASSED"),
                          ("soda_slo.log", r"(\d+)/(\d+) checks PASSED")):
        p = ROOT / "reports" / name
        if p.exists():
            m = re.search(pattern, p.read_text(encoding="utf-8", errors="ignore"))
            if m:
                out[name] = [int(g) for g in m.groups()]
    (ROOT / "reports" / "test_counts.json").write_text(json.dumps(out, indent=2), encoding="utf-8")
    return out


def build_pool() -> dict[str, str]:
    sources: dict[str, object] = {"reports/test_counts.json": test_counts()}
    for rel in ("reports/results.json", "reports/benchmark.json", "reports/evidence.json", "reports/failure_demo.json",
                "reports/recovery_check.json", "reports/anomaly_review.json", "reports/fare_model_review.json",
                "reports/distance_model_review.json", "reports/copilot_suggestions.json", "data/raw/manifest.json",
                "ci/quality_baseline.json"):
        if (ROOT / rel).exists():
            sources[rel] = json.loads((ROOT / rel).read_text(encoding="utf-8"))
    for p in sorted((ROOT / "reports").glob("*_review_sample.csv")):
        sources[f"reports/{p.name}"] = p.read_text(encoding="utf-8")
    res = sources.get("reports/results.json")
    if res:   # ratios the report prints but does not store
        sources["reports/results.json (derived)"] = {
            q["partition_id"]: {"quarantined_pct": 100 * q["quarantined_records"] / q["rows_total"]}
            for q in res["partitions"]}
    for p in sorted((ROOT / "models").glob("*.json")):
        sources[f"models/{p.name}"] = json.loads(p.read_text(encoding="utf-8"))
    for p in sorted((ROOT / "config").glob("*.yaml")):
        sources[f"config/{p.name}"] = yaml.safe_load(p.read_text(encoding="utf-8"))
    pool: dict[str, str] = {}
    for rel, obj in sources.items():
        for key, value in flatten(obj):
            for r in renderings(value):
                pool.setdefault(r, f"{rel} :: {key}")
    return pool


def readme_numbers(text: str) -> list[tuple[int, str]]:
    out = []
    in_code = False
    for i, line in enumerate(text.split("\n"), 1):
        if line.strip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        line = re.sub(r"`[^`]*`", " ", line)                       # inline code: identifiers, commands
        line = re.sub(r"\]\([^)]*\)|https?://\S+|<[^>]+>", " ", line)  # links, urls, html
        line = re.sub(r"yellow_\d{4}-\d{2}|#\d+|\{[^}]*\}", " ", line)                 # partition ids, labels, value sets
        line = re.sub(r"\b\d{1,2}:\d{2}(?::\d{2})?\b", " ", line)                      # clock times
        line = re.sub(r"\bDQ\d+\w*|\b[vV]\d+(?:\.\d+)*\b|\b\d+\.\d+\.\d+\b", " ", line)   # rule ids, versions
        line = re.sub(r"\b20\d\d(?:-\d\d)?(?:-\d\d)?\b|\b\d{1,2} (?:Jan|Feb|Mar|Apr|Nov|Dec)\w* 20\d\d", " ", line)  # dates
        line = re.sub(r"\bp\d+(?:\.\d+)?\b|R²|\bQ[13]\b|\b[A-Z]\d\b", " ", line)             # p99.99, quartiles
        for m in re.finditer(r"(?<![\w.,])[-−]?\$?(\d[\d,]*(?:\.\d+)?)(%|×|k\b|M\b)?", line):
            out.append((i, m.group(1) + (m.group(2) or "")))
    return out


def main() -> int:
    pool = build_pool()
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    rows, unverified = [], []
    for line, token in readme_numbers(text):
        bare = token.rstrip("%×kM")
        norm = bare.replace(",", "")
        candidates = {bare, norm}
        if "." in norm:
            candidates.add(norm.rstrip("0").rstrip("."))
        if token.endswith("k"):
            candidates |= {str(int(float(norm) * 1000)), f"{int(float(norm) * 1000):,}"}
        src = next((pool[c] for c in candidates if c in pool), None)
        if src is None:
            src = next((f"STATED: {STATED[k]}" for k in (token, bare, norm) if k in STATED), None)
        rows.append((line, token, src))
        if src is None:
            unverified.append((line, token))
    out = ["# README numbers audit", "", f"{len(rows)} numeric tokens checked, {len(unverified)} without a source.", "",
           "| line | number | source |", "|---:|---|---|"]
    out += [f"| {ln} | {tok} | {src or '**UNVERIFIED**'} |" for ln, tok, src in rows]
    (ROOT / "reports" / "readme_numbers_audit.md").write_text("\n".join(out) + "\n", encoding="utf-8")
    print(f"{len(rows)} numbers checked, {len(unverified)} unverified")
    for ln, tok in unverified:
        print(f"  README.md:{ln}: {tok}")
    return 1 if unverified else 0


if __name__ == "__main__":
    sys.exit(main())
