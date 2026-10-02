"""Quality Copilot — explains incidents AFTER deterministic detection. Never the source of truth.

Guarantees (enforced by construction, not by prompt):
* Input = facts read from dq.* tables (rule results, quarantined samples, drift metrics). The model
  never sees or decides which records are valid.
* Output = a row in dq.copilot_suggestions, written through the `dqc_copilot` Postgres role, which
  has INSERT on that single table and no access to raw/analytics. It cannot modify data.
* Every suggestion stores the exact evidence (+ sha256), prompt version, provider and model, and is
  labelled "SUGGESTION — not verified"; status starts at `proposed` and only a human changes it.
* No API key is required: the default provider is a built-in deterministic analyzer that computes its
  explanation from the same evidence (segment concentration, trend, what drives the change). The LLM is optional.
"""

from __future__ import annotations

import hashlib
import json
import os
from functools import lru_cache

import psycopg

from dqc import config, db

PROMPT_VERSION = "copilot-v2"
MODEL = "claude-opus-5-5"
COPILOT_DSN = os.environ.get("DQC_COPILOT_DSN", config.PG_DSN.replace("dqc:dqc@", "dqc_copilot:copilot@"))

RESPONSE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["summary", "likely_causes", "investigation_steps", "remediation_suggestion",
                 "candidate_rule", "confidence"],
    "properties": {
        "summary": {"type": "string"},
        "likely_causes": {"type": "array", "items": {"type": "string"}},
        "investigation_steps": {"type": "array", "items": {"type": "string"}},
        "remediation_suggestion": {"type": "string"},
        "candidate_rule": {
            "type": "object",
            "additionalProperties": False,
            "required": ["rule_id", "severity", "description", "yaml"],
            "properties": {"rule_id": {"type": "string"}, "severity": {"type": "string"},
                           "description": {"type": "string"}, "yaml": {"type": "string"}},
        },
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
    },
}

SYSTEM = """You are a data-quality analyst assistant for a NYC TLC taxi-trip pipeline.
You receive EVIDENCE produced by deterministic rules and statistics. Your job is to explain, not to judge:
- Use only the evidence. If it is insufficient, say so and lower confidence.
- Explain likely causes as hypotheses, propose concrete investigation steps (queries, checks on the
  TLC data dictionary), a possible remediation, and optionally one candidate rule in the same YAML
  shape as the existing ruleset.
- Never state that records are correct or incorrect beyond what the rules measured, and never propose
  to modify, delete or publish records automatically. Remediations are proposals for a human reviewer."""


# --------------------------------------------------------------------------- evidence
def incidents(limit: int = 5) -> list[dict]:
    """Most relevant incidents of the latest run per partition, from the warehouse."""
    rules_df = db.query_df("""
        WITH latest AS (
            SELECT DISTINCT ON (pq.partition_id) pq.partition_id, pq.run_id
            FROM dq.partition_quality pq JOIN dq.pipeline_runs r USING (run_id)
            JOIN dq.dataset_partitions p USING (partition_id) WHERE p.service = 'yellow'
            ORDER BY pq.partition_id, r.started_at DESC)
        SELECT rr.partition_id, rr.run_id::text, rr.rule_id, rr.rule_version, rr.severity, rr.dimension,
               rr.records_checked, rr.failed_rows, rr.failure_rate, d.description,
               lag(rr.failure_rate) OVER (PARTITION BY rr.rule_id ORDER BY rr.partition_id) AS prev_failure_rate
        FROM dq.rule_results rr JOIN latest l USING (partition_id, run_id)
        JOIN dq.rule_definitions d ON d.rule_id = rr.rule_id AND d.rule_version = rr.rule_version
        ORDER BY rr.partition_id, rr.rule_id""")
    out = []
    for r in rules_df.iter_rows(named=True):
        if not r["failed_rows"]:
            continue
        prev = r["prev_failure_rate"]
        jump = (r["failure_rate"] / prev) if prev else None
        out.append({"incident_type": "rule_failure", "priority": r["failed_rows"] * (3 if r["severity"] == "critical" else 1)
                    * (jump if jump and jump > 1.5 else 1), **r, "failure_rate_change_x": jump})
    drift_df = db.query_df("""
        SELECT DISTINCT ON (d.partition_id, d.column_name, d.metric) d.partition_id, d.run_id::text,
               d.reference_partition_id, d.column_name, d.metric, d.value, d.threshold, d.status
        FROM dq.drift_results d JOIN dq.pipeline_runs r USING (run_id)
        WHERE d.status = 'alert' ORDER BY d.partition_id, d.column_name, d.metric, r.started_at DESC""")
    for r in drift_df.iter_rows(named=True):
        # drift priority = how far above its threshold, on a scale comparable to ~10k failing records
        ratio = abs(r["value"] or 0) / r["threshold"] if r["threshold"] else 1.0
        out.append({"incident_type": "drift", "priority": 10_000 * ratio, **r})
    out.sort(key=lambda x: -x["priority"])
    return out[:limit]


@lru_cache(maxsize=16)
def _base_segments(partition_id: str) -> dict:
    """Rows per (VendorID, payment_type) in a partition: the denominator for segment failure rates."""
    df = db.query_df("""SELECT vendor_id, payment_type, count(*) AS n FROM raw.yellow_trips
                        WHERE partition_id = %s GROUP BY 1, 2""", (partition_id,))
    return {(r["vendor_id"], r["payment_type"]): r["n"] for r in df.iter_rows(named=True)}


def _failing_segments(partition_id: str, rule_id: str) -> list[dict]:
    """Failing records of a rule (critical or warning) by (VendorID, payment_type), with segment rates."""
    df = db.query_df("""
        SELECT t.vendor_id, t.payment_type, count(*) AS failed,
               count(*) FILTER (WHERE t.total_amount >= 0) AS failed_with_non_negative_total
        FROM dq.record_quality q JOIN raw.yellow_trips t USING (partition_id, record_id)
        WHERE q.partition_id = %s AND %s = ANY(q.failed_critical || q.failed_warning)
        GROUP BY 1, 2 ORDER BY failed DESC""", (partition_id, rule_id))
    base = _base_segments(partition_id)
    total = df["failed"].sum() if df.height else 0
    out = []
    for r in df.iter_rows(named=True):
        n = base.get((r["vendor_id"], r["payment_type"]), 0)
        out.append({**r, "segment_rows": n, "segment_failure_rate": round(r["failed"] / n, 6) if n else None,
                    "share_of_failures": round(r["failed"] / total, 6) if total else 0.0})
    return out


def evidence_for(inc: dict) -> dict:
    """Facts only, all read from the warehouse. Both providers receive exactly this."""
    ev = {k: v for k, v in inc.items() if k != "priority"}
    pid = inc["partition_id"]
    if inc["incident_type"] == "rule_failure":
        rid = inc["rule_id"]
        ev["quarantined_sample"] = db.query_df("""
            SELECT record_id, original_value, original_record FROM dq.quarantine
            WHERE partition_id = %s AND failed_rule = %s AND resolved_by_run_id IS NULL
            ORDER BY record_id LIMIT 8""", (pid, rid)).to_dicts()
        ev["history"] = db.query_df("""
            SELECT DISTINCT ON (rr.partition_id) rr.partition_id, rr.failed_rows, rr.failure_rate
            FROM dq.rule_results rr JOIN dq.pipeline_runs r USING (run_id)
            JOIN dq.dataset_partitions p USING (partition_id)
            WHERE rr.rule_id = %s AND p.service = 'yellow' AND rr.partition_id <= %s
            ORDER BY rr.partition_id, r.started_at DESC""", (rid, pid)).to_dicts()
        ev["segments"] = _failing_segments(pid, rid)[:8]
        prev = [h["partition_id"] for h in ev["history"] if h["partition_id"] < pid]
        if prev:
            ev["previous_partition"] = prev[-1]
            ev["segments_previous"] = _failing_segments(prev[-1], rid)[:8]
    else:
        ref = inc["reference_partition_id"]
        shares = {}
        for part in (ref, pid):
            base = _base_segments(part)
            tot = sum(base.values()) or 1
            by_pt: dict = {}
            for (_, pt), n in base.items():
                by_pt[pt] = by_pt.get(pt, 0) + n
            shares[part] = {str(k): round(100 * v / tot, 4) for k, v in sorted(by_pt.items(), key=lambda kv: str(kv[0]))}
        ev["payment_type_share_pct"] = shares
        ev["schema_events_same_partition"] = db.query_df("""
            SELECT DISTINCT check_name, column_name, detail FROM dq.schema_checks
            WHERE partition_id = %s AND check_name LIKE '%%_vs_previous'""", (pid,)).to_dicts()
        ev["other_drift_alerts_same_partition"] = db.query_df("""
            SELECT DISTINCT column_name, metric, round(value::numeric, 4)::float AS value FROM dq.drift_results
            WHERE partition_id = %s AND run_id = %s AND status = 'alert'
              AND NOT (column_name = %s AND metric = %s) ORDER BY 1, 2""",
            (pid, inc["run_id"], inc["column_name"], inc["metric"])).to_dicts()
    return json.loads(json.dumps(ev, default=str))


# --------------------------------------------------------------------------- providers
_NO_RULE = {"rule_id": "", "severity": "", "description": "", "yaml": ""}
_PAYMENT = {0: "Flex Fare", 1: "credit card", 2: "cash", 3: "no charge", 4: "dispute", 5: "unknown", 6: "voided"}


def _seg_name(s: dict) -> str:
    return f"VendorID={s['vendor_id']} / payment_type={s['payment_type']} ({_PAYMENT.get(s['payment_type'], '?')})"


def analyze_rule(ev: dict) -> dict:
    """Deterministic incident analysis: concentration, systematic segments, what drives the change."""
    critical = ev["severity"] == "critical"
    segs, prev = ev.get("segments") or [], ev.get("segments_previous") or []
    hist = ev.get("history") or []
    causes, steps, candidate, confidence = [], [], dict(_NO_RULE), "low"
    summary = (f"{ev['rule_id']} (v{ev['rule_version']}, {ev['severity']}) failed {ev['failed_rows']:,} of "
               f"{ev['records_checked']:,} records ({100 * ev['failure_rate']:.3f}%) in {ev['partition_id']}.")
    if len(hist) > 1:
        summary += " Trend: " + " -> ".join(f"{100 * h['failure_rate']:.3f}%" for h in hist) + "."

    top = segs[0] if segs else None
    if top:
        rate = top["segment_failure_rate"] or 0.0
        overall = ev["failure_rate"] or 1e-12
        causes.append(f"{100 * top['share_of_failures']:.1f}% of the failures come from {_seg_name(top)}: "
                      f"{top['failed']:,} of its {top['segment_rows']:,} records fail "
                      f"({100 * rate:.1f}%, {rate / overall:.1f}x the partition-wide rate).")
        if rate >= 0.995:
            causes.append("Every record of that segment fails: this is how the segment is reported upstream "
                          "(systematic), not random corruption.")
        nn = top.get("failed_with_non_negative_total") or 0
        if ev["rule_id"].startswith("DQ021") and top["failed"] and nn / top["failed"] >= 0.5:
            causes.append(f"{100 * nn / top['failed']:.1f}% of that segment's failing records still have a "
                          "non-negative total_amount: fare_amount looks like an adjustment component there, "
                          "not a reversed trip (hypothesis for the source owner).")
        elif ev["rule_id"].startswith(("DQ021", "DQ022", "DQ023")) and top["payment_type"] in (2, 3, 4, 6):
            causes.append("Negative amounts on dispute / no-charge / cash records are consistent with reversal "
                          "entries that mirror an earlier positive charge.")

    if prev and segs:
        before = {(p["vendor_id"], p["payment_type"]): p["failed"] for p in prev}
        deltas = sorted(((s["failed"] - before.get((s["vendor_id"], s["payment_type"]), 0), i) for i, s in enumerate(segs)),
                        reverse=True)
        total_delta = sum(s["failed"] for s in segs) - sum(p["failed"] for p in prev)
        d, i = deltas[0]
        if total_delta > 0 and d > 0:
            part = (f"{100 * d / total_delta:.0f}% of the increase" if d <= total_delta else
                    "more than the whole net increase, because other segments fell")
            causes.append(f"Versus {ev['previous_partition']} failures rose by {total_delta:,}; {_seg_name(segs[i])} "
                          f"alone accounts for {d:+,} ({part}).")
            if d / total_delta >= 0.8:
                confidence = "medium"

    if top and top["share_of_failures"] >= 0.5 and (top["segment_failure_rate"] or 0) >= 0.3:
        confidence = "medium"
        short, rest = ev["rule_id"].split("_", 1)
        pt = top["payment_type"]
        new_id = f"{short}b_{rest}_payment_type_{pt}"
        candidate = {
            "rule_id": new_id, "severity": "warning",
            "description": (f"Track the {_seg_name(top)} pattern separately instead of mixing it with the rest of "
                            f"{ev['rule_id']}; decide its severity once the source owner confirms the semantics."),
            "yaml": (f"- rule_id: {new_id}\n  rule_version: 1\n  severity: warning\n  dimension: {ev['dimension']}\n"
                     f"  type: same_as:{ev['rule_id']}\n  only_payment_types: [{pt}]\n"
                     f"  description: >\n    Same check as {ev['rule_id']}, restricted to payment_type={pt} "
                     f"({_PAYMENT.get(pt, '?')}).\n"
                     f"# and on {ev['rule_id']}: add  skip_payment_types: [{pt}]  and bump rule_version\n"
                     "# NOTE: `only_payment_types` / `same_as` are not implemented in the engine yet. This is a\n"
                     "# proposal to be reviewed, implemented, tested and passed through the CI gate."),
        }

    steps.append((f"SELECT original_record FROM dq.quarantine WHERE failed_rule='{ev['rule_id']}' "
                  f"AND partition_id='{ev['partition_id']}' LIMIT 100") if critical else
                 (f"SELECT t.* FROM analytics.fct_clean_trips t WHERE '{ev['rule_id']}' = ANY(t.failed_warning_rules) "
                  f"AND t.partition_id='{ev['partition_id']}' LIMIT 100"))
    if top:
        steps.append(f"Ask the owner of {_seg_name(top)} data whether the pattern is intended; check the TLC data "
                     "dictionary revision for that month.")
        steps.append("Plot the daily failure count of that segment to find the exact start date of the change.")
    return {
        "summary": summary,
        "likely_causes": causes or ["No segment concentrates the failures; evidence is insufficient for a cause."],
        "investigation_steps": steps,
        "remediation_suggestion": ("Keep the records quarantined until the source owner confirms; do not relax the rule "
                                   "to meet the SLO." if critical else
                                   "Records stay in the curated layer with a warning flag; confirm whether the "
                                   "pattern is expected before changing severity."),
        "candidate_rule": candidate,
        "confidence": confidence,
    }


def analyze_drift(ev: dict) -> dict:
    pid, ref = ev["partition_id"], ev["reference_partition_id"]
    causes, confidence = [], "low"
    shares = ev.get("payment_type_share_pct") or {}
    cur, old = shares.get(pid, {}), shares.get(ref, {})
    moves = sorted(((cur.get(k, 0.0) - old.get(k, 0.0), k) for k in set(cur) | set(old)), key=lambda m: -abs(m[0]))
    if moves and abs(moves[0][0]) >= 1.0:
        d, k = moves[0]
        label = _PAYMENT.get(int(k), "?") if k.lstrip("-").isdigit() else "?"
        causes.append(f"payment_type={k} ({label}) share moved {d:+.2f} pp "
                      f"({old.get(k, 0.0):.2f}% -> {cur.get(k, 0.0):.2f}%).")
        if ev["metric"] == "null_rate_change_pp" and abs(d - ev["value"]) < 0.5:
            causes.append(f"That matches the null-rate change of {ev['column_name']} ({ev['value']:+.2f} pp) almost "
                          "exactly: the nulls are the growing segment, which never populates this column.")
            confidence = "medium"
    for e in ev.get("schema_events_same_partition") or []:
        causes.append(f"Schema event in the same partition: {e['check_name']} {e['column_name']} ({e['detail']}): "
                      "an upstream reporting/policy change happened in this month.")
    others = ev.get("other_drift_alerts_same_partition") or []
    if others:
        causes.append("Co-occurring drift alerts: " + ", ".join(f"{o['column_name']}/{o['metric']}={o['value']}"
                                                                for o in others[:5]) + ".")
    return {
        "summary": (f"{ev['metric']} for {ev['column_name']} in {pid} is {ev['value']:.3f} vs threshold "
                    f"{ev['threshold']} (reference {ref})."),
        "likely_causes": causes or ["No correlated segment or schema change found; evidence is insufficient."],
        "investigation_steps": [
            f"Compare {ev['column_name']} by VendorID and payment_type between {ref} and {pid}.",
            "Check TLC / MTA announcements for the month (fare rules, congestion pricing, new vendors).",
            "If the shift is a confirmed structural change, re-baseline the drift reference to the new regime.",
        ],
        "remediation_suggestion": "No data change. Annotate the alert with the confirmed cause; re-baseline only then.",
        "candidate_rule": dict(_NO_RULE),
        "confidence": confidence,
    }


def _template(ev: dict) -> dict:
    """Built-in provider (no API, no network): explanation computed from the evidence only."""
    return analyze_drift(ev) if ev["incident_type"] == "drift" else analyze_rule(ev)


def _anthropic(ev: dict) -> tuple[dict, str]:
    import anthropic

    client = anthropic.Anthropic()
    resp = client.beta.messages.create(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        system=SYSTEM,
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": RESPONSE_SCHEMA}},
        messages=[{"role": "user", "content": "EVIDENCE (JSON):\n" + json.dumps(ev, indent=2, sort_keys=True)}],
    )
    if resp.stop_reason == "refusal":
        raise RuntimeError(f"model declined: {getattr(resp.stop_details, 'category', None)}")
    text = next(b.text for b in resp.content if b.type == "text")
    return json.loads(text), resp.model


def provider() -> str:
    choice = os.environ.get("DQC_COPILOT_PROVIDER", "auto")
    if choice == "auto":
        return "anthropic" if os.environ.get("ANTHROPIC_API_KEY") else "deterministic_analyzer"
    return choice


# --------------------------------------------------------------------------- public API
def explain(inc: dict) -> dict:
    ev = evidence_for(inc)
    ev_sha = hashlib.sha256(json.dumps(ev, sort_keys=True).encode()).hexdigest()
    prov, model = provider(), None
    if prov == "anthropic":
        try:
            response, model = _anthropic(ev)
        except Exception as exc:  # degrade, and record why
            response, prov = _template(ev), "deterministic_analyzer"
            response["provider_error"] = repr(exc)[:500]
    else:
        response = _template(ev)
    ref = "/".join(str(ev.get(k)) for k in ("run_id", "partition_id", "rule_id", "column_name", "metric") if ev.get(k))
    with psycopg.connect(COPILOT_DSN) as conn:  # least-privileged role: INSERT on suggestions only
        sid = conn.execute(
            """INSERT INTO dq.copilot_suggestions (incident_type, incident_ref, partition_id, evidence,
                   evidence_sha256, provider, model, prompt_version, response)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING suggestion_id""",
            (ev["incident_type"], ref, ev.get("partition_id"), json.dumps(ev), ev_sha, prov, model,
             PROMPT_VERSION, json.dumps(response))).fetchone()[0]
    return {"suggestion_id": sid, "incident_ref": ref, "provider": prov, "model": model,
            "label": "SUGGESTION — not verified, requires human review", "response": response}


def explain_latest(limit: int = 5) -> list[dict]:
    return [explain(i) for i in incidents(limit)]
