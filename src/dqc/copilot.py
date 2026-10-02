"""Quality Copilot — explains incidents AFTER deterministic detection. Never the source of truth.

Guarantees (enforced by construction, not by prompt):
* Input = facts read from dq.* tables (rule results, quarantined samples, drift metrics). The model
  never sees or decides which records are valid.
* Output = a row in dq.copilot_suggestions, written through the `dqc_copilot` Postgres role, which
  has INSERT on that single table and no access to raw/analytics. It cannot modify data.
* Every suggestion stores the exact evidence (+ sha256), prompt version, provider and model, and is
  labelled "SUGGESTION — not verified"; status starts at `proposed` and only a human changes it.
* Without an API key a deterministic template provider is used, so the feature degrades, never fails.
"""

from __future__ import annotations

import hashlib
import json
import os

import psycopg

from dqc import config, db

PROMPT_VERSION = "copilot-v1"
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


def evidence_for(inc: dict) -> dict:
    ev = {k: v for k, v in inc.items() if k != "priority"}
    if inc["incident_type"] == "rule_failure":
        sample = db.query_df("""
            SELECT record_id, original_value, original_record FROM dq.quarantine
            WHERE partition_id = %s AND failed_rule = %s AND resolved_by_run_id IS NULL
            ORDER BY record_id LIMIT 8""", (inc["partition_id"], inc["rule_id"]))
        ev["quarantined_sample"] = sample.to_dicts()
        if inc["severity"] == "critical":
            ev["payment_type_breakdown_of_quarantined"] = db.query_df("""
                SELECT original_record->>'payment_type' AS payment_type, original_record->>'VendorID' AS vendor_id,
                       count(*) AS n
                FROM dq.quarantine WHERE partition_id=%s AND failed_rule=%s AND resolved_by_run_id IS NULL
                GROUP BY 1, 2 ORDER BY n DESC LIMIT 10""", (inc["partition_id"], inc["rule_id"])).to_dicts()
    return json.loads(json.dumps(ev, default=str))


# --------------------------------------------------------------------------- providers
def _template(ev: dict) -> dict:
    """Deterministic fallback: explanation assembled from rule metadata and measured evidence only."""
    if ev["incident_type"] == "drift":
        return {
            "summary": (f"{ev['metric']} for {ev['column_name']} in {ev['partition_id']} is {ev['value']:.3f} "
                        f"vs threshold {ev['threshold']} (reference {ev['reference_partition_id']})."),
            "likely_causes": ["Genuine change in trip mix (seasonality, policy such as congestion pricing)",
                              "Upstream change in how a vendor populates the column"],
            "investigation_steps": [f"Compare {ev['column_name']} distribution by VendorID and payment_type "
                                    "between the two partitions", "Check TLC announcements for the month"],
            "remediation_suggestion": "None until the cause is known; if structural, re-baseline drift reference.",
            "candidate_rule": {"rule_id": "", "severity": "", "description": "", "yaml": ""},
            "confidence": "low",
        }
    critical = ev["severity"] == "critical"
    change = ev.get("failure_rate_change_x")
    breakdown = ev.get("payment_type_breakdown_of_quarantined") or []
    top = ", ".join(f"payment_type={b['payment_type']}/vendor={b['vendor_id']}: {b['n']}" for b in breakdown[:3])
    causes = []
    if ev["rule_id"].startswith("DQ002"):
        causes.append("passenger_count nulls co-occur with payment_type=0 (Flex Fare); growth tracks Flex Fare share")
    if ev["rule_id"].startswith(("DQ021", "DQ022", "DQ023")):
        causes.append("Negative amounts are typically reversal/void/dispute accounting entries (payment_type 3/4/0)")
    if change and change > 1.5:
        causes.append(f"Failure rate is {change:.1f}x the previous partition: likely an upstream behaviour change")
    return {
        "summary": (f"{ev['rule_id']} (v{ev['rule_version']}, {ev['severity']}) failed {ev['failed_rows']:,} of "
                    f"{ev['records_checked']:,} records ({100 * ev['failure_rate']:.3f}%) in {ev['partition_id']}."
                    + (f" Top segments: {top}." if top else "")),
        "likely_causes": causes or ["Insufficient evidence for a specific cause"],
        "investigation_steps": [
            (f"SELECT original_record FROM dq.quarantine WHERE failed_rule='{ev['rule_id']}' "
             f"AND partition_id='{ev['partition_id']}' LIMIT 100") if critical else
            (f"SELECT t.* FROM analytics.fct_clean_trips t WHERE '{ev['rule_id']}' = ANY(t.failed_warning_rules) "
             f"AND t.partition_id='{ev['partition_id']}' LIMIT 100"),
            "Break down failures by VendorID, payment_type and pickup date",
        ],
        "remediation_suggestion": ("Confirm with the source owner; keep records quarantined until reviewed."
                                   if critical else "Records stay in the curated layer with a warning flag; "
                                   "confirm with the source owner whether the pattern is expected."),
        "candidate_rule": {"rule_id": "", "severity": "", "description": "", "yaml": ""},
        "confidence": "low",
    }


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
        return "anthropic" if os.environ.get("ANTHROPIC_API_KEY") else "deterministic_template"
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
            response, prov = _template(ev), "deterministic_template"
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
