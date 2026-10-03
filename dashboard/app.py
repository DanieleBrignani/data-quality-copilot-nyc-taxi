"""Streamlit quality dashboard (read-only; uses the dqc_reader role in docker-compose)."""

from __future__ import annotations

import json
import os

import altair as alt
import pandas as pd
import psycopg
import streamlit as st

from dqc import config

# read-only role when its password is configured; never a hardcoded credential
DSN = (os.environ.get("DQC_DASHBOARD_DSN") or config.role_dsn("dqc_reader", "DQC_READER_PASSWORD")
       or config.PG_DSN)
if not DSN:
    st.error("Database credentials are not configured: see .env.example")
    st.stop()
# validated categorical order (dataviz reference palette), assigned in fixed order, never cycled
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#4a3aa7", "#e34948"]
STATUS = {"ok": "#0ca30c", "warn": "#fab219", "alert": "#d03b3b"}

st.set_page_config(page_title="Data Quality Copilot — NYC Taxi", layout="wide")

LATEST = """SELECT DISTINCT ON (pq.partition_id) pq.*, p.year_month
            FROM dq.partition_quality pq JOIN dq.pipeline_runs r USING (run_id)
            JOIN dq.dataset_partitions p USING (partition_id) WHERE p.service='yellow'
            ORDER BY pq.partition_id, r.started_at DESC"""


@st.cache_data(ttl=60)
def q(sql: str, params: tuple | None = None) -> pd.DataFrame:
    with psycopg.connect(DSN) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        return pd.DataFrame(cur.fetchall(), columns=[d.name for d in cur.description])


def line(df, x, y, color=None, title="", fmt=".2f"):
    enc = {"x": alt.X(f"{x}:N", title=None, sort=None), "y": alt.Y(f"{y}:Q", title=title, scale=alt.Scale(zero=False)),
           "tooltip": [x, alt.Tooltip(f"{y}:Q", format=fmt)] + ([color] if color else [])}
    if color:
        enc["color"] = alt.Color(f"{color}:N", scale=alt.Scale(range=SERIES), legend=alt.Legend(orient="top"))
    return (alt.Chart(df).mark_line(strokeWidth=2, point=alt.OverlayMarkDef(size=64)).encode(**enc)
            .properties(height=260))


def bars(df, x, y, color=None, title="", fmt=",.0f"):
    enc = {"x": alt.X(f"{x}:N", title=None, sort=None), "y": alt.Y(f"{y}:Q", title=title),
           "tooltip": [x, alt.Tooltip(f"{y}:Q", format=fmt)] + ([color] if color else [])}
    if color:
        enc["color"] = alt.Color(f"{color}:N", scale=alt.Scale(range=SERIES), legend=alt.Legend(orient="top"))
        enc["xOffset"] = f"{color}:N"
    else:
        enc["color"] = alt.value(SERIES[0])
    return alt.Chart(df).mark_bar(cornerRadiusEnd=4).encode(**enc).properties(height=260)


latest = q(LATEST).sort_values("year_month")
if latest.empty:
    st.warning("No pipeline runs yet. Run `python -m dqc run` first.")
    st.stop()

st.title("Data Quality Copilot — NYC Taxi")
st.caption("Real TLC Yellow Taxi partitions · deterministic rules decide · statistics investigate · "
           "the copilot only suggests")

cur = latest.iloc[-1]
k = st.columns(5)
k[0].metric("Quality score (latest)", f"{cur.quality_score:.2f}",
            f"{cur.quality_score - latest.iloc[-2].quality_score:+.2f}" if len(latest) > 1 else None)
k[1].metric("Valid record rate", f"{cur.valid_record_rate:.2f}%")
k[2].metric("Records processed (all partitions)", f"{latest.rows_total.sum():,}")
k[3].metric("Quarantined records", f"{latest.quarantined_records.sum():,}",
            f"{100 * latest.quarantined_records.sum() / latest.rows_total.sum():.2f}% of total", delta_color="off")
drift_alerts = q("""SELECT d.partition_id, count(*) FILTER (WHERE status='alert') AS alerts
                    FROM dq.drift_results d JOIN (""" + LATEST + """) l USING (run_id, partition_id) GROUP BY 1""")
k[4].metric("Drift alerts (latest runs)", int(drift_alerts.alerts.sum()) if not drift_alerts.empty else 0)

tabs = st.tabs(["Trends", "Rules", "Drift", "Anomalies", "Quarantine", "Schema", "Copilot", "Audit", "ML model"])

with tabs[0]:
    c1, c2 = st.columns(2)
    long = latest.melt(id_vars="year_month", value_vars=["quality_score", "valid_record_rate"],
                       var_name="measure", value_name="value")
    c1.subheader("Quality score & valid-record rate")
    c1.altair_chart(line(long, "year_month", "value", "measure", "score / %"), width="stretch")
    c2.subheader("Quarantined records per partition")
    c2.altair_chart(bars(latest, "year_month", "quarantined_records", title="records"), width="stretch")
    c3, c4 = st.columns(2)
    c3.subheader("Dataset volume")
    c3.altair_chart(bars(latest, "year_month", "rows_total", title="rows"), width="stretch")
    c4.subheader("Dimension scores")
    dims = pd.DataFrame([{"year_month": r.year_month, "dimension": d, "score": v}
                         for r in latest.itertuples() for d, v in (r.dimension_scores or {}).items()])
    if not dims.empty:
        c4.altair_chart(line(dims, "year_month", "score", "dimension", "score"), width="stretch")
    st.dataframe(latest[["partition_id", "rows_total", "valid_rows", "quarantined_records", "warning_only_records",
                         "valid_record_rate", "quality_score", "schema_status", "source_lag_days",
                         "duration_s", "rows_per_sec"]], hide_index=True, width="stretch")

with tabs[1]:
    rr = q("""SELECT rr.partition_id, l.year_month, rr.rule_id, rr.rule_version, rr.severity, rr.dimension,
                     rr.columns, rr.records_checked, rr.failed_rows, rr.failure_rate
              FROM dq.rule_results rr JOIN (""" + LATEST + """) l USING (run_id, partition_id)
              ORDER BY rr.partition_id, rr.failed_rows DESC""")
    sev = st.radio("Severity", ["critical", "warning"], horizontal=True)
    sub = rr[(rr.severity == sev) & (rr.failed_rows > 0)].copy()
    sub["failure_pct"] = 100 * sub.failure_rate
    st.altair_chart(line(sub, "year_month", "failure_pct", "rule_id", "failure rate %", ".4f"),
                    width="stretch")
    st.dataframe(rr, hide_index=True, width="stretch")

with tabs[2]:
    dr = q("""SELECT d.partition_id, d.reference_partition_id, d.column_name, d.metric, d.value, d.threshold, d.status
              FROM dq.drift_results d JOIN (""" + LATEST + """) l USING (run_id, partition_id)""")
    if dr.empty:
        st.info("No drift results yet.")
    else:
        metric = st.selectbox("Metric", sorted(dr.metric.unique()), index=sorted(dr.metric.unique()).index("psi"))
        m = dr[dr.metric == metric]
        heat = alt.Chart(m).mark_rect(stroke="#fcfcfb", strokeWidth=2).encode(
            x=alt.X("partition_id:N", title=None), y=alt.Y("column_name:N", title=None),
            color=alt.Color("status:N", scale=alt.Scale(domain=list(STATUS), range=list(STATUS.values())),
                            legend=alt.Legend(orient="top", title="status")),
            tooltip=["partition_id", "reference_partition_id", "column_name",
                     alt.Tooltip("value:Q", format=".4f"), "threshold", "status"])
        text = alt.Chart(m).mark_text(fontSize=11).encode(
            x="partition_id:N", y="column_name:N", text=alt.Text("value:Q", format=".3f"),
            color=alt.value("#0b0b0b"))
        st.altair_chart((heat + text).properties(height=34 * m.column_name.nunique()), width="stretch")
        st.caption("Status is also written in the table below — colour is never the only encoding.")
        st.dataframe(dr[dr.status.isin(["alert", "warn"])], hide_index=True, width="stretch")

with tabs[3]:
    an = q("""SELECT a.partition_id, a.method, a.records_scored, a.anomalies, a.anomaly_rate, a.runtime_s, a.per_feature
              FROM dq.anomaly_results a JOIN (""" + LATEST + """) l USING (run_id, partition_id) ORDER BY 1, 2""")
    st.info("Anomaly detectors run on rule-VALID records only and never quarantine: they produce an "
            "investigation queue. See README for why they are not a substitute for rules.")
    if not an.empty:
        an["anomaly_pct"] = 100 * an.anomaly_rate
        st.altair_chart(bars(an, "partition_id", "anomaly_pct", "method", "% of valid records flagged", ".3f"),
                        width="stretch")
        st.dataframe(an, hide_index=True, width="stretch")
        top = q("""SELECT ar.partition_id, ar.method, ar.record_id, ar.score, ar.features
                   FROM dq.anomaly_records ar JOIN (""" + LATEST + """) l USING (run_id, partition_id)
                   WHERE ar.method='isolation_forest' ORDER BY ar.score DESC LIMIT 50""")
        st.subheader("Top Isolation Forest anomalies")
        st.dataframe(top, hide_index=True, width="stretch")

with tabs[4]:
    qs = q("""SELECT partition_id, failed_rule, count(*) AS rows, count(DISTINCT record_id) AS records,
                     count(*) FILTER (WHERE review_status <> 'pending') AS reviewed
              FROM dq.quarantine WHERE resolved_by_run_id IS NULL GROUP BY 1, 2 ORDER BY 1, 3 DESC""")
    st.dataframe(qs, hide_index=True, width="stretch")
    c1, c2 = st.columns(2)
    part = c1.selectbox("Partition", sorted(qs.partition_id.unique())) if not qs.empty else None
    rule = c2.selectbox("Rule", sorted(qs[qs.partition_id == part].failed_rule.unique())) if part else None
    if part and rule:
        rows = q("""SELECT quarantine_id, record_id, original_value, reason, pipeline_run_id, quarantined_at,
                           review_status, original_record
                    FROM dq.quarantine WHERE partition_id=%s AND failed_rule=%s AND resolved_by_run_id IS NULL
                    ORDER BY quarantine_id LIMIT 200""", (part, rule))
        st.dataframe(rows, hide_index=True, width="stretch")

with tabs[5]:
    st.dataframe(q("""SELECT s.partition_id, s.check_name, s.column_name, s.severity, s.detail, s.checked_at
                      FROM dq.schema_checks s ORDER BY s.checked_at DESC LIMIT 200"""),
                 hide_index=True, width="stretch")

with tabs[6]:
    st.warning("Every item below is a SUGGESTION generated after detection. It is not verified, changes no "
               "data, and requires human review.")
    sg = q("""SELECT suggestion_id, created_at, incident_type, incident_ref, provider, model, prompt_version,
                     status, evidence_sha256, response FROM dq.copilot_suggestions ORDER BY suggestion_id DESC LIMIT 30""")
    for r in sg.itertuples():
        resp = r.response if isinstance(r.response, dict) else json.loads(r.response)
        with st.expander(f"#{r.suggestion_id} · {r.incident_type} · {r.incident_ref} · [{r.status}] · {r.provider}"):
            st.markdown(f"**Summary.** {resp.get('summary', '')}")
            st.markdown("**Likely causes (hypotheses)**\n" + "\n".join(f"- {c}" for c in resp.get("likely_causes", [])))
            st.markdown("**Investigation steps**\n" + "\n".join(f"- {c}" for c in resp.get("investigation_steps", [])))
            st.markdown(f"**Possible remediation (proposal).** {resp.get('remediation_suggestion', '')}")
            cr = resp.get("candidate_rule") or {}
            if cr.get("yaml"):
                st.code(cr["yaml"], language="yaml")
            st.caption(f"confidence: {resp.get('confidence')} · evidence sha256 {r.evidence_sha256[:16]}… · "
                       f"model {r.model} · prompt {r.prompt_version}")

with tabs[7]:
    st.subheader("Pipeline runs")
    st.dataframe(q("""SELECT run_id, started_at, finished_at, status, trigger, ruleset_version, rules_sha256,
                             code_version, partitions, rows_processed, duration_s, error
                      FROM dq.pipeline_runs ORDER BY started_at DESC LIMIT 50"""), hide_index=True,
                 width="stretch")
    st.subheader("Raw partitions (immutable sources)")
    st.dataframe(q("""SELECT partition_id, source_url, file_format, sha256, size_bytes, row_count, downloaded_at,
                             source_last_modified, loaded_sha256 = sha256 AS loaded_matches_source
                      FROM dq.dataset_partitions ORDER BY partition_id"""), hide_index=True, width="stretch")
    st.subheader("Quarantine review log")
    st.dataframe(q("SELECT * FROM dq.quarantine_review_log ORDER BY reviewed_at DESC LIMIT 100"), hide_index=True,
                 width="stretch")

with tabs[8]:
    regs = q("SELECT DISTINCT ON (model_name) * FROM dq.model_registry ORDER BY model_name, version DESC")
    if regs.empty:
        st.info("No model registered yet. Run `python -m dqc ml train` then `python -m dqc ml score`.")
    else:
        name = st.radio("Model", list(regs.model_name), horizontal=True)
        r = regs[regs.model_name == name].iloc[0]
        st.caption(f"{r.model_name} v{r.version} · target {r.target} · {r.algorithm} · trained on {r.train_partition} "
                   f"({r.train_rows:,} rows), selected and calibrated on {r.validation_partition} · "
                   f"artifact sha256 {r.artifact_sha256[:16]}…")
        mm = q("""SELECT partition_id, split, n, mae, mae_ci_low, mae_ci_high, rmse, median_ae, r2, flagged, flag_rate,
                         mae_vs_validation, status
                  FROM dq.model_metrics WHERE model_name=%s AND version=%s ORDER BY partition_id""",
               (r.model_name, int(r.version)))
        c1, c2 = st.columns(2)
        c1.subheader("MAE per partition, out-of-time monitoring")
        c1.altair_chart(bars(mm, "partition_id", "mae", title="MAE", fmt=".3f"), width="stretch")
        sel = pd.DataFrame([{"candidate": k, "validation_mae": v["mae"]} for k, v in (r.selection or {}).items()
                            if not k.startswith("baseline_median")]).sort_values("validation_mae")
        c2.subheader("Candidates on the validation month (median baseline omitted)")
        c2.altair_chart(bars(sel, "candidate", "validation_mae", title="MAE", fmt=".3f"), width="stretch")
        st.dataframe(mm, hide_index=True, width="stretch")
        st.subheader("Rolling-origin backtest (train on month t, evaluate on t+1)")
        st.dataframe(pd.DataFrame(r.backtest or []), hide_index=True, width="stretch")
        st.subheader("Top flagged records: investigation queue")
        st.dataframe(q("""SELECT partition_id, record_id, actual_value, round(predicted_value::numeric, 2) AS predicted,
                                 round(log_ratio::numeric, 3) AS log_ratio, features
                          FROM dq.model_flags WHERE model_name=%s AND version=%s
                          ORDER BY log_ratio DESC LIMIT 100""", (r.model_name, int(r.version))),
                     hide_index=True, width="stretch")
