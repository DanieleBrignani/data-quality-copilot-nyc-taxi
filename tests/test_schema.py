import polars as pl

from dqc import schema
from tests.conftest import trips_frame, valid_trip


def _raw(rows=None):
    return trips_frame(rows or [valid_trip()], with_ids=False)


def test_valid_schema_with_documented_optional_column():
    df, res = schema.validate_and_normalise(_raw())
    assert df is not None and not res.is_breaking
    assert [e.check for e in res.events] == ["optional_column_present"]


def test_optional_column_absent_is_filled_with_nulls():
    df, res = schema.validate_and_normalise(_raw().drop("cbd_congestion_fee"))
    assert not res.is_breaking and res.events == []
    assert df["cbd_congestion_fee"].null_count() == 1


def test_missing_required_column_rejects_partition():
    df, res = schema.validate_and_normalise(_raw().drop("fare_amount"))
    assert df is None and res.is_breaking
    assert any(e.check == "missing_required_column" and e.column == "fare_amount" for e in res.events)


def test_type_change_rejects_partition():
    df, res = schema.validate_and_normalise(_raw().with_columns(pl.col("fare_amount").cast(pl.String)))
    assert df is None
    assert any(e.check == "type_mismatch" and e.column == "fare_amount" for e in res.events)


def test_unexpected_column_is_warned_and_dropped():
    df, res = schema.validate_and_normalise(_raw().with_columns(pl.lit(1).alias("surprise_col")))
    assert df is not None and "surprise_col" not in df.columns
    assert any(e.check == "unexpected_column" and e.severity == "warning" for e in res.events)
    assert res.unexpected_changes == 1


def test_known_alias_is_normalised():
    df, res = schema.validate_and_normalise(_raw().rename({"Airport_fee": "airport_fee"}))
    assert df is not None and "Airport_fee" in df.columns
    assert any(e.check == "column_alias" for e in res.events)


def test_diff_vs_previous_partition():
    ev = schema.diff_vs_previous({"a": "int64", "b": "double", "new": "double"}, {"a": "int32", "b": "double"})
    assert [(e.check, e.column) for e in ev] == [("column_added_vs_previous", "new"),
                                                  ("type_changed_vs_previous", "a")]
