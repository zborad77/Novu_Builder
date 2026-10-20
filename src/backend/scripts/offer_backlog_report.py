#!/usr/bin/env python3
"""Backlog a připravenost offer workeru – spustit PŘED jeho zapnutím.

Vypíše, co by offer worker po startu zpracoval nebo odeslal: offer joby ve
frontě/rozpracované (= volání AI), rozpracované offer requesty, nepublikované
outbox události (zveřejní je outbox publisher) a délku Redis fronty. Ověří také
konfiguraci providera (AI_OFFER_PROVIDER=claude jen s platným klíčem a tvrdými
rozpočtovými limity).

    python -m scripts.offer_backlog_report            # přehled (exit 0, nebo 3 při nepřipraveném provideru)
    python -m scripts.offer_backlog_report --json
    python -m scripts.offer_backlog_report --require-no-ai-work   # exit 2, pokud by worker hned volal AI
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys

from app.composition.wiring import init_modules
from app.modules.offers.public import OfferWorkerNotReadyError, check_offer_provider_ready, collect_offer_backlog
from app.platform.config import get_settings
from app.platform.db.session import WorkerAsyncSessionFactory
from app.platform.redis_client import build_queue_redis_client_from_settings

init_modules()


async def _run(args: argparse.Namespace) -> int:
    settings = get_settings()
    redis = build_queue_redis_client_from_settings(settings, client_name="offer-backlog-report") if settings.redis_url else None
    provider_error: str | None = None
    try:
        async with WorkerAsyncSessionFactory() as session:
            try:
                provider = await check_offer_provider_ready(settings, session)
            except OfferWorkerNotReadyError as exc:
                provider, provider_error = settings.ai_offer_provider, str(exc)
            backlog = await collect_offer_backlog(session, redis)
    finally:
        if redis is not None:
            await redis.aclose()

    report = {"ai_offer_provider": provider, "provider_ready": provider_error is None, "provider_error": provider_error,
              **backlog.as_dict()}
    if args.json:
        print(json.dumps(report, default=str, indent=2))
    else:
        for key, value in report.items():
            print(f"{key:32} {value}")
    if provider_error is not None:
        return 3
    if args.require_no_ai_work and backlog.would_call_ai:
        return 2
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--require-no-ai-work", action="store_true", help="exit 2 if the worker would call AI right away")
    return asyncio.run(_run(parser.parse_args()))


if __name__ == "__main__":
    sys.exit(main())
