"""Raw ingestion: download official TLC files into an immutable, hash-verified raw layer.

Raw files are never modified. Each file is written once (atomic rename), marked
read-only and registered in ``data/raw/manifest.json`` with its SHA-256, row count
and schema. Re-running the ingestion is idempotent: a file already present with a
matching hash is skipped; a file whose hash no longer matches is reported as tampered.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import stat
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import pyarrow.parquet as pq

from dqc import config

log = logging.getLogger("dqc.ingest")


class IntegrityError(RuntimeError):
    pass


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while block := fh.read(chunk):
            h.update(block)
    return h.hexdigest()


def partition_id(service: str, year_month: str) -> str:
    return f"{service}_{year_month}"


def load_manifest(path: Path = config.MANIFEST_PATH) -> dict:
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"files": {}}


def save_manifest(manifest: dict, path: Path = config.MANIFEST_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, path)


def describe_parquet(path: Path) -> dict:
    pf = pq.ParquetFile(path)
    return {
        "row_count": pf.metadata.num_rows,
        "schema": {f.name: str(f.type) for f in pf.schema_arrow},
    }


DOWNLOAD_ATTEMPTS = 4
DOWNLOAD_BACKOFF_S = 2.0


def _download_once(url: str, dest: Path) -> dict:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")
    req = urllib.request.Request(url, headers={"User-Agent": "dq-copilot/0.1"})
    with urllib.request.urlopen(req, timeout=300) as resp, open(tmp, "wb") as out:
        headers = {"last_modified": resp.headers.get("Last-Modified"), "etag": resp.headers.get("ETag")}
        while block := resp.read(1 << 20):
            out.write(block)
    os.replace(tmp, dest)   # atomic: a partial download never becomes a raw file
    return headers


def _download(url: str, dest: Path, attempts: int = DOWNLOAD_ATTEMPTS, backoff_s: float = DOWNLOAD_BACKOFF_S) -> dict:
    """Download with exponential backoff. Transient failures (network, 5xx, 429) are retried; a client
    error such as 404 (month not published yet) fails immediately — retrying cannot fix it."""
    for attempt in range(1, attempts + 1):
        try:
            return _download_once(url, dest)
        except urllib.error.HTTPError as exc:
            if exc.code < 500 and exc.code != 429:
                raise
            last = exc
        except (urllib.error.URLError, TimeoutError, ConnectionError) as exc:
            last = exc
        if attempt < attempts:
            log.warning("download failed (%s), attempt %d/%d, retrying in %.0fs", last, attempt, attempts,
                        backoff_s * 2 ** (attempt - 1))
            time.sleep(backoff_s * 2 ** (attempt - 1))
    raise RuntimeError(f"download failed after {attempts} attempts: {url}") from last


def _make_read_only(path: Path) -> None:
    os.chmod(path, stat.S_IREAD | stat.S_IRGRP | stat.S_IROTH)


def ingest_month(year_month: str, service: str = "yellow", raw_dir: Path = config.RAW_DIR,
                 manifest_path: Path = config.MANIFEST_PATH) -> dict:
    """Download one monthly TLC file into the raw layer (idempotent)."""
    pid = partition_id(service, year_month)
    fname = f"{service}_tripdata_{year_month}.parquet"
    dest = raw_dir / service / fname
    manifest = load_manifest(manifest_path)
    entry = manifest["files"].get(pid)

    if entry and dest.exists():
        if sha256_file(dest) != entry["sha256"]:
            raise IntegrityError(f"{dest} hash differs from manifest: raw layer was modified")
        return {**entry, "action": "skipped_already_ingested"}

    url = f"{config.TLC_BASE_URL}/{fname}"
    headers = _download(url, dest)
    _make_read_only(dest)
    entry = {
        "partition_id": pid,
        "service": service,
        "year_month": year_month,
        "source": "NYC Taxi & Limousine Commission — TLC Trip Record Data",
        "source_url": url,
        "file_format": "parquet",
        "local_path": str(dest.relative_to(raw_dir.parent)).replace("\\", "/"),
        "sha256": sha256_file(dest),
        "size_bytes": dest.stat().st_size,
        "downloaded_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "http_last_modified": headers["last_modified"],
        "http_etag": headers["etag"],
        **describe_parquet(dest),
    }
    manifest["files"][pid] = entry
    save_manifest(manifest, manifest_path)
    return {**entry, "action": "downloaded"}


def ingest_zone_lookup(ref_dir: Path = config.REFERENCE_DIR) -> Path:
    dest = ref_dir / "taxi_zone_lookup.csv"
    if not dest.exists():
        _download(config.TLC_ZONES_URL, dest)
        _make_read_only(dest)
    return dest


def verify_raw_layer(manifest_path: Path = config.MANIFEST_PATH) -> list[dict]:
    """Re-hash every raw file; returns one status row per file."""
    manifest = load_manifest(manifest_path)
    out = []
    for pid, e in sorted(manifest["files"].items()):
        p = manifest_path.parent.parent / e["local_path"]
        ok = p.exists() and sha256_file(p) == e["sha256"]
        out.append({"partition_id": pid, "ok": ok, "path": str(p)})
    return out
