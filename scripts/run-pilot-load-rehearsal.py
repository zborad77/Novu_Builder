"""
Small, repeatable pilot load rehearsal for NOVU Builder.

Scope:
  1. Auth burst            - concurrent login + refresh
  2. Project/photo burst   - create case, upload image(s), preview redirect
  3. Queue orchestration   - enqueue analysis jobs, poll states,
                             and sample queue/worker health
  4. End-to-end mini flow  - smaller mixed create/upload/analyze flow
"""

from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from io import BytesIO
import json
import os
from pathlib import Path
import statistics
import sys
import time
from typing import Any

import httpx

try:
    from PIL import Image
except ImportError:  # pragma: no cover - requirements include Pillow
    Image = None


DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_EMAIL = os.getenv("NOVU_TEST_EMAIL", "").strip() or "demo@novu.local"
DEFAULT_PASSWORD = os.getenv("NOVU_TEST_PASSWORD", "").strip() or "demo1234"
DEFAULT_OBSERVER_EMAIL = os.getenv("NOVU_OBSERVER_EMAIL", "").strip()
DEFAULT_OBSERVER_PASSWORD = os.getenv("NOVU_OBSERVER_PASSWORD", "").strip()
DEFAULT_ACCESS_TOKEN = os.getenv("NOVU_TEST_ACCESS_TOKEN", "").strip()
DEFAULT_OBSERVER_ACCESS_TOKEN = os.getenv("NOVU_OBSERVER_ACCESS_TOKEN", "").strip()
DEFAULT_TIMEOUT = 15.0
DEFAULT_SAMPLE_INTERVAL = 2.0
CASE_TITLE_PREFIX = "[LOAD-REHEARSAL]"
TERMINAL_JOB_STATUSES = {"completed", "failed", "canceled", "cancelled", "error"}


def utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def percentile(values: list[float], quantile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * quantile)))
    return float(ordered[index])


def safe_mean(values: list[float]) -> float:
    return float(statistics.mean(values)) if values else 0.0


def clamp_non_negative(value: float) -> float:
    return max(0.0, float(value))


def generate_jpeg_bytes(*, width: int = 1600, height: int = 900) -> bytes:
    if Image is None:
        raise RuntimeError("Pillow is required for the rehearsal image payload.")
    image = Image.new("RGB", (width, height), color=(214, 226, 238))
    buffer = BytesIO()
    image.save(buffer, format="JPEG", quality=88)
    return buffer.getvalue()


@dataclass
class LatencyBucket:
    name: str
    durations_ms: list[float] = field(default_factory=list)
    status_codes: Counter[str] = field(default_factory=Counter)
    errors: list[str] = field(default_factory=list)

    def record(self, *, duration_ms: float, status_code: int, error: str | None = None) -> None:
        self.durations_ms.append(clamp_non_negative(duration_ms))
        self.status_codes[str(status_code)] += 1
        if error:
            self.errors.append(error)

    @property
    def count(self) -> int:
        return len(self.durations_ms)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def error_rate(self) -> float:
        return (self.error_count / self.count) if self.count else 0.0

    def summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "count": self.count,
            "errorCount": self.error_count,
            "errorRate": round(self.error_rate, 4),
            "avgMs": round(safe_mean(self.durations_ms), 1),
            "p50Ms": round(percentile(self.durations_ms, 0.50), 1),
            "p95Ms": round(percentile(self.durations_ms, 0.95), 1),
            "maxMs": round(max(self.durations_ms), 1) if self.durations_ms else 0.0,
            "statusCodes": dict(sorted(self.status_codes.items())),
            "sampleErrors": self.errors[:5],
        }


@dataclass
class CreatedCase:
    case_id: str
    image_id: str | None = None


@dataclass
class JobOutcome:
    case_id: str
    job_id: str
    terminal_status: str
    finished: bool
    enqueue_ms: float
    total_ms: float
    provider: str | None
    retried_from_job_id: str | None = None


@dataclass
class ObserverSample:
    observed_at: str
    processing_ready_status: str
    queue_state: str | None
    worker_state: str | None
    api_ready: bool | None = None
    job_processing_ready: bool | None = None
    jobs_running: int | None = None
    jobs_queued: int | None = None
    queue_length: int | None = None
    processing_jobs: int | None = None
    max_running_age_seconds: float | None = None


@dataclass
class SuccessCriteria:
    auth_p95_ms_max: float = 1000.0
    refresh_p95_ms_max: float = 1000.0
    create_case_p95_ms_max: float = 1200.0
    upload_p95_ms_max: float = 2200.0
    preview_p95_ms_max: float = 750.0
    enqueue_p95_ms_max: float = 1200.0
    http_error_rate_max: float = 0.02
    terminal_completion_ratio_min: float = 0.95
    completed_ratio_min: float = 0.90


class PilotLoadRehearsal:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.api_prefix = args.base_url.rstrip("/") + "/api/v1"
        self.auth_client = httpx.AsyncClient(timeout=args.timeout)
        self.observer_client = httpx.AsyncClient(timeout=args.timeout)
        self.manager_headers: dict[str, str] = {}
        self.observer_headers: dict[str, str] = {}
        self.created_cases: list[CreatedCase] = []
        self.buckets: dict[str, LatencyBucket] = {
            name: LatencyBucket(name)
            for name in (
                "auth.login",
                "auth.refresh",
                "case.create",
                "image.upload",
                "image.preview",
                "analysis.enqueue",
                "analysis.cancel",
                "analysis.retry",
                "cleanup.archive",
                "e2e.total",
            )
        }
        self.observer_samples: list[ObserverSample] = []
        self.job_outcomes: list[JobOutcome] = []
        self.environment_blockers: list[str] = []
        self.notes: list[str] = []
        self.criteria = SuccessCriteria()

    async def close(self) -> None:
        await self.auth_client.aclose()
        await self.observer_client.aclose()

    async def authenticate(self) -> None:
        if self.args.access_token:
            self.manager_headers = {"Authorization": f"Bearer {self.args.access_token}"}
        else:
            manager_login = await self._login(
                client=self.auth_client,
                email=self.args.email,
                password=self.args.password,
                bucket_name="auth.login",
            )
            self.manager_headers = {"Authorization": f"Bearer {manager_login['accessToken']}"}

        if self.args.observer_access_token:
            self.observer_headers = {"Authorization": f"Bearer {self.args.observer_access_token}"}
        elif self.args.observer_email and self.args.observer_password:
            observer_login = await self._login(
                client=self.auth_client,
                email=self.args.observer_email,
                password=self.args.observer_password,
                bucket_name="auth.login",
            )
            self.observer_headers = {"Authorization": f"Bearer {observer_login['accessToken']}"}

    async def _login(
        self,
        *,
        client: httpx.AsyncClient,
        email: str,
        password: str,
        bucket_name: str,
    ) -> dict[str, Any]:
        started = time.perf_counter()
        response = await client.post(
            f"{self.api_prefix}/auth/login",
            json={"email": email, "password": password},
        )
        duration_ms = (time.perf_counter() - started) * 1000.0
        error = None if response.status_code == 200 else response.text[:200]
        self.buckets[bucket_name].record(
            duration_ms=duration_ms,
            status_code=response.status_code,
            error=error,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or "accessToken" not in payload:
            raise RuntimeError("Login response does not contain accessToken.")
        return payload

    async def _refresh(self, refresh_token: str) -> dict[str, Any]:
        started = time.perf_counter()
        response = await self.auth_client.post(
            f"{self.api_prefix}/auth/refresh",
            json={"refreshToken": refresh_token},
        )
        duration_ms = (time.perf_counter() - started) * 1000.0
        error = None if response.status_code == 200 else response.text[:200]
        self.buckets["auth.refresh"].record(
            duration_ms=duration_ms,
            status_code=response.status_code,
            error=error,
        )
        response.raise_for_status()
        return response.json()

    async def run(self) -> dict[str, Any]:
        await self.authenticate()

        auth_result = await self.run_auth_phase()
        project_result = await self.run_project_photo_phase()
        analysis_result = await self.run_analysis_phase()
        e2e_result = await self.run_end_to_end_phase(skip_due_to_blocker=not analysis_result["queueReady"])
        cleanup_result = await self.cleanup_cases()
        criteria_result = self.evaluate_success_criteria()
        verdict = self.build_verdict(criteria_result, analysis_result)

        return {
            "startedAt": utc_now_iso(),
            "baseUrl": self.args.base_url,
            "authUser": self.args.email,
            "observerUser": self.args.observer_email or None,
            "phases": {
                "auth": auth_result,
                "projectPhoto": project_result,
                "analysis": analysis_result,
                "endToEnd": e2e_result,
                "cleanup": cleanup_result,
            },
            "latencies": {name: bucket.summary() for name, bucket in self.buckets.items()},
            "observer": {
                "sampleCount": len(self.observer_samples),
                "samples": [asdict(sample) for sample in self.observer_samples[:20]],
                "maxQueueLength": max((sample.queue_length or 0) for sample in self.observer_samples) if self.observer_samples else 0,
                "maxJobsQueued": max((sample.jobs_queued or 0) for sample in self.observer_samples) if self.observer_samples else 0,
                "maxJobsRunning": max((sample.jobs_running or 0) for sample in self.observer_samples) if self.observer_samples else 0,
            },
            "jobOutcomes": [asdict(outcome) for outcome in self.job_outcomes],
            "successCriteria": criteria_result,
            "environmentBlockers": self.environment_blockers,
            "notes": self.notes,
            "verdict": verdict,
        }

    async def run_auth_phase(self) -> dict[str, Any]:
        print("\n== Phase 1: auth burst ==", flush=True)
        sem = asyncio.Semaphore(self.args.auth_concurrency)
        refresh_success = 0

        async def _one_login(index: int) -> None:
            nonlocal refresh_success
            async with sem:
                try:
                    login_payload = await self._login(
                        client=self.auth_client,
                        email=self.args.email,
                        password=self.args.password,
                        bucket_name="auth.login",
                    )
                    refresh_payload = await self._refresh(login_payload["refreshToken"])
                    if refresh_payload.get("accessToken"):
                        refresh_success += 1
                except httpx.HTTPError as exc:
                    self.notes.append(f"Auth burst request #{index + 1} failed: {exc}")

        await asyncio.gather(*[_one_login(index) for index in range(self.args.auth_requests)], return_exceptions=True)
        summary = {
            "requests": self.args.auth_requests,
            "refreshesSucceeded": refresh_success,
            "login": self.buckets["auth.login"].summary(),
            "refresh": self.buckets["auth.refresh"].summary(),
        }
        print(json.dumps(summary, indent=2), flush=True)
        return summary

    async def run_project_photo_phase(self) -> dict[str, Any]:
        print("\n== Phase 2: project/photo burst ==", flush=True)
        sem = asyncio.Semaphore(self.args.project_concurrency)
        image_bytes = generate_jpeg_bytes()

        async def _create_one(index: int) -> CreatedCase:
            async with sem:
                try:
                    case_id = await self._create_case(index=index)
                    image_id = await self._upload_and_preview(case_id=case_id, index=index, image_bytes=image_bytes)
                    created = CreatedCase(case_id=case_id, image_id=image_id)
                    self.created_cases.append(created)
                    return created
                except httpx.HTTPError as exc:
                    self.notes.append(f"Project/photo worker #{index + 1} failed: {exc}")
                    return CreatedCase(case_id="failed")

        await asyncio.gather(*[_create_one(index) for index in range(self.args.project_count)], return_exceptions=True)
        summary = {
            "createdCases": len(self.created_cases),
            "createCase": self.buckets["case.create"].summary(),
            "upload": self.buckets["image.upload"].summary(),
            "preview": self.buckets["image.preview"].summary(),
        }
        print(json.dumps(summary, indent=2), flush=True)
        return summary

    async def _create_case(self, *, index: int) -> str:
        title = f"{CASE_TITLE_PREFIX} {utc_now_iso()} #{index + 1}"
        payload = {
            "title": title,
            "description": "Pilot load rehearsal case",
            "propertyType": "house",
            "repairScope": "facade_repair",
            "addressLabel": f"Load rehearsal {index + 1}",
        }
        started = time.perf_counter()
        response = await self.auth_client.post(
            f"{self.api_prefix}/cases",
            json=payload,
            headers=self.manager_headers,
        )
        duration_ms = (time.perf_counter() - started) * 1000.0
        error = None if response.status_code == 201 else response.text[:200]
        self.buckets["case.create"].record(
            duration_ms=duration_ms,
            status_code=response.status_code,
            error=error,
        )
        response.raise_for_status()
        body = response.json()
        case_id = body.get("id")
        if not isinstance(case_id, str):
            raise RuntimeError("Case create response does not contain id.")
        return case_id

    async def _upload_and_preview(self, *, case_id: str, index: int, image_bytes: bytes) -> str | None:
        image_id: str | None = None
        for photo_index in range(self.args.photos_per_case):
            filename = f"pilot-{index + 1:03d}-{photo_index + 1:02d}.jpg"
            files = {"files": (filename, image_bytes, "image/jpeg")}
            data = {"isPrimary": "true" if photo_index == 0 else "false"}
            started = time.perf_counter()
            response = await self.auth_client.post(
                f"{self.api_prefix}/cases/{case_id}/images",
                headers=self.manager_headers,
                files=files,
                data=data,
            )
            duration_ms = (time.perf_counter() - started) * 1000.0
            error = None if response.status_code == 201 else response.text[:200]
            self.buckets["image.upload"].record(
                duration_ms=duration_ms,
                status_code=response.status_code,
                error=error,
            )
            response.raise_for_status()
            payload = response.json()
            uploaded = payload.get("uploaded") or []
            if photo_index == 0 and uploaded:
                first = uploaded[0]
                if isinstance(first, dict):
                    image_id = first.get("id")

        if image_id:
            started = time.perf_counter()
            response = await self.auth_client.get(
                f"{self.api_prefix}/images/{image_id}/preview",
                headers=self.manager_headers,
                follow_redirects=False,
            )
            duration_ms = (time.perf_counter() - started) * 1000.0
            error = None if response.status_code in (302, 307) else response.text[:200]
            self.buckets["image.preview"].record(
                duration_ms=duration_ms,
                status_code=response.status_code,
                error=error,
            )
            if response.status_code not in (302, 307):
                response.raise_for_status()
        return image_id

    async def run_analysis_phase(self) -> dict[str, Any]:
        print("\n== Phase 3: queue/worker orchestration ==", flush=True)
        if len(self.created_cases) < self.args.analysis_jobs:
            missing = self.args.analysis_jobs - len(self.created_cases)
            self.notes.append(
                f"Creating {missing} additional cases so queue load uses distinct projects."
            )
            image_bytes = generate_jpeg_bytes()
            for index in range(missing):
                try:
                    case_id = await self._create_case(index=len(self.created_cases) + index)
                    image_id = await self._upload_and_preview(
                        case_id=case_id,
                        index=len(self.created_cases) + index,
                        image_bytes=image_bytes,
                    )
                    self.created_cases.append(CreatedCase(case_id=case_id, image_id=image_id))
                except httpx.HTTPError as exc:
                    self.notes.append(f"Additional analysis case creation failed: {exc}")

        sampler_stop = asyncio.Event()
        sampler_task = asyncio.create_task(self._sample_observability(sampler_stop))
        try:
            queue_ready = await self._processing_ready_strict()
            if not queue_ready:
                self.environment_blockers.append(
                    "Job processing is not ready before the load phase. "
                    "Typical cause: Redis/worker missing or degraded."
                )

            selected_cases = [created for created in self.created_cases if created.case_id != "failed"][
                : self.args.analysis_jobs
            ]
            sem = asyncio.Semaphore(self.args.analysis_concurrency)
            enqueued: list[tuple[str, str, float, str | None]] = []

            async def _enqueue(created: CreatedCase) -> None:
                async with sem:
                    try:
                        started = time.perf_counter()
                        response = await self.auth_client.post(
                            f"{self.api_prefix}/cases/{created.case_id}/analysis-jobs",
                            headers=self.manager_headers,
                        )
                        duration_ms = (time.perf_counter() - started) * 1000.0
                        error = None if response.status_code in (200, 202) else response.text[:200]
                        self.buckets["analysis.enqueue"].record(
                            duration_ms=duration_ms,
                            status_code=response.status_code,
                            error=error,
                        )
                        response.raise_for_status()
                        payload = response.json()
                        enqueued.append(
                            (
                                created.case_id,
                                str(payload["jobId"]),
                                duration_ms,
                                payload.get("provider"),
                            )
                        )
                    except httpx.HTTPError as exc:
                        self.notes.append(f"Analysis enqueue failed for case {created.case_id}: {exc}")

            enqueue_started = time.perf_counter()
            await asyncio.gather(*[_enqueue(created) for created in selected_cases], return_exceptions=True)

            retried: dict[str, str] = {}
            for case_id, job_id, _enqueue_ms, provider in enqueued[: self.args.retry_probe_jobs]:
                canceled = await self._cancel_job(job_id)
                if canceled:
                    retried_job_id = await self._retry_job(job_id)
                    if retried_job_id:
                        retried[job_id] = retried_job_id
                        self.notes.append(
                            f"Retry probe requeued canceled job {job_id} as {retried_job_id}."
                        )
                    else:
                        self.notes.append(f"Retry probe could not requeue job {job_id}.")
                else:
                    self.notes.append(f"Retry probe could not cancel job {job_id}; likely already running.")

            poll_results = await asyncio.gather(
                *[
                    self._poll_job_terminal_state(retried.get(original_job_id, original_job_id))
                    for _, original_job_id, _, _ in enqueued
                ]
            )

            terminal_jobs = 0
            completed_jobs = 0
            failed_jobs = 0
            still_active_jobs = 0

            for (case_id, original_job_id, enqueue_ms, provider), (terminal_status, finished, total_ms) in zip(
                enqueued,
                poll_results,
            ):
                poll_job_id = retried.get(original_job_id, original_job_id)
                if finished:
                    terminal_jobs += 1
                else:
                    still_active_jobs += 1
                if terminal_status == "completed":
                    completed_jobs += 1
                elif terminal_status == "failed":
                    failed_jobs += 1
                self.job_outcomes.append(
                    JobOutcome(
                        case_id=case_id,
                        job_id=poll_job_id,
                        terminal_status=terminal_status,
                        finished=finished,
                        enqueue_ms=round(enqueue_ms, 1),
                        total_ms=round(total_ms, 1),
                        provider=provider,
                        retried_from_job_id=original_job_id if poll_job_id != original_job_id else None,
                    )
                )

            phase_elapsed = time.perf_counter() - enqueue_started
            throughput = completed_jobs / phase_elapsed if phase_elapsed > 0 else 0.0
            if failed_jobs == 0:
                self.notes.append(
                    "No naturally failed analysis jobs were observed in this rehearsal. "
                    "Retry was exercised via the cancel/retry probe, not provider failure."
                )

            summary = {
                "requestedJobs": self.args.analysis_jobs,
                "queueReady": queue_ready,
                "terminalJobs": terminal_jobs,
                "completedJobs": completed_jobs,
                "failedJobs": failed_jobs,
                "activeAfterTimeout": still_active_jobs,
                "throughputJobsPerSec": round(throughput, 2),
                "enqueue": self.buckets["analysis.enqueue"].summary(),
                "cancel": self.buckets["analysis.cancel"].summary(),
                "retry": self.buckets["analysis.retry"].summary(),
            }
            print(json.dumps(summary, indent=2), flush=True)
            return summary
        finally:
            sampler_stop.set()
            await sampler_task

    async def _processing_ready_strict(self) -> bool:
        response = await self.auth_client.get(f"{self.api_prefix}/ready/processing?strict=true")
        if response.status_code not in (200, 503):
            return False
        payload = response.json()
        return bool(payload.get("jobProcessingReady"))

    async def _cancel_job(self, job_id: str) -> bool:
        started = time.perf_counter()
        response = await self.auth_client.post(
            f"{self.api_prefix}/analysis-jobs/{job_id}/cancel",
            headers=self.manager_headers,
        )
        duration_ms = (time.perf_counter() - started) * 1000.0
        error = None if response.status_code == 200 else response.text[:200]
        self.buckets["analysis.cancel"].record(
            duration_ms=duration_ms,
            status_code=response.status_code,
            error=error,
        )
        return response.status_code == 200

    async def _retry_job(self, job_id: str) -> str | None:
        started = time.perf_counter()
        response = await self.auth_client.post(
            f"{self.api_prefix}/analysis-jobs/{job_id}/retry",
            headers=self.manager_headers,
        )
        duration_ms = (time.perf_counter() - started) * 1000.0
        error = None if response.status_code in (200, 202) else response.text[:200]
        self.buckets["analysis.retry"].record(
            duration_ms=duration_ms,
            status_code=response.status_code,
            error=error,
        )
        if response.status_code not in (200, 202):
            return None
        payload = response.json()
        job_id_value = payload.get("jobId")
        return str(job_id_value) if isinstance(job_id_value, str) else None

    async def _poll_job_terminal_state(self, job_id: str) -> tuple[str, bool, float]:
        started = time.perf_counter()
        deadline = started + self.args.poll_timeout
        last_status = "unknown"
        while time.perf_counter() < deadline:
            response = await self.auth_client.get(
                f"{self.api_prefix}/analysis-jobs/{job_id}",
                headers=self.manager_headers,
            )
            if response.status_code != 200:
                await asyncio.sleep(self.args.poll_interval)
                continue
            payload = response.json()
            last_status = str(payload.get("status") or "unknown")
            if last_status in TERMINAL_JOB_STATUSES:
                total_ms = (time.perf_counter() - started) * 1000.0
                return last_status, True, total_ms
            await asyncio.sleep(self.args.poll_interval)
        total_ms = (time.perf_counter() - started) * 1000.0
        return last_status, False, total_ms

    async def _sample_observability(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            sample = ObserverSample(
                observed_at=utc_now_iso(),
                processing_ready_status="unknown",
                queue_state=None,
                worker_state=None,
            )
            try:
                ready_response = await self.auth_client.get(f"{self.api_prefix}/ready/processing?strict=true")
                ready_payload = ready_response.json()
                sample.processing_ready_status = str(ready_payload.get("status") or "unknown")
                sample.queue_state = ready_payload.get("queueState")
                sample.worker_state = ready_payload.get("workerState")
                sample.api_ready = ready_payload.get("apiReady")
                sample.job_processing_ready = ready_payload.get("jobProcessingReady")
            except Exception as exc:  # pragma: no cover - diagnostic path
                sample.processing_ready_status = f"error:{type(exc).__name__}"

            if self.observer_headers:
                try:
                    internal_response = await self.observer_client.get(
                        f"{self.api_prefix}/health/internal",
                        headers=self.observer_headers,
                    )
                    if internal_response.status_code == 200:
                        payload = internal_response.json()
                        jobs = payload.get("jobs") or {}
                        sample.jobs_running = jobs.get("running")
                        sample.jobs_queued = jobs.get("queued")
                        sample.queue_length = jobs.get("queueLength")
                        sample.processing_jobs = jobs.get("processing")
                        sample.max_running_age_seconds = jobs.get("maxRunningAgeSeconds")
                        sample.queue_state = ((payload.get("queue") or {}).get("state")) or sample.queue_state
                        sample.worker_state = ((payload.get("worker") or {}).get("state")) or sample.worker_state
                except Exception:
                    pass

            self.observer_samples.append(sample)
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self.args.sample_interval)
            except asyncio.TimeoutError:
                continue

    async def run_end_to_end_phase(self, *, skip_due_to_blocker: bool) -> dict[str, Any]:
        print("\n== Phase 4: end-to-end mini flow ==", flush=True)
        if skip_due_to_blocker:
            summary = {
                "skipped": True,
                "reason": "Queue/worker processing is not ready, so a mixed end-to-end flow would only repeat the same blocker.",
            }
            print(json.dumps(summary, indent=2), flush=True)
            return summary

        sem = asyncio.Semaphore(self.args.e2e_concurrency)
        image_bytes = generate_jpeg_bytes(width=1400, height=900)
        completed = 0

        async def _one_flow(index: int) -> None:
            nonlocal completed
            async with sem:
                started = time.perf_counter()
                try:
                    case_id = await self._create_case(index=10_000 + index)
                    self.created_cases.append(CreatedCase(case_id=case_id))
                    await self._upload_and_preview(case_id=case_id, index=10_000 + index, image_bytes=image_bytes)
                    response = await self.auth_client.post(
                        f"{self.api_prefix}/cases/{case_id}/analysis-jobs",
                        headers=self.manager_headers,
                    )
                    response.raise_for_status()
                    job_id = response.json()["jobId"]
                    terminal_status, finished, _total_ms = await self._poll_job_terminal_state(job_id)
                    duration_ms = (time.perf_counter() - started) * 1000.0
                    error = None if (finished and terminal_status == "completed") else terminal_status
                    self.buckets["e2e.total"].record(
                        duration_ms=duration_ms,
                        status_code=200 if error is None else 500,
                        error=error,
                    )
                    if error is None:
                        completed += 1
                except httpx.HTTPError as exc:
                    duration_ms = (time.perf_counter() - started) * 1000.0
                    self.buckets["e2e.total"].record(
                        duration_ms=duration_ms,
                        status_code=500,
                        error=str(exc),
                    )
                    self.notes.append(f"End-to-end flow #{index + 1} failed: {exc}")

        await asyncio.gather(*[_one_flow(index) for index in range(self.args.e2e_flows)], return_exceptions=True)
        summary = {
            "skipped": False,
            "flows": self.args.e2e_flows,
            "completedFlows": completed,
            "total": self.buckets["e2e.total"].summary(),
        }
        print(json.dumps(summary, indent=2), flush=True)
        return summary

    async def cleanup_cases(self) -> dict[str, Any]:
        print("\n== Cleanup ==", flush=True)
        archived = 0
        failed = 0
        for created in self.created_cases:
            started = time.perf_counter()
            response = await self.auth_client.post(
                f"{self.api_prefix}/cases/{created.case_id}/archive",
                headers=self.manager_headers,
            )
            duration_ms = (time.perf_counter() - started) * 1000.0
            error = None if response.status_code == 200 else response.text[:200]
            self.buckets["cleanup.archive"].record(
                duration_ms=duration_ms,
                status_code=response.status_code,
                error=error,
            )
            if response.status_code == 200:
                archived += 1
            else:
                failed += 1
        summary = {
            "attempted": len(self.created_cases),
            "archived": archived,
            "failed": failed,
            "archive": self.buckets["cleanup.archive"].summary(),
        }
        print(json.dumps(summary, indent=2), flush=True)
        return summary

    def evaluate_success_criteria(self) -> dict[str, Any]:
        analysis_requested = self.args.analysis_jobs
        terminal_jobs = sum(1 for outcome in self.job_outcomes if outcome.finished)
        completed_jobs = sum(1 for outcome in self.job_outcomes if outcome.terminal_status == "completed")
        checks = {
            "authLoginP95": self.buckets["auth.login"].summary()["p95Ms"] <= self.criteria.auth_p95_ms_max,
            "authRefreshP95": self.buckets["auth.refresh"].summary()["p95Ms"] <= self.criteria.refresh_p95_ms_max,
            "createCaseP95": self.buckets["case.create"].summary()["p95Ms"] <= self.criteria.create_case_p95_ms_max,
            "uploadP95": self.buckets["image.upload"].summary()["p95Ms"] <= self.criteria.upload_p95_ms_max,
            "previewP95": self.buckets["image.preview"].summary()["p95Ms"] <= self.criteria.preview_p95_ms_max,
            "enqueueP95": self.buckets["analysis.enqueue"].summary()["p95Ms"] <= self.criteria.enqueue_p95_ms_max,
            "httpErrorRate": all(
                bucket.error_rate <= self.criteria.http_error_rate_max
                for bucket in (
                    self.buckets["auth.login"],
                    self.buckets["auth.refresh"],
                    self.buckets["case.create"],
                    self.buckets["image.upload"],
                    self.buckets["image.preview"],
                    self.buckets["analysis.enqueue"],
                )
            ),
            "terminalCompletionRatio": (
                (terminal_jobs / analysis_requested) if analysis_requested else 0.0
            ) >= self.criteria.terminal_completion_ratio_min,
            "completedRatio": (
                (completed_jobs / analysis_requested) if analysis_requested else 0.0
            ) >= self.criteria.completed_ratio_min,
        }
        return {
            "checks": checks,
            "terminalCompletionRatio": round((terminal_jobs / analysis_requested) if analysis_requested else 0.0, 3),
            "completedRatio": round((completed_jobs / analysis_requested) if analysis_requested else 0.0, 3),
            "passed": all(checks.values()),
        }

    def build_verdict(self, criteria_result: dict[str, Any], analysis_result: dict[str, Any]) -> dict[str, Any]:
        if self.environment_blockers:
            status = "blocked_by_environment"
            summary = (
                "API/load script is usable, but queue/worker rehearsal is blocked by missing "
                "runtime dependencies or degraded processing readiness."
            )
        elif criteria_result["passed"]:
            status = "pilot_ready"
            summary = "Pilot-sized load rehearsal passed the configured success criteria."
        elif analysis_result.get("completedJobs", 0) >= max(1, round(self.args.analysis_jobs * 0.8)):
            status = "pilot_possible_with_watchouts"
            summary = "Load rehearsal mostly held, but one or more criteria missed and need watching."
        else:
            status = "not_pilot_ready"
            summary = "Pilot rehearsal showed material instability or poor queue/job completion."
        return {
            "status": status,
            "summary": summary,
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Small pilot load rehearsal for NOVU Builder.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Base URL, for example http://localhost:8000")
    parser.add_argument("--email", default=DEFAULT_EMAIL, help="Manager user email.")
    parser.add_argument("--password", default=DEFAULT_PASSWORD, help="Manager user password.")
    parser.add_argument("--access-token", default=DEFAULT_ACCESS_TOKEN, help="Optional pre-issued manager Bearer token for bootstrap requests.")
    parser.add_argument("--observer-email", default=DEFAULT_OBSERVER_EMAIL, help="Optional observer/superadmin email for /health/internal.")
    parser.add_argument("--observer-password", default=DEFAULT_OBSERVER_PASSWORD, help="Optional observer/superadmin password.")
    parser.add_argument("--observer-access-token", default=DEFAULT_OBSERVER_ACCESS_TOKEN, help="Optional pre-issued observer Bearer token for bootstrap requests.")
    parser.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT, help="Per-request timeout in seconds.")
    parser.add_argument("--sample-interval", type=float, default=DEFAULT_SAMPLE_INTERVAL, help="Observability sampling interval in seconds.")
    parser.add_argument("--auth-requests", type=int, default=20, help="Number of login+refresh pairs.")
    parser.add_argument("--auth-concurrency", type=int, default=6, help="Parallel auth requests.")
    parser.add_argument("--project-count", type=int, default=24, help="How many distinct cases to create for the rehearsal.")
    parser.add_argument("--photos-per-case", type=int, default=1, help="How many photos to upload per created case.")
    parser.add_argument("--project-concurrency", type=int, default=4, help="Parallel project/photo workers.")
    parser.add_argument("--analysis-jobs", type=int, default=24, help="How many analysis jobs to enqueue.")
    parser.add_argument("--analysis-concurrency", type=int, default=8, help="Parallel analysis enqueue calls.")
    parser.add_argument("--retry-probe-jobs", type=int, default=2, help="How many enqueue jobs should go through the cancel/retry probe.")
    parser.add_argument("--poll-timeout", type=float, default=90.0, help="How long to wait for job terminal state.")
    parser.add_argument("--poll-interval", type=float, default=2.0, help="Job polling interval in seconds.")
    parser.add_argument("--e2e-flows", type=int, default=6, help="Number of mini end-to-end flows.")
    parser.add_argument("--e2e-concurrency", type=int, default=3, help="Parallel end-to-end flows.")
    parser.add_argument("--json-out", default="", help="Optional path to write the JSON summary.")
    return parser.parse_args()


async def async_main() -> int:
    args = parse_args()
    rehearsal = PilotLoadRehearsal(args)
    try:
        result = await rehearsal.run()
    finally:
        await rehearsal.close()

    rendered = json.dumps(result, indent=2)
    print("\n== Final summary ==", flush=True)
    print(rendered, flush=True)

    if args.json_out:
        output_path = Path(args.json_out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(rendered + "\n", encoding="utf-8")
        print(f"\nJSON summary written to {output_path}", flush=True)

    return 0 if result["verdict"]["status"] in {"pilot_ready", "pilot_possible_with_watchouts"} else 1


def main() -> None:
    try:
        raise SystemExit(asyncio.run(async_main()))
    except KeyboardInterrupt:
        raise SystemExit(130)


if __name__ == "__main__":
    main()
