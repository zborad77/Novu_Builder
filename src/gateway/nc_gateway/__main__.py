"""Vstupní bod: ``python -m nc_gateway``.

Konfigurace jen z proměnných prostředí. Neplatná konfigurace nebo allowlist
= okamžitý konec s kódem 2 (fail-fast), nic se nespouští.
"""

from __future__ import annotations

import logging
import sys

import uvicorn

from nc_gateway.allowlist import AllowlistError
from nc_gateway.app import create_app
from nc_gateway.config import ConfigError, load_settings
from nc_gateway.logging_setup import configure_logging


def main() -> int:
    configure_logging()
    log = logging.getLogger("nc_gateway")
    try:
        settings = load_settings()
        app = create_app(settings)
    except (ConfigError, AllowlistError) as exc:
        log.critical("gateway_config_invalid", extra={"reason": str(exc)})
        return 2
    uvicorn.run(
        app,
        host=settings.listen_host,
        port=settings.listen_port,
        # Adresa klienta jen ze spojení / NC_BFF_TRUSTED_PROXY – uvicorn
        # nesmí sám přepisovat scope["client"] podle X-Forwarded-For.
        proxy_headers=False,
        server_header=False,
        access_log=False,
        log_config=None,
        lifespan="on",
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
