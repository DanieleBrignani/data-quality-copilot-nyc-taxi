"""The built-in copilot provider is pure: evidence dict in, explanation out. No API, no database."""

from dqc import copilot


def _seg(vendor, pt, failed, rows, share, nonneg=0):
    return {"vendor_id": vendor, "payment_type": pt, "failed": failed, "segment_rows": rows,
            "segment_failure_rate": failed / rows, "share_of_failures": share,
            "failed_with_non_negative_total": nonneg}


def _rule_evidence(**over):
    ev = {"incident_type": "rule_failure", "rule_id": "DQ002_passenger_count_not_null", "rule_version": 1,
          "severity": "warning", "dimension": "completeness", "partition_id": "yellow_2025-02",
          "records_checked": 1000, "failed_rows": 200, "failure_rate": 0.2,
          "history": [{"partition_id": "yellow_2025-01", "failure_rate": 0.1},
                      {"partition_id": "yellow_2025-02", "failure_rate": 0.2}],
          "previous_partition": "yellow_2025-01",
          "segments": [_seg(2, 0, 180, 180, 0.9), _seg(1, 1, 20, 500, 0.1)],
          "segments_previous": [_seg(2, 0, 80, 80, 0.8), _seg(1, 1, 20, 500, 0.2)]}
    ev.update(over)
    return ev


def test_systematic_segment_is_identified_and_a_candidate_rule_is_proposed():
    r = copilot.analyze_rule(_rule_evidence())
    text = " ".join(r["likely_causes"])
    assert "VendorID=2 / payment_type=0 (Flex Fare)" in text and "Every record of that segment fails" in text
    assert "accounts for +100 (100% of the increase)" in text
    assert r["confidence"] == "medium"
    assert r["candidate_rule"]["rule_id"] == "DQ002b_passenger_count_not_null_payment_type_0"
    assert "not implemented in the engine yet" in r["candidate_rule"]["yaml"]  # a proposal, never auto-applied
    assert "Trend: 10.000% -> 20.000%" in r["summary"]


def test_diffuse_failures_get_low_confidence_and_no_rule():
    segs = [_seg(1, 1, 30, 5000, 0.3), _seg(2, 1, 30, 5000, 0.3), _seg(2, 2, 40, 5000, 0.4)]
    r = copilot.analyze_rule(_rule_evidence(segments=segs, segments_previous=segs, failed_rows=100, failure_rate=0.01))
    assert r["confidence"] == "low" and r["candidate_rule"]["rule_id"] == ""


def test_negative_fare_with_positive_total_is_flagged_as_hypothesis_and_critical_stays_quarantined():
    ev = _rule_evidence(rule_id="DQ021_fare_amount_range", severity="critical", dimension="validity",
                        segments=[_seg(2, 0, 100, 600, 0.7, nonneg=96), _seg(2, 4, 40, 300, 0.3)],
                        segments_previous=[_seg(2, 0, 20, 400, 0.3), _seg(2, 4, 45, 300, 0.7)])
    r = copilot.analyze_rule(ev)
    text = " ".join(r["likely_causes"])
    assert "96.0% of that segment's failing records still have a non-negative total_amount" in text
    assert "hypothesis" in text and "more than the whole net increase" in text
    assert "do not relax the rule" in r["remediation_suggestion"]
    assert "dq.quarantine" in r["investigation_steps"][0]


def test_null_rate_drift_is_linked_to_the_growing_payment_type():
    ev = {"incident_type": "drift", "partition_id": "yellow_2025-02", "reference_partition_id": "yellow_2025-01",
          "column_name": "passenger_count", "metric": "null_rate_change_pp", "value": 7.0, "threshold": 2.0,
          "payment_type_share_pct": {"yellow_2025-01": {"0": 15.5, "1": 70.0}, "yellow_2025-02": {"0": 22.6, "1": 63.0}},
          "schema_events_same_partition": [], "other_drift_alerts_same_partition": []}
    r = copilot.analyze_drift(ev)
    assert "payment_type=0 (Flex Fare) share moved +7.10 pp" in r["likely_causes"][0]
    assert r["confidence"] == "medium" and r["candidate_rule"]["rule_id"] == ""
    assert "No data change" in r["remediation_suggestion"]
