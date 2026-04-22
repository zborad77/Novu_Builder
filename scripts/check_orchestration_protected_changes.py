from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
PROTECTED_MANIFEST = REPO_ROOT / ".github" / "orchestration_protected_files.txt"
REQUIRED_PR_BODY_MARKERS = (
    "`python scripts/verify_orchestration_release_gate.py` is green",
    "command / rule / before_commit / after_commit / event / invariant impact reviewed",
)


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def _load_protected_files() -> set[str]:
    lines = PROTECTED_MANIFEST.read_text(encoding="utf-8").splitlines()
    return {
        line.strip().replace("\\", "/")
        for line in lines
        if line.strip() and not line.strip().startswith("#")
    }


def _load_github_event() -> dict:
    event_path = os.environ.get("GITHUB_EVENT_PATH")
    if not event_path:
        return {}
    try:
        return json.loads(Path(event_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _resolve_base_ref(explicit_base_ref: str | None) -> str:
    if explicit_base_ref:
        return explicit_base_ref

    event = _load_github_event()
    pull_request = event.get("pull_request") or {}
    if pull_request.get("base", {}).get("sha"):
        return pull_request["base"]["sha"]

    if event.get("before") and event["before"] != "0" * 40:
        return event["before"]

    github_base_ref = os.environ.get("GITHUB_BASE_REF")
    if github_base_ref:
        remote_ref = f"origin/{github_base_ref}"
        try:
            return _git("merge-base", "HEAD", remote_ref)
        except subprocess.CalledProcessError:
            return github_base_ref

    for fallback in ("origin/master", "master", "HEAD~1"):
        try:
            return _git("merge-base", "HEAD", fallback)
        except subprocess.CalledProcessError:
            continue
    return "HEAD~1"


def _changed_files(base_ref: str, head_ref: str) -> list[str]:
    diff_output = _git("diff", "--name-only", f"{base_ref}...{head_ref}")
    if not diff_output:
        return []
    return [line.strip().replace("\\", "/") for line in diff_output.splitlines() if line.strip()]


def _checked_in_pr_body(body: str, marker: str) -> bool:
    normalized_body = body.lower()
    normalized_marker = marker.lower()
    return f"- [x] {normalized_marker}" in normalized_body or f"- [X] {marker}" in body


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Detect changes to orchestration protected files and require the PR "
            "checklist when those files are touched."
        )
    )
    parser.add_argument("--base-ref", default=None)
    parser.add_argument("--head-ref", default="HEAD")
    args = parser.parse_args()

    protected_files = _load_protected_files()
    base_ref = _resolve_base_ref(args.base_ref)
    changed_files = _changed_files(base_ref, args.head_ref)
    changed_protected = [path for path in changed_files if path in protected_files]

    if not changed_protected:
        print("No protected orchestration files changed.")
        return 0

    print("Protected orchestration files changed:")
    for path in changed_protected:
        print(f" - {path}")

    event = _load_github_event()
    pull_request = event.get("pull_request") or {}
    body = pull_request.get("body") or ""
    if not body:
        print("No pull request body detected; skipping checklist enforcement outside PR context.")
        return 0

    missing_markers = [marker for marker in REQUIRED_PR_BODY_MARKERS if not _checked_in_pr_body(body, marker)]
    if missing_markers:
        print("Protected orchestration files require the PR orchestration checklist.")
        for marker in missing_markers:
            print(f"Missing checked item: {marker}")
        return 1

    print("Protected-file PR checklist is present.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
