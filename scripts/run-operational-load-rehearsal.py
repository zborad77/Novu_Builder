from __future__ import annotations

import argparse
import asyncio
from collections import Counter, defaultdict
from datetime import UTC, datetime
from io import BytesIO
import json
from pathlib import Path
import statistics
import time
from typing import Any

import httpx

try:
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * quantile)))
    return float(ordered[index])


def summarize_latencies(values: list[float], statuses: Counter[str], errors: list[str]) -> dict[str, Any]:
    return {
        "count": len(values),
        "errorCount": len(errors),
        "errorRate": round((len(errors) / len(values)) if values else 0.0, 4),
        "avgMs": round(float(statistics.mean(values)) if values else 0.0, 1),
        "p50Ms": round(percentile(values, 0.50), 1),
        "p95Ms": round(percentile(values, 0.95), 1),
        "p99Ms": round(percentile(values, 0.99), 1),
        "maxMs": round(max(values), 1) if values else 0.0,
        "statusCodes": dict(sorted(statuses.items())),
        "sampleErrors": errors[:8],
    }


def parse_tenants(path: str) -> list[dict[str, str]]:
    if not path:
        return [{"label": "demo", "email": "demo@novu.local", "password": "demo1234"}]
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    tenants = payload.get("tenants") if isinstance(payload, dict) else None
    if not isinstance(tenants, list) or not tenants:
        raise SystemExit("Tenant file must contain {'tenants': [...]} with at least one tenant.")
    return tenants


def generate_jpeg_bytes() -> bytes:
    if Image is None:
        raise RuntimeError("Pillow is required for the rehearsal image payload.")
    image = Image.new("RGB", (1600, 900), color=(214, 226, 238))
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=88)
    return buffer.getvalue()


async def record_request(
    bucket: dict[str, Any],
    coro,
    *,
    ok_statuses: tuple[int, ...],
) -> httpx.Response:
    started = time.perf_counter()
    response = await coro
    duration_ms = (time.perf_counter() - started) * 1000.0
    bucket["values"].append(duration_ms)
    bucket["statuses"][str(response.status_code)] += 1
    if response.status_code not in ok_statuses:
        bucket["errors"].append(response.text[:240])
    return response


async def login(client: httpx.AsyncClient, api_prefix: str, email: str, password: str, bucket: dict[str, Any]) -> dict[str, Any]:
    response = await record_request(
        bucket,
        client.post(f"{api_prefix}/auth/login", json={"email": email, "password": password}),
        ok_statuses=(200,),
    )
    response.raise_for_status()
    return response.json()


async def refresh(client: httpx.AsyncClient, api_prefix: str, refresh_token: str, bucket: dict[str, Any]) -> dict[str, Any]:
    response = await record_request(
        bucket,
        client.post(f"{api_prefix}/auth/refresh", json={"refreshToken": refresh_token}),
        ok_statuses=(200,),
    )
    response.raise_for_status()
    return response.json()


async def create_case(
    client: httpx.AsyncClient,
    api_prefix: str,
    headers: dict[str, str],
    bucket: dict[str, Any],
    *,
    title: str,
    description: str,
    address_label: str,
) -> str:
    response = await record_request(
        bucket,
        client.post(
            f"{api_prefix}/cases",
            headers=headers,
            json={
                "title": title,
                "description": description,
                "propertyType": "house",
                "repairScope": "facade_repair",
                "addressLabel": address_label,
            },
        ),
        ok_statuses=(201,),
    )
    response.raise_for_status()
    return str(response.json()["id"])


async def upload_and_preview(
    client: httpx.AsyncClient,
    api_prefix: str,
    headers: dict[str, str],
    upload_bucket: dict[str, Any],
    preview_bucket: dict[str, Any],
    *,
    case_id: str,
    filename: str,
    image_bytes: bytes,
) -> str | None:
    response = await record_request(
        upload_bucket,
        client.post(
            f"{api_prefix}/cases/{case_id}/images",
            headers=headers,
            files={"files": (filename, image_bytes, "image/jpeg")},
            data={"isPrimary": "true"},
        ),
        ok_statuses=(201,),
    )
    response.raise_for_status()
    uploaded = response.json().get("uploaded") or []
    image_id = uploaded[0].get("id") if uploaded and isinstance(uploaded[0], dict) else None
    if isinstance(image_id, str):
        preview = await record_request(
            preview_bucket,
            client.get(
                f"{api_prefix}/images/{image_id}/preview",
                headers=headers,
                follow_redirects=False,
            ),
            ok_statuses=(302, 307),
        )
        if preview.status_code not in (302, 307):
            preview.raise_for_status()
    return image_id if isinstance(image_id, str) else None


async def enqueue_job(
    client: httpx.AsyncClient,
    api_prefix: str,
    headers: dict[str, str],
    bucket: dict[str, Any],
    *,
    case_id: str,
) -> dict[str, Any]:
    response = await record_request(
        bucket,
        client.post(f"{api_prefix}/cases/{case_id}/analysis-jobs", headers=headers),
        ok_statuses=(200, 202),
    )
    response.raise_for_status()
    return response.json()


async def get_job(
    client: httpx.AsyncClient,
    api_prefix: str,
    headers: dict[str, str],
    bucket: dict[str, Any],
    *,
    job_id: str,
) -> dict[str, Any] | None:
    response = await record_request(
        bucket,
        client.get(f"{api_prefix}/analysis-jobs/{job_id}", headers=headers),
        ok_statuses=(200,),
    )
    return response.json() if response.status_code == 200 else None


async def sample_internal(
    client: httpx.AsyncClient,
    observer_client: httpx.AsyncClient,
    api_prefix: str,
    observer_headers: dict[str, str],
) -> dict[str, Any]:
    sample: dict[str, Any] = {"observedAt": utc_now_iso()}
    ready = await client.get(f"{api_prefix}/ready/processing?strict=true")
    sample["processingReady"] = ready.json()
    if observer_headers:
        internal = await observer_client.get(f"{api_prefix}/health/internal", headers=observer_headers)
        sample["internalHealth"] = internal.json()
    return sample


async def poll_terminal(
    client: httpx.AsyncClient,
    api_prefix: str,
    headers: dict[str, str],
    poll_bucket: dict[str, Any],
    *,
    job_id: str,
    timeout_seconds: float,
    interval_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    payload: dict[str, Any] = {"id": job_id, "status": "unknown", "finished": False}
    while time.monotonic() < deadline:
        current = await get_job(client, api_prefix, headers, poll_bucket, job_id=job_id)
        if current is not None:
            payload = current
            status = str(current.get("status") or "unknown")
            if status in {"completed", "failed", "canceled", "cancelled", "dead_letter"}:
                payload["finished"] = True
                return payload
        await asyncio.sleep(interval_seconds)
    payload["finished"] = False
    return payload


async def async_main() -> int:
    parser = argparse.ArgumentParser(description="Operational load rehearsal for NOVU Builder.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--tenant-file", default="")
    parser.add_argument("--observer-email", default="admin@novu.cz")
    parser.add_argument("--observer-password", default="NovuAdmin2024!")
    parser.add_argument("--auth-requests", type=int, default=24)
    parser.add_argument("--case-count", type=int, default=18)
    parser.add_argument("--retry-probe-jobs", type=int, default=6)
    parser.add_argument("--sustained-flows", type=int, default=6)
    parser.add_argument("--timeout", type=float, default=20.0)
    parser.add_argument("--poll-timeout", type=float, default=120.0)
    parser.add_argument("--poll-interval", type=float, default=2.0)
    parser.add_argument("--json-out", default="")
    args = parser.parse_args()

    api_prefix = args.base_url.rstrip("/") + "/api/v1"
    tenants = parse_tenants(args.tenant_file)
    image_bytes = generate_jpeg_bytes()
    buckets = {
        key: {"values": [], "statuses": Counter(), "errors": []}
        for key in ("auth_login", "auth_refresh", "case_create", "image_upload", "image_preview", "analysis_enqueue", "analysis_poll", "sustained_flow")
    }
    notes: list[str] = []
    client = httpx.AsyncClient(timeout=args.timeout)
    observer_client = httpx.AsyncClient(timeout=args.timeout)
    headers_by_tenant: dict[str, dict[str, str]] = {}
    observer_headers: dict[str, str] = {}
    created_cases: list[dict[str, Any]] = []
    samples: list[dict[str, Any]] = []
    try:
        for tenant in tenants:
            auth = await login(client, api_prefix, tenant["email"], tenant["password"], buckets["auth_login"])
            headers_by_tenant[tenant["label"]] = {"Authorization": f"Bearer {auth['accessToken']}"}
        if args.observer_email and args.observer_password:
            observer_auth = await login(client, api_prefix, args.observer_email, args.observer_password, buckets["auth_login"])
            observer_headers = {"Authorization": f"Bearer {observer_auth['accessToken']}"}

        health = await client.get(f"{api_prefix}/health")
        ready = await client.get(f"{api_prefix}/ready")
        processing = await client.get(f"{api_prefix}/ready/processing?strict=true")
        processing_body = processing.json()
        blocker = None
        if processing_body.get("jobProcessingReady") is not True:
            blocker = {
                "type": "live_environment" if processing_body.get("queueState") == "unavailable" else "configuration_or_runtime",
                "message": f"processing readiness is not green: workerState={processing_body.get('workerState')}, queueState={processing_body.get('queueState')}",
            }
        buckets["auth_login"] = {"values": [], "statuses": Counter(), "errors": []}
        buckets["auth_refresh"] = {"values": [], "statuses": Counter(), "errors": []}

        async def auth_worker(index: int) -> None:
            tenant = tenants[index % len(tenants)]
            try:
                auth = await login(client, api_prefix, tenant["email"], tenant["password"], buckets["auth_login"])
                await refresh(client, api_prefix, auth["refreshToken"], buckets["auth_refresh"])
            except httpx.HTTPError as exc:
                notes.append(f"auth burst #{index + 1} failed: {exc}")

        await asyncio.gather(*(auth_worker(index) for index in range(args.auth_requests)))

        for index in range(args.case_count):
            tenant = tenants[index % len(tenants)]["label"]
            try:
                case_id = await create_case(
                    client,
                    api_prefix,
                    headers_by_tenant[tenant],
                    buckets["case_create"],
                    title=f"[LOAD-OPS] {tenant} #{index + 1}",
                    description="Operational load rehearsal case",
                    address_label=f"{tenant}-addr-{index + 1}",
                )
                image_id = await upload_and_preview(
                    client,
                    api_prefix,
                    headers_by_tenant[tenant],
                    buckets["image_upload"],
                    buckets["image_preview"],
                    case_id=case_id,
                    filename=f"load-{tenant}-{index + 1:03d}.jpg",
                    image_bytes=image_bytes,
                )
                created_cases.append({"tenant": tenant, "caseId": case_id, "imageId": image_id, "marker": None})
            except httpx.HTTPError as exc:
                notes.append(f"crud burst #{index + 1} failed: {exc}")

        queue_jobs: list[dict[str, Any]] = []
        retry_jobs: list[dict[str, Any]] = []
        fairness_by_tenant: dict[str, Any] = {}
        sustained = {"status": "blocked" if blocker else "completed", "completedFlows": 0, "failedFlows": 0}
        if not blocker:
            for item in created_cases:
                payload = await enqueue_job(client, api_prefix, headers_by_tenant[item["tenant"]], buckets["analysis_enqueue"], case_id=item["caseId"])
                queue_jobs.append({"tenant": item["tenant"], "caseId": item["caseId"], "jobId": payload["jobId"], "provider": payload.get("provider")})
            samples.append(await sample_internal(client, observer_client, api_prefix, observer_headers))
            queued_records = list(queue_jobs)
            queue_results = await asyncio.gather(
                *(poll_terminal(client, api_prefix, headers_by_tenant[item["tenant"]], buckets["analysis_poll"], job_id=item["jobId"], timeout_seconds=args.poll_timeout, interval_seconds=args.poll_interval) for item in queued_records)
            )
            queue_jobs = [{**record, **result} for record, result in zip(queued_records, queue_results)]
            samples.append(await sample_internal(client, observer_client, api_prefix, observer_headers))

            for index in range(args.retry_probe_jobs):
                tenant = tenants[index % len(tenants)]["label"]
                case_id = await create_case(
                    client, api_prefix, headers_by_tenant[tenant], buckets["case_create"],
                    title=f"[LOAD-OPS][RETRY] {tenant} #{index + 1}",
                    description="Operational load rehearsal case [rehearsal:fail-until-attempt=2]",
                    address_label=f"{tenant}-retry-{index + 1}",
                )
                await upload_and_preview(client, api_prefix, headers_by_tenant[tenant], buckets["image_upload"], buckets["image_preview"], case_id=case_id, filename=f"retry-{tenant}-{index + 1}.jpg", image_bytes=image_bytes)
                payload = await enqueue_job(client, api_prefix, headers_by_tenant[tenant], buckets["analysis_enqueue"], case_id=case_id)
                retry_jobs.append({"tenant": tenant, "jobId": payload["jobId"], "provider": payload.get("provider")})
            retry_records = list(retry_jobs)
            retry_results = await asyncio.gather(
                *(poll_terminal(client, api_prefix, headers_by_tenant[item["tenant"]], buckets["analysis_poll"], job_id=item["jobId"], timeout_seconds=args.poll_timeout, interval_seconds=args.poll_interval) for item in retry_records)
            )
            retry_jobs = [{**record, **result} for record, result in zip(retry_records, retry_results)]

            grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
            for job in queue_jobs:
                grouped[str(job["tenant"])].append(job)
            fairness_by_tenant = {
                tenant: {
                    "jobs": len(items),
                    "completed": sum(1 for item in items if item.get("status") == "completed"),
                    "completedRatio": round(sum(1 for item in items if item.get("status") == "completed") / max(1, len(items)), 3),
                }
                for tenant, items in grouped.items()
            }

            for index in range(args.sustained_flows):
                tenant = tenants[index % len(tenants)]["label"]
                started = time.perf_counter()
                try:
                    case_id = await create_case(client, api_prefix, headers_by_tenant[tenant], buckets["case_create"], title=f"[LOAD-OPS][SUSTAINED] {tenant} #{index + 1}", description="Sustained load rehearsal case", address_label=f"{tenant}-sustained-{index + 1}")
                    await upload_and_preview(client, api_prefix, headers_by_tenant[tenant], buckets["image_upload"], buckets["image_preview"], case_id=case_id, filename=f"sustained-{tenant}-{index + 1}.jpg", image_bytes=image_bytes)
                    job = await enqueue_job(client, api_prefix, headers_by_tenant[tenant], buckets["analysis_enqueue"], case_id=case_id)
                    result = await poll_terminal(client, api_prefix, headers_by_tenant[tenant], buckets["analysis_poll"], job_id=job["jobId"], timeout_seconds=args.poll_timeout, interval_seconds=args.poll_interval)
                    flow_ms = (time.perf_counter() - started) * 1000.0
                    buckets["sustained_flow"]["values"].append(flow_ms)
                    buckets["sustained_flow"]["statuses"]["200" if result.get("status") == "completed" else "500"] += 1
                    if result.get("status") == "completed":
                        sustained["completedFlows"] += 1
                    else:
                        sustained["failedFlows"] += 1
                except Exception as exc:  # pragma: no cover
                    buckets["sustained_flow"]["errors"].append(str(exc))
                    sustained["failedFlows"] += 1

        result = {
            "startedAt": utc_now_iso(),
            "preflight": {
                "health": {"status": health.status_code, "body": health.json()},
                "ready": {"status": ready.status_code, "body": ready.json()},
                "processingReadyStrict": {"status": processing.status_code, "body": processing_body},
                "blocker": blocker,
            },
            "scenarios": {
                "authBurst": {
                    "login": summarize_latencies(**buckets["auth_login"]),
                    "refresh": summarize_latencies(**buckets["auth_refresh"]),
                },
                "crudPhotoBurst": {
                    "createdCases": len(created_cases),
                    "createCase": summarize_latencies(**buckets["case_create"]),
                    "upload": summarize_latencies(**buckets["image_upload"]),
                    "preview": summarize_latencies(**buckets["image_preview"]),
                },
                "queueThroughput": {
                    "status": "blocked" if blocker else "completed",
                    "jobs": queue_jobs,
                    "observerSamples": samples,
                },
                "retryStorm": {
                    "status": "blocked" if blocker else "completed",
                    "jobs": retry_jobs,
                },
                "tenantFairness": {
                    "status": "blocked" if blocker else ("skipped" if len(tenants) < 2 else "completed"),
                    "perTenant": fairness_by_tenant,
                },
                "sustainedLoad": sustained | {"flow": summarize_latencies(**buckets["sustained_flow"])},
            },
            "latencies": {key: summarize_latencies(**value) for key, value in buckets.items()},
            "notes": notes,
            "verdict": {
                "pilotReady": blocker is None and any(item.get("status") == "completed" for item in queue_jobs),
                "mediumScaleSafe": blocker is None and len(tenants) >= 2 and sustained["failedFlows"] == 0,
                "hundredKReady": False,
                "hundredKReasons": [
                    "current rehearsal remains single-node and does not prove 100k+ tenant posture",
                    "CPU/memory/DB/Redis node pressure is not exposed by backend HTTP diagnostics alone",
                ],
            },
        }
        rendered = json.dumps(result, indent=2)
        print(rendered)
        if args.json_out:
            output_path = Path(args.json_out)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(rendered + "\n", encoding="utf-8")
        return 0 if blocker is None else 1
    finally:
        await client.aclose()
        await observer_client.aclose()


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
