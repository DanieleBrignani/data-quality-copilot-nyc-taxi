import json
from datetime import datetime, timedelta

import polars as pl
import pytest

from dqc import rules
from tests.conftest import trips_frame, valid_trip

RS = rules.load_ruleset()
YM = "2025-01"


def failed(rows, rule_id):
    df = trips_frame(rows)
    ev = rules.evaluate(df, RS, YM)
    return ev.failures[rule_id].to_list()


def summary(rows):
    return rules.evaluate(trips_frame(rows), RS, YM).summary


def test_valid_record_passes_every_rule():
    ev = rules.evaluate(trips_frame([valid_trip()]), RS, YM)
    assert ev.summary["failed_rows"].sum() == 0


def test_ruleset_is_versioned_and_unique():
    assert RS.version and len(RS.sha256) == 64
    assert all(r.rule_version >= 1 for r in RS.rules)
    assert len({r.rule_id for r in RS.rules}) == len(RS.rules)


def test_mandatory_null():
    assert failed([valid_trip(fare_amount=None), valid_trip()], "DQ001_mandatory_fields_not_null") == [True, False]


def test_passenger_count_null_is_only_a_warning():
    assert failed([valid_trip(passenger_count=None)], "DQ002_passenger_count_not_null") == [True]
    assert failed([valid_trip(passenger_count=None)], "DQ024_passenger_count_max") == [False]


@pytest.mark.parametrize("value,expected", [(-0.01, True), (0.0, False), (999.0, False), (1000.01, True)])
def test_negative_and_implausible_fare(value, expected):
    assert failed([valid_trip(fare_amount=value)], "DQ021_fare_amount_range") == [expected]


def test_negative_tip():
    assert failed([valid_trip(tip_amount=-1.0)], "DQ023_tip_amount_non_negative") == [True]


def test_impossible_trip_duration():
    p = datetime(2025, 1, 10, 8)
    rows = [valid_trip(tpep_pickup_datetime=p, tpep_dropoff_datetime=p),                       # zero
            valid_trip(tpep_pickup_datetime=p, tpep_dropoff_datetime=p - timedelta(minutes=5)),  # negative
            valid_trip(tpep_pickup_datetime=p, tpep_dropoff_datetime=p + timedelta(hours=25))]   # > 24h
    assert failed(rows, "DQ010_pickup_before_dropoff") == [True, True, False]
    assert failed(rows, "DQ011_trip_duration_max") == [False, False, True]


def test_pickup_outside_partition_month():
    p = datetime(2009, 1, 1, 0, 5)
    assert failed([valid_trip(tpep_pickup_datetime=p, tpep_dropoff_datetime=p + timedelta(minutes=9))],
                  "DQ012_pickup_in_partition_window") == [True]


@pytest.mark.parametrize("pc,crit,warn", [(0, False, True), (1, False, False), (6, False, False), (7, True, False)])
def test_invalid_passenger_count(pc, crit, warn):
    assert failed([valid_trip(passenger_count=pc)], "DQ024_passenger_count_max") == [crit]
    assert failed([valid_trip(passenger_count=pc)], "DQ025_passenger_count_zero") == [warn]


def test_accepted_values():
    assert failed([valid_trip(payment_type=9)], "DQ031_payment_type_accepted") == [True]
    assert failed([valid_trip(VendorID=3)], "DQ030_vendor_id_accepted") == [True]
    assert failed([valid_trip(RatecodeID=None)], "DQ032_ratecode_accepted") == [False]
    assert failed([valid_trip(PULocationID=999)], "DQ034_location_ids_known") == [True]


def test_total_reconciliation_is_vendor_scoped():
    # Vendor 1 embeds congestion (2.5) + cbd (0.75) inside `extra` -> total lower than the naive sum.
    v1 = valid_trip(VendorID=1, extra=3.25 + 1.0, total_amount=27.15 + 1.0)
    v2_same = valid_trip(VendorID=2, extra=3.25 + 1.0, total_amount=27.15 + 1.0)
    flex = valid_trip(payment_type=0, total_amount=99.0)
    broken = valid_trip(total_amount=50.0)
    assert failed([valid_trip(), v1, v2_same, flex, broken], "DQ040_total_amount_reconciles") == [
        False, False, True, False, True]
    s = summary([valid_trip(), flex]).filter(pl.col("rule_id") == "DQ040_total_amount_reconciles")
    assert s["records_checked"].item() == 1  # flex fare is out of scope, not "passed"


def test_exact_duplicates_keep_first_occurrence():
    r = valid_trip()
    assert failed([r, r, r, valid_trip(fare_amount=10.0)], "DQ050_exact_duplicate") == [False, True, True, False]


def test_business_key_duplicate_excludes_reversal_pairs():
    charge = valid_trip()
    reversal = valid_trip(fare_amount=-18.4, total_amount=-27.15, tip_amount=0.0)
    resubmitted = valid_trip(fare_amount=18.5)
    assert failed([charge, reversal], "DQ051_business_key_duplicate") == [False, False]
    assert failed([charge, resubmitted], "DQ051_business_key_duplicate") == [True, True]


def test_quarantine_rows_keep_original_values_and_never_drop_input():
    rows = [valid_trip(), valid_trip(fare_amount=-5.0, total_amount=-5.0), valid_trip(passenger_count=9)]
    df = trips_frame(rows)
    ev = rules.evaluate(df, RS, YM)
    flags = rules.record_flags(ev, RS)
    q = rules.quarantine_rows(df, flags, RS)
    assert df.height == 3  # engine is pure
    assert set(q["record_id"]) == {"t:1", "t:2"}
    fare = q.filter(pl.col("failed_rule") == "DQ021_fare_amount_range").row(0, named=True)
    assert fare["original_value"] == "fare_amount=-5.0"
    assert json.loads(fare["original_record"])["fare_amount"] == -5.0
    assert fare["severity"] == "critical" and fare["reason"]
    assert flags.filter(pl.col("record_id") == "t:0").is_empty()


def test_warning_does_not_quarantine():
    df = trips_frame([valid_trip(passenger_count=0)])
    ev = rules.evaluate(df, RS, YM)
    flags = rules.record_flags(ev, RS)
    assert flags["is_valid"].to_list() == [True]
    assert rules.quarantine_rows(df, flags, RS).is_empty()
