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

    # Shared pre-chain used by both structlog and the stdlib ProcessorFormatter.
    # add_logger_name adds the originating module to every entry ("logger" key).
    shared_processors: list = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    # Exception rendering: structured dict for JSON (machine-parseable),
    # formatted string for console (human-readable).
    exc_processor = (
        structlog.processors.dict_tracebacks
        if use_json
        else structlog.processors.format_exc_info
    )

    renderer = (
        structlog.processors.JSONRenderer()
        if use_json
        else structlog.dev.ConsoleRenderer()
    )

    # Apply structlog's ProcessorFormatter to all stdlib handlers so that
    # uvicorn / SQLAlchemy / third-party logs share the same format and context.
    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )
    for handler in handlers:
        handler.setFormatter(formatter)

    logging.basicConfig(handlers=handlers, level=level)

    # structlog uses PrintLoggerFactory (direct output) so that its own loggers
    # render independently of stdlib — avoids the wrap_for_formatter chicken-and-egg
    # problem when loggers are called before configure_logging() runs (e.g. at
    # module import time in provider __init__ methods).
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            *shared_processors,
            exc_processor,
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )
