from __future__ import annotations

import sys

from app.worker.heartbeat import local_worker_heartbeat_is_fresh, worker_local_health_path


def main() -> int:
    if local_worker_heartbeat_is_fresh():
        return 0

    sys.stderr.write(
        f"worker heartbeat stale or missing: {worker_local_health_path()}\n"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
