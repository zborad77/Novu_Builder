from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
TARGET_CHECK = "orchestration-release-gate"
DEFAULT_PROTECTED_BRANCH = "master"


def _git(*args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return completed.stdout.strip()


def _gh_api_json(path: str) -> dict:
    completed = subprocess.run(
        ["gh", "api", path],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        capture_output=True,
    )
    return json.loads(completed.stdout)


def _derive_repo_slug() -> str:
    remote_url = _git("remote", "get-url", "origin")
    if remote_url.endswith(".git"):
        remote_url = remote_url[:-4]
    if remote_url.startswith("https://github.com/"):
        return remote_url.removeprefix("https://github.com/")
    if remote_url.startswith("git@github.com:"):
        return remote_url.removeprefix("git@github.com:")
    raise ValueError(f"Unsupported origin remote URL: {remote_url}")


def _build_required_status_payload(protection: dict) -> dict:
    current = protection.get("required_status_checks") or {}
    strict = bool(current.get("strict", True))

    contexts = set(current.get("contexts") or [])
    contexts.add(TARGET_CHECK)

    raw_checks = current.get("checks") or []
    checks_by_context: dict[str, dict] = {}
    for check in raw_checks:
        context = check.get("context")
        if context:
            checks_by_context[context] = {
                "context": context,
                "app_id": check.get("app_id"),
            }
    checks_by_context.setdefault(TARGET_CHECK, {"context": TARGET_CHECK, "app_id": None})

    return {
        "strict": strict,
        "contexts": sorted(contexts),
        "checks": sorted(checks_by_context.values(), key=lambda item: item["context"]),
    }


def _run_apply(repo_slug: str, branch: str, payload: dict) -> None:
    endpoint = f"repos/{repo_slug}/branches/{branch}/protection/required_status_checks"
    subprocess.run(
        ["gh", "api", "--method", "PATCH", endpoint, "--input", "-"],
        cwd=REPO_ROOT,
        check=True,
        text=True,
        input=json.dumps(payload),
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Enable the orchestration-release-gate GitHub branch protection status check. "
            "Dry-run by default; pass --apply to perform the PATCH via gh api."
        )
    )
    parser.add_argument("--repo", default=None, help="GitHub repo slug owner/name (default: derive from origin)")
    parser.add_argument(
        "--branch",
        default=DEFAULT_PROTECTED_BRANCH,
        help="Protected branch to update (default: %(default)s)",
    )
    parser.add_argument(
        "--allow-non-default-branch",
        action="store_true",
        help=(
            "Permit updating a branch other than the default protected branch. "
            "Without this flag, the script fails closed for non-default branches."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Actually call gh api and patch required_status_checks. Default is dry-run only.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    repo_slug = args.repo or _derive_repo_slug()
    if args.branch != DEFAULT_PROTECTED_BRANCH and not args.allow_non_default_branch:
        print(
            f"Refusing to update branch {args.branch!r}. "
            f"This helper is fail-closed and defaults to {DEFAULT_PROTECTED_BRANCH!r}. "
            "Re-run with --allow-non-default-branch only if this is intentional.",
            file=sys.stderr,
        )
        return 1

    protection_endpoint = f"repos/{repo_slug}/branches/{args.branch}/protection"

    try:
        protection = _gh_api_json(protection_endpoint)
    except Exception as exc:
        print(f"Failed to load current branch protection for {repo_slug}:{args.branch}: {exc}", file=sys.stderr)
        return 1

    payload = _build_required_status_payload(protection)
    print(f"Repo: {repo_slug}")
    print(f"Branch: {args.branch}")
    print(f"Target check: {TARGET_CHECK}")
    print("Required status checks payload:")
    print(json.dumps(payload, indent=2))

    if not args.apply:
        print("\nDry run only. Re-run with --apply to update GitHub branch protection.")
        return 0

    try:
        _run_apply(repo_slug, args.branch, payload)
    except Exception as exc:
        print(f"Failed to patch required status checks: {exc}", file=sys.stderr)
        return 1

    print("\nBranch protection updated successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
