"""Re-aligns the volatile figures of README.md (wall-clock timings, throughput, detector runtimes)
with reports/results.json and reports/benchmark.json.

    python scripts/sync_readme.py

Counts, scores and model metrics are deterministic and do not change between runs; wall-clock times do.
This script rewrites only the timing figures, so the README always quotes the latest reference run.
It fails loudly if a pattern it expects is no longer in the README.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    readme = ROOT / "README.md"
    s = readme.read_text(encoding="utf-8")
    res = json.loads((ROOT / "reports" / "results.json").read_text(encoding="utf-8"))
    bench = json.loads((ROOT / "reports" / "benchmark.json").read_text(encoding="utf-8"))
    t, parts = res["totals"], res["partitions"]
    stages = [q["stage_timings"] for q in parts]

    def rng(key: str) -> str:
        v = [x[key] for x in stages if x.get(key) is not None]
        lo, hi = round(min(v)), round(max(v))
        return f"{lo}" if lo == hi else f"{lo}–{hi}"

    def sub(pattern: str, repl, count: int = 1, flags: int = 0) -> None:
        nonlocal s
        s, n = re.subn(pattern, repl, s, flags=flags)
        if n < count:
            raise SystemExit(f"sync_readme: pattern not found in README.md: {pattern[:80]}")

    # results table: duration and rows/s per partition, and the total row
    for q in parts:
        sub(rf"(\| {q['partition_id']} \| [\d,]+ \| [\d,]+ \| [\d.]+ \| [\d,]+ \| [\d.]+ \| [\d.]+ \| \w+ \| )\d+ \| [\d,]+ \|",
            lambda m, q=q: m.group(1) + f"{q['duration_s']:.0f} | {q['rows_per_sec']:,.0f} |")
    sub(r"\| \*\*\d+\*\* \| \*\*[\d,]+\*\* \|", f"| **{t['processing_s']:.0f}** | **{t['rows_per_sec']:,.0f}** |")
    sub(r"End-to-end processing of the 14\.4M rows: \d+ s \([\d,]+ rows/s\)",
        f"End-to-end processing of the 14.4M rows: {t['processing_s']:.0f} s ({t['rows_per_sec']:,.0f} rows/s)")
    sub(r"- Stage times \(s, reference run\): .*?\. Wall-clock",
        f"- Stage times (s, reference run): raw landing {rng('raw_landing')} · rules {rng('rules')} · persisting quality "
        f"results {rng('persist_quality')} · anomaly detection {rng('anomaly')} · profiling {rng('profiling')} · "
        f"drift {rng('drift')}. Wall-clock")
    rc = res["rerun_check"]["partitions"]
    lo, hi = round(min(r["rerun_raw_landing_s"] for r in rc)), round(max(r["rerun_raw_landing_s"] for r in rc))
    sub(r"\(\d+(?:–\d+)? s instead of \d+(?:–\d+)? s\)", f"({lo}–{hi} s instead of {rng('raw_landing')} s)")
    sub(r"\| run duration per partition \| ≤ 900 s \|.*\|",
        "| run duration per partition | ≤ 900 s | " + " | ".join(f"{q['duration_s']:.0f} s ✅" for q in parts) + " |")
    sub(r"\(\d+(?:–\d+)? s/partition, the slowest stage\)", f"({rng('raw_landing')} s/partition, the slowest stage)")
    sub(r"still \d+(?:–\d+)? s per partition — the remaining bottleneck",
        f"still {rng('raw_landing')} s per partition — the remaining bottleneck")

    # benchmark table: runtime column, and the Isolation Forest vs log-IQR ratio
    for name in bench["results"]:
        rt = bench["runtime_s"].get("rules" if name.startswith("rules_critical") and "+" not in name else name, "")
        sub(rf"(\| {re.escape(name)} \| [^|]+ \| [^|]+ \| [\d.]+% \| [\d,]+ \| )[\d.]* \|", lambda m, rt=rt: m.group(1) + f"{rt} |")
    forest, logiqr = bench["runtime_s"]["isolation_forest"], bench["runtime_s"]["iqr_log"]
    sub(r"\d+× slower than log-IQR \([\d.]+ s vs [\d.]+ s on [\d,]+ rows\)",
        f"{forest / logiqr:.0f}× slower than log-IQR ({forest} s vs {logiqr} s on {bench['total_rows']:,} rows)")
    readme.write_text(s, encoding="utf-8")
    print("README.md timing figures aligned with reports/results.json and reports/benchmark.json")
    return 0


if __name__ == "__main__":
    sys.exit(main())
