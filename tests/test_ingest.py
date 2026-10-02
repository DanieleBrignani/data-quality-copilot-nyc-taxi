import os
import stat

import pytest

from dqc import ingest
from tests.conftest import trips_frame, valid_trip


@pytest.fixture
def fake_download(monkeypatch, tmp_path):
    calls = []
    src = tmp_path / "src.parquet"
    trips_frame([valid_trip()] * 3, with_ids=False).write_parquet(src)

    def _dl(url, dest):
        calls.append(url)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(src.read_bytes())
        return {"last_modified": "Wed, 23 Apr 2025 16:31:58 GMT", "etag": "x"}

    monkeypatch.setattr(ingest, "_download", _dl)
    return calls


def test_ingestion_is_idempotent_and_raw_is_read_only(fake_download, tmp_path):
    raw, manifest = tmp_path / "raw", tmp_path / "raw" / "manifest.json"
    first = ingest.ingest_month("2025-01", raw_dir=raw, manifest_path=manifest)
    second = ingest.ingest_month("2025-01", raw_dir=raw, manifest_path=manifest)
    assert first["action"] == "downloaded" and second["action"] == "skipped_already_ingested"
    assert len(fake_download) == 1
    assert first["row_count"] == 3 and len(first["sha256"]) == 64
    path = raw / "yellow" / "yellow_tripdata_2025-01.parquet"
    assert not os.stat(path).st_mode & stat.S_IWRITE
    assert ingest.load_manifest(manifest)["files"].keys() == {"yellow_2025-01"}


def test_tampered_raw_file_is_detected(fake_download, tmp_path):
    raw, manifest = tmp_path / "raw", tmp_path / "raw" / "manifest.json"
    ingest.ingest_month("2025-01", raw_dir=raw, manifest_path=manifest)
    path = raw / "yellow" / "yellow_tripdata_2025-01.parquet"
    os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    with open(path, "ab") as fh:
        fh.write(b"tamper")
    with pytest.raises(ingest.IntegrityError):
        ingest.ingest_month("2025-01", raw_dir=raw, manifest_path=manifest)
    assert ingest.verify_raw_layer(manifest)[0]["ok"] is False
