import logging
import logging.handlers
import sys

import structlog


def configure_logging(log_level: str = "INFO", log_file: str = "", log_error_file: str = "") -> None:
    level = getattr(logging, log_level.upper(), logging.INFO)

    # stdout — always
    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(level)
    handlers: list[logging.Handler] = [stdout_handler]

    use_json = False

    if log_file:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10 MB
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        handlers.append(file_handler)
        use_json = True

    if log_error_file:
        # ERROR-only rotating file — separate from the main log
        error_handler = logging.handlers.RotatingFileHandler(
            log_error_file,
            maxBytes=5 * 1024 * 1024,  # 5 MB
            backupCount=10,             # keep more error rotations
            encoding="utf-8",
        )
        error_handler.setLevel(logging.ERROR)
        handlers.append(error_handler)
        use_json = True

    logging.basicConfig(format="%(message)s", handlers=handlers, level=level)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.dict_tracebacks,
            structlog.processors.JSONRenderer() if use_json else structlog.dev.ConsoleRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
