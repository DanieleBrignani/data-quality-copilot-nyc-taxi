"""Deterministic, versioned rule engine (Polars).

Rules live in ``config/rules.yaml``. Each rule compiles to a Polars boolean expression
that is True when a record FAILS the rule. The engine returns:

* a per-rule summary (records_checked / failed_rows / failure_rate)
* a per-record failure matrix used to build quarantine and record-level flags.

The engine is pure: it never mutates or drops input rows.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import polars as pl

from dqc import config


@dataclass(frozen=True)
class Rule:
    rule_id: str
    rule_version: int
    severity: str
    dimension: str
    type: str
    description: str
    spec: dict

    @property
    def columns(self) -> list[str]:
        s = self.spec
        if "columns" in s:
            return list(s["columns"])
        if "column" in s:
            return [s["column"]]
        if self.type == "column_compare":
            return [s["left"], s["right"]]
        if self.type in ("duration_max", "implied_speed"):
            return ["tpep_pickup_datetime", "tpep_dropoff_datetime"] + (
                ["trip_distance"] if self.type == "implied_speed" else [])
        if self.type == "total_reconciliation":
            return ["total_amount"]
        if self.type == "zero_distance_between_zones":
            return ["trip_distance", "PULocationID", "DOLocationID"]
        if self.type == "charged_without_trip":
            return ["trip_distance", "fare_amount"]
        if self.type == "business_key_duplicate":
            return list(s["key"])
        return []


@dataclass(frozen=True)
class RuleSet:
    version: str
    rules: tuple[Rule, ...]
    sha256: str

    def by_id(self, rule_id: str) -> Rule:
        return next(r for r in self.rules if r.rule_id == rule_id)


def load_ruleset(path: Path | None = None) -> RuleSet:
    path = path or config.CONFIG_DIR / "rules.yaml"
    raw = path.read_bytes()
    import yaml

    doc = yaml.safe_load(raw)
    base = {"rule_id", "rule_version", "severity", "dimension", "type", "description"}
    rules = []
    for r in doc["rules"]:
        if r["severity"] not in ("critical", "warning"):
            raise ValueError(f"{r['rule_id']}: invalid severity {r['severity']}")
        rules.append(Rule(r["rule_id"], int(r["rule_version"]), r["severity"], r["dimension"], r["type"],
                          " ".join(str(r["description"]).split()), {k: v for k, v in r.items() if k not in base}))
    ids = [r.rule_id for r in rules]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate rule_id in ruleset")
    return RuleSet(str(doc["ruleset_version"]), tuple(rules), hashlib.sha256(raw).hexdigest())


# --------------------------------------------------------------------------- compilation
_OPS = {"<": "lt", "<=": "le", ">": "gt", ">=": "ge", "==": "eq", "!=": "ne"}
_REVERSAL_COLS = ["fare_amount", "total_amount"]


def _zone_ids() -> list[int]:
    path = config.REFERENCE_DIR / "taxi_zone_lookup.csv"
    if path.exists():
        return pl.read_csv(path)["LocationID"].to_list()
    return list(range(1, 266))  # documented fallback: official lookup has IDs 1..265


def _failed_expr(rule: Rule, ctx: dict) -> pl.Expr:
    s, t = rule.spec, rule.type
    if t == "not_null":
        return pl.any_horizontal([pl.col(c).is_null() for c in s["columns"]])
    if t == "range":
        c = pl.col(s["column"])
        cond = pl.lit(False)
        if "min" in s:
            cond = cond | (c < s["min"])
        if "max" in s:
            cond = cond | (c > s["max"])
        if s.get("allow_null", False):
            return cond.fill_null(False)
        return cond.fill_null(True)
    if t == "accepted_values":
        c = pl.col(s["column"])
        bad = ~c.is_in(s["values"])
        return bad.fill_null(not s.get("allow_null", False))
    if t == "accepted_values_negated":
        return pl.any_horizontal([pl.col(c).is_in(s["values"]).fill_null(False) for c in s["columns"]])
    if t == "zone_lookup":
        ids = ctx["zone_ids"]
        return pl.any_horizontal([~pl.col(c).is_in(ids) for c in s["columns"]]).fill_null(False)
    if t == "column_compare":
        ok = getattr(pl.col(s["left"]), _OPS[s["op"]])(pl.col(s["right"]))
        return (~ok).fill_null(False)  # nulls are the job of DQ001
    if t == "duration_max":
        return ((pl.col("tpep_dropoff_datetime") - pl.col("tpep_pickup_datetime")).dt.total_seconds()
                > s["max_seconds"]).fill_null(False)
    if t == "partition_window":
        start, end = ctx["window"]
        c = pl.col(s["column"])
        return ((c < start) | (c >= end)).fill_null(False)
    if t == "implied_speed":
        hours = (pl.col("tpep_dropoff_datetime") - pl.col("tpep_pickup_datetime")).dt.total_seconds() / 3600
        return (pl.when(hours > 0).then(pl.col("trip_distance") / hours > s["max_mph"])
                .otherwise(False)).fill_null(False)
    if t in ("zero_distance_between_zones", "charged_without_trip"):
        seconds = (pl.col("tpep_dropoff_datetime") - pl.col("tpep_pickup_datetime")).dt.total_seconds()
        zero = pl.col("trip_distance") == 0
        if t == "zero_distance_between_zones":
            cond = zero & (pl.col("PULocationID") != pl.col("DOLocationID")) & (seconds >= s["min_duration_seconds"])
        else:
            cond = zero & (pl.col("fare_amount") > 0) & (seconds < s["max_duration_seconds"]) & (seconds >= 0)
        return cond.fill_null(False)
    if t == "total_reconciliation":
        comps = ["fare_amount", "extra", "mta_tax", "tip_amount", "tolls_amount", "improvement_surcharge",
                 "congestion_surcharge", "Airport_fee", "cbd_congestion_fee"]
        z = {c: pl.col(c).fill_null(0.0) for c in comps}
        residual = pl.col("total_amount") - pl.sum_horizontal(list(z.values()))
        cs, af, cbd = z["congestion_surcharge"], z["Airport_fee"], z["cbd_congestion_fee"]
        tol = s["tolerance"]
        exact_ok = residual.abs() <= tol
        # Vendors that embed surcharges inside `extra` (VendorID=1, measured on real data)
        combos = [cs, af, cbd, cs + af, cs + cbd, af + cbd, cs + af + cbd]
        embedded_ok = pl.any_horizontal([(residual + k).abs() <= tol for k in combos]) & pl.col(
            "VendorID").is_in(s.get("embedded_surcharge_vendors", []))
        skip = pl.col("payment_type").is_in(s.get("skip_payment_types", []))
        return (~(exact_ok | embedded_ok) & ~skip).fill_null(False)
    if t == "exact_duplicate":
        cols = [c for c in ctx["data_columns"]]
        return pl.struct(cols).is_duplicated() & ~pl.struct(cols).is_first_distinct()
    if t == "business_key_duplicate":
        key = s["key"]
        dup = pl.struct(key).is_duplicated()
        if s.get("exclude_reversal_pairs", True):
            has_neg = pl.any_horizontal([pl.col(c) < 0 for c in _REVERSAL_COLS]).fill_null(False)
            dup = dup & ~has_neg.any().over(key)
        exact = pl.struct(ctx["data_columns"]).is_duplicated()
        return (dup & ~exact).fill_null(False)
    raise ValueError(f"unknown rule type {t}")


def not_applicable_expr(rule: Rule) -> pl.Expr | None:
    """Rows outside a rule's scope are not counted in records_checked."""
    if rule.type == "total_reconciliation" and rule.spec.get("skip_payment_types"):
        return pl.col("payment_type").is_in(rule.spec["skip_payment_types"]).fill_null(False)
    return None


def month_window(year_month: str) -> tuple[datetime, datetime]:
    y, m = map(int, year_month.split("-"))
    start = datetime(y, m, 1)
    end = datetime(y + (m == 12), m % 12 + 1, 1)
    return start, end


# --------------------------------------------------------------------------- evaluation
@dataclass
class RuleEvaluation:
    summary: pl.DataFrame  # one row per rule
    failures: pl.DataFrame  # record_id + one bool column per rule (True = failed)


def evaluate(df: pl.DataFrame, ruleset: RuleSet, year_month: str) -> RuleEvaluation:
    data_columns = [c for c in df.columns if c not in ("record_id", "source_row", "partition_id")]
    ctx = {"window": month_window(year_month), "zone_ids": _zone_ids(), "data_columns": data_columns}
    exprs = [_failed_expr(r, ctx).alias(r.rule_id) for r in ruleset.rules]
    failures = df.select(pl.col("record_id"), *exprs)

    na_exprs = [(not_applicable_expr(r) if not_applicable_expr(r) is not None else pl.lit(False))
                .sum().alias(r.rule_id) for r in ruleset.rules]
    not_applicable = df.select(na_exprs).row(0, named=True)
    failed_counts = failures.select(pl.col(r.rule_id).sum() for r in ruleset.rules).row(0, named=True)

    n = df.height
    rows = []
    for r in ruleset.rules:
        checked = n - int(not_applicable[r.rule_id])
        failed = int(failed_counts[r.rule_id])
        rows.append({
            "rule_id": r.rule_id, "rule_version": r.rule_version, "severity": r.severity,
            "dimension": r.dimension, "description": r.description, "columns": ",".join(r.columns),
            "records_checked": checked, "failed_rows": failed,
            "failure_rate": (failed / checked) if checked else 0.0,
        })
    return RuleEvaluation(pl.DataFrame(rows), failures)


def record_flags(ev: RuleEvaluation, ruleset: RuleSet) -> pl.DataFrame:
    """Per-record lists of failed critical / warning rules (only records with any failure)."""
    crit = [r.rule_id for r in ruleset.rules if r.severity == "critical"]
    warn = [r.rule_id for r in ruleset.rules if r.severity == "warning"]

    def _list(ids: list[str]) -> pl.Expr:
        if not ids:
            return pl.lit([], dtype=pl.List(pl.String))
        return pl.concat_list([pl.when(pl.col(i)).then(pl.lit(i)).otherwise(None) for i in ids]).list.drop_nulls()

    rule_cols = crit + warn
    return (ev.failures
            .filter(pl.any_horizontal(rule_cols))
            .select("record_id", _list(crit).alias("failed_critical"), _list(warn).alias("failed_warning"))
            .with_columns(is_valid=pl.col("failed_critical").list.len() == 0))


def quarantine_rows(df: pl.DataFrame, flags: pl.DataFrame, ruleset: RuleSet) -> pl.DataFrame:
    """One quarantine row per (record, failed critical rule), carrying the original values."""
    bad = flags.filter(~pl.col("is_valid")).select("record_id", "failed_critical").explode("failed_critical", empty_as_null=True)
    bad = bad.rename({"failed_critical": "failed_rule"})
    if bad.is_empty():
        return pl.DataFrame(schema={"record_id": pl.String, "failed_rule": pl.String, "rule_version": pl.Int64,
                                    "severity": pl.String, "original_value": pl.String, "reason": pl.String,
                                    "original_record": pl.String})
    data_cols = [c for c in df.columns if c not in ("record_id", "source_row", "partition_id")]
    originals = df.join(bad.select("record_id").unique(), on="record_id", how="semi")
    parts = []
    for r in ruleset.rules:
        if r.severity != "critical":
            continue
        sub = bad.filter(pl.col("failed_rule") == r.rule_id)
        if sub.is_empty():
            continue
        cols = [c for c in r.columns if c in data_cols]
        txt = (pl.concat_str([pl.format(f"{c}={{}}", pl.col(c).cast(pl.String).fill_null("NULL")) for c in cols],
                             separator="; ") if cols else pl.lit("(whole record)"))
        parts.append(sub.join(originals, on="record_id", how="left").select(
            "record_id", "failed_rule",
            pl.lit(r.rule_version, pl.Int64).alias("rule_version"),
            pl.lit(r.severity).alias("severity"),
            txt.alias("original_value"),
            pl.lit(r.description).alias("reason"),
            pl.struct(data_cols).struct.json_encode().alias("original_record"),
        ))
    return pl.concat(parts)


def ruleset_as_records(ruleset: RuleSet) -> list[dict]:
    return [{"rule_id": r.rule_id, "rule_version": r.rule_version, "severity": r.severity,
             "dimension": r.dimension, "rule_type": r.type, "description": r.description,
             "definition": json.dumps(r.spec, default=str), "ruleset_version": ruleset.version}
            for r in ruleset.rules]
