#!/usr/bin/env python
from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.storage.s3_photo_storage import _build_s3_client_kwargs  # noqa: E402


def _build_s3_client(*, region: str):
    import boto3  # type: ignore[import]

    kwargs = dict(_build_s3_client_kwargs())
    kwargs["region_name"] = region
    return boto3.client("s3", **kwargs)


def _target_key(storage_key: str) -> str:
    return storage_key


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Restore version-pinned S3 media into an isolated target bucket.")
    parser.add_argument("--media-manifest", required=True, help="Path to the S3 media manifest JSON.")
    parser.add_argument("--target-bucket", required=True, help="Isolated restore bucket for recovered media.")
    parser.add_argument("--target-region", required=True, help="Region of the isolated restore bucket.")
    parser.add_argument("--output", required=True, help="Output JSON path for the restore result manifest.")
    return parser


def _load_manifest(path: Path) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("format") != "novu-s3-media-manifest-v1":
        raise RuntimeError(f"Unsupported media manifest format in {path}.")
    return payload


def _head_if_exists(client, *, bucket: str, key: str):
    try:
        return client.head_object(Bucket=bucket, Key=key)
    except Exception as exc:
        error_code = getattr(exc, "response", {}).get("Error", {}).get("Code")
        if error_code in {"NoSuchKey", "404", "NotFound"}:
            return None
        raise


def main() -> int:
    args = _build_parser().parse_args()
    manifest_path = Path(args.media_manifest)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    manifest = _load_manifest(manifest_path)
    source_bucket = str(manifest["source_bucket"])
    source_region = str(manifest["source_region"])
    target_bucket = args.target_bucket.strip()
    target_region = args.target_region.strip()

    if not target_bucket:
        raise SystemExit("target bucket is required")
    if target_bucket == source_bucket:
        raise SystemExit("target bucket must differ from the authoritative source bucket to avoid destructive overwrite.")

    client = _build_s3_client(region=target_region or source_region)

    restored_objects: list[dict[str, object]] = []
    for item in manifest.get("objects", []):
        key = str(item["key"])
        target_key = _target_key(key)
        if _head_if_exists(client, bucket=target_bucket, key=target_key) is not None:
            raise SystemExit(
                f"Refusing to overwrite existing restore target object: bucket={target_bucket!r} key={target_key!r}"
            )

        copy_source = {
            "Bucket": source_bucket,
            "Key": key,
            "VersionId": str(item["version_id"]),
        }
        client.copy_object(
            Bucket=target_bucket,
            Key=target_key,
            CopySource=copy_source,
        )
        restored = client.head_object(Bucket=target_bucket, Key=target_key)
        restored_size = int(restored.get("ContentLength", 0))
        expected_size = int(item.get("size", 0))
        if restored_size != expected_size:
            raise SystemExit(
                f"Restored object size mismatch for key={key!r}: expected={expected_size} actual={restored_size}"
            )

        restored_objects.append(
            {
                "source_key": key,
                "target_key": target_key,
                "source_version_id": str(item["version_id"]),
                "size": restored_size,
            }
        )

    output = {
        "format": "novu-restored-s3-media-v1",
        "restored_at": datetime.now(UTC).isoformat(),
        "source_bucket": source_bucket,
        "source_region": source_region,
        "target_bucket": target_bucket,
        "target_region": target_region or source_region,
        "db_backup_file": manifest.get("db_backup_file"),
        "db_manifest_file": manifest.get("db_manifest_file"),
        "declared_recovery_point": manifest.get("declared_recovery_point"),
        "object_count": len(restored_objects),
        "app_compatible_key_layout": True,
        "objects": restored_objects,
    }
    output_path.write_text(json.dumps(output, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "ok",
                "output": str(output_path),
                "object_count": len(restored_objects),
                "target_bucket": target_bucket,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
