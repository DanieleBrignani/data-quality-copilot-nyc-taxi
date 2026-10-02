"""Schema contract validation and normalisation.

Classifies every difference between an incoming file and the contract:
  * missing required column  -> critical  (partition rejected)
  * incompatible type        -> critical  (partition rejected)
  * known optional column    -> info      (documented additive change, e.g. cbd_congestion_fee)
  * unexpected new column    -> warning   (loaded to audit, not propagated)
  * renamed via known alias  -> info
"""

from __future__ import annotations

from dataclasses import dataclass, field

import polars as pl

from dqc import config

_KIND = {
    "int": (pl.Int8, pl.Int16, pl.Int32, pl.Int64, pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64),
    "float": (pl.Float32, pl.Float64, pl.Int8, pl.Int16, pl.Int32, pl.Int64),  # ints are safely castable
    "datetime": (pl.Datetime,),
    "str": (pl.String, pl.Categorical),
}
_CAST = {"int": pl.Int64, "float": pl.Float64, "datetime": pl.Datetime("us"), "str": pl.String}


@dataclass
class SchemaEvent:
    check: str
    column: str | None
    severity: str  # critical | warning | info
    detail: str


@dataclass
class SchemaResult:
    events: list[SchemaEvent] = field(default_factory=list)

    @property
    def is_breaking(self) -> bool:
        return any(e.severity == "critical" for e in self.events)

    @property
    def unexpected_changes(self) -> int:
        return sum(e.severity in ("critical", "warning") for e in self.events)


def _matches(dtype: pl.DataType, kind: str) -> bool:
    return any(dtype == t or (isinstance(t, type) and isinstance(dtype, t)) for t in _KIND[kind]) or (
        kind == "datetime" and isinstance(dtype, pl.Datetime)
    )


def validate_and_normalise(df: pl.DataFrame, contract: dict | None = None) -> tuple[pl.DataFrame | None, SchemaResult]:
    """Return (normalised frame or None if breaking, SchemaResult)."""
    contract = contract or config.thresholds()["schema"]
    required: dict = contract["required_columns"]
    optional: dict = contract.get("optional_columns", {})
    aliases: dict = contract.get("aliases", {})
    res = SchemaResult()

    renames = {c: aliases[c] for c in df.columns if c in aliases and aliases[c] not in df.columns}
    for src, dst in renames.items():
        res.events.append(SchemaEvent("column_alias", src, "info", f"renamed {src} -> {dst}"))
    df = df.rename(renames)

    for col, kind in required.items():
        if col not in df.columns:
            res.events.append(SchemaEvent("missing_required_column", col, "critical", f"expected {kind}"))
        elif not _matches(df.schema[col], kind):
            res.events.append(SchemaEvent("type_mismatch", col, "critical",
                                          f"expected {kind}, got {df.schema[col]}"))
    for col, kind in optional.items():
        if col in df.columns:
            if not _matches(df.schema[col], kind):
                res.events.append(SchemaEvent("type_mismatch", col, "critical",
                                              f"expected {kind}, got {df.schema[col]}"))
            else:
                res.events.append(SchemaEvent("optional_column_present", col, "info",
                                              "documented additive column"))
    for col in df.columns:
        if col not in required and col not in optional:
            res.events.append(SchemaEvent("unexpected_column", col, "warning",
                                          f"not in contract ({df.schema[col]}); dropped from curated flow"))

    if res.is_breaking:
        return None, res

    exprs = [pl.col(c).cast(_CAST[k]) for c, k in required.items()]
    exprs += [(pl.col(c).cast(_CAST[k]) if c in df.columns else pl.lit(None, _CAST[k]).alias(c))
              for c, k in optional.items()]
    return df.select(exprs), res


def diff_vs_previous(current: dict, previous: dict) -> list[SchemaEvent]:
    """Column-level differences between two partitions' SOURCE schemas (before normalisation)."""
    ev = []
    for c in sorted(set(current) - set(previous)):
        ev.append(SchemaEvent("column_added_vs_previous", c, "info", f"new column ({current[c]})"))
    for c in sorted(set(previous) - set(current)):
        ev.append(SchemaEvent("column_removed_vs_previous", c, "info", f"was {previous[c]}"))
    for c in sorted(set(current) & set(previous)):
        if current[c] != previous[c]:
            ev.append(SchemaEvent("type_changed_vs_previous", c, "info", f"{previous[c]} -> {current[c]}"))
    return ev
