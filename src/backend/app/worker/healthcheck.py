from __future__ import annotations

import sys

from app.worker.heartbeat import local_worker_heartbeat_status, worker_local_health_path


def main() -> int:
    healthy, reason = local_worker_heartbeat_status(require_process=True)
    if healthy:
        return 0

    sys.stderr.write(
        f"worker heartbeat unhealthy ({reason}): {worker_local_health_path()}\n"
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
