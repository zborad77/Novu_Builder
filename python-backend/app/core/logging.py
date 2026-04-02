"""Central logging configuration and sensitive-data redaction.

This module keeps the logging hardening in one place so request/security/worker
logs can stay diagnostically useful without leaking credentials or tokens.
"""

from __future__ import annotations

import logging
import logging.handlers
import re
import sys
from collections.abc import Mapping, Sequence

import structlog

REDACTED = "[REDACTED]"
REDACTED_TOKEN = "[REDACTED_TOKEN]"
REDACTED_BEARER = "Bearer [REDACTED]"

_SECURITY_PREFIX = "SECURITY_EVENT:"
_NON_SENSITIVE_TOKEN_KEYS = frozenset({
    "tokentype",
    "tokenstype",
    "tokensvalidafter",
})
_SENSITIVE_EXACT_KEYS = frozenset({
    "authorization",
    "token",
    "rawtoken",
    "accesstoken",
    "refreshtoken",
    "resettoken",
    "resetpasswordtoken",
    "jwttoken",
    "metricsauthtoken",
    "jwtsecret",
    "password",
    "currentpassword",
    "newpassword",
    "oldpassword",
    "smtppassword",
    "openaiapikey",
    "anthropicapikey",
    "s3secretaccesskey",
    "s3accesskeyid",
    "secretaccesskey",
    "clientsecret",
    "apikey",
    "apitoken",
    "tokendigest",
    "tokenhash",
    "inputpayload",
    "rawpayload",
    "requestbody",
    "responsebody",
    "providerrequest",
    "providerresponse",
})
_SENSITIVE_QUERY_KEYS = (
    "access_token",
    "refresh_token",
    "token",
    "reset_token",
    "password",
    "currentpassword",
    "newpassword",
    "secret",
    "signature",
    "sig",
    "x-amz-signature",
    "x-amz-credential",
    "x-amz-security-token",
    "awsaccesskeyid",
)
_BEARER_RE = re.compile(r"(?i)\bBearer\s+[^\s,;]+")
_JWT_RE = re.compile(
    r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}(?![A-Za-z0-9_-])"
)
_URL_CREDENTIAL_RE = re.compile(
    r"([a-z][a-z0-9+\-.]*://[^@\s]*:)([^@\s/]+)(@)",
    flags=re.IGNORECASE,
)
_JSON_STYLE_SECRET_RE = re.compile(
    r'((?:"|\')?(?:authorization|access_token|refresh_token|accessToken|refreshToken|token|reset_token|resetToken|password|currentPassword|newPassword|secret|jwt_secret|metrics_auth_token|openai_api_key|anthropic_api_key|smtp_password|s3_secret_access_key)(?:"|\')?\s*[:=]\s*)(?:"[^"]*"|\'[^\']*\'|[^\s,}]+)',
    flags=re.IGNORECASE,
)
_QUERY_STRING_SECRET_RE = re.compile(
    r"([?&](?:"
    + "|".join(re.escape(key) for key in _SENSITIVE_QUERY_KEYS)
    + r")=)[^&\s]+",
    flags=re.IGNORECASE,
)


def _normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", key.lower())


def is_sensitive_log_key(key: str) -> bool:
    normalized = _normalize_key(key)
    if normalized in _NON_SENSITIVE_TOKEN_KEYS:
        return False
    if normalized in _SENSITIVE_EXACT_KEYS:
        return True
    if "password" in normalized or "authorization" in normalized or "secret" in normalized:
        return True
    if normalized.endswith("token") or normalized.endswith("tokenhash") or normalized.endswith("tokendigest"):
        return True
    if normalized.endswith("apikey"):
        return True
    return False


def redact_sensitive_string(value: str) -> str:
    redacted = _BEARER_RE.sub(REDACTED_BEARER, value)
    redacted = _URL_CREDENTIAL_RE.sub(r"\1" + REDACTED + r"\3", redacted)
    redacted = _QUERY_STRING_SECRET_RE.sub(r"\1" + REDACTED, redacted)
    redacted = _JSON_STYLE_SECRET_RE.sub(r"\1" + REDACTED, redacted)
    redacted = _JWT_RE.sub(REDACTED_TOKEN, redacted)
    return redacted


def redact_sensitive_data(value: object, *, key: str | None = None) -> object:
    """Recursively redact sensitive log values without destroying diagnostics."""
    if key is not None and is_sensitive_log_key(key):
        return REDACTED

    if isinstance(value, str):
        return redact_sensitive_string(value)

    if isinstance(value, Mapping):
        return {
            map_key: redact_sensitive_data(map_value, key=str(map_key))
            for map_key, map_value in value.items()
        }

    if isinstance(value, tuple):
        return tuple(redact_sensitive_data(item) for item in value)

    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [redact_sensitive_data(item) for item in value]

    return value


def normalize_security_event(
    _logger: object,
    _method_name: str,
    event_dict: dict,
) -> dict:
    event = event_dict.get("event")
    if isinstance(event, str) and event.startswith(_SECURITY_PREFIX):
        raw_name = event[len(_SECURITY_PREFIX):].strip()
        normalized_name = re.sub(r"[^a-z0-9]+", "_", raw_name.lower()).strip("_")
        event_dict["event"] = "security_event"
        event_dict["security_event"] = normalized_name or "unknown"
        event_dict.setdefault("event_category", "security")
    return event_dict


def redact_log_event(
    _logger: object,
    _method_name: str,
    event_dict: dict,
) -> dict:
    return {
        key: redact_sensitive_data(value, key=key)
        for key, value in event_dict.items()
    }


def configure_logging(log_level: str = "INFO", log_file: str = "", log_error_file: str = "") -> None:
    structlog.reset_defaults()
    level = getattr(logging, log_level.upper(), logging.INFO)

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setLevel(level)
    handlers: list[logging.Handler] = [stdout_handler]

    use_json = False

    if log_file:
        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setLevel(level)
        handlers.append(file_handler)
        use_json = True

    if log_error_file:
        error_handler = logging.handlers.RotatingFileHandler(
            log_error_file,
            maxBytes=5 * 1024 * 1024,
            backupCount=10,
            encoding="utf-8",
        )
        error_handler.setLevel(logging.ERROR)
        handlers.append(error_handler)
        use_json = True

    stdlib_processors: list = [
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        normalize_security_event,
        redact_log_event,
    ]

    shared_processors: list = [
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    renderer = (
        structlog.processors.JSONRenderer()
        if use_json
        else structlog.dev.ConsoleRenderer()
    )

    structlog_processors = [
        structlog.contextvars.merge_contextvars,
        *shared_processors,
    ]
    if use_json:
        structlog_processors.append(structlog.processors.dict_tracebacks)
    structlog_processors.extend([
        normalize_security_event,
        redact_log_event,
        renderer,
    ])

    formatter = structlog.stdlib.ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=stdlib_processors,
    )
    for handler in handlers:
        handler.setFormatter(formatter)

    logging.basicConfig(handlers=handlers, level=level, force=True)

    structlog.configure(
        processors=structlog_processors,
        wrapper_class=structlog.make_filtering_bound_logger(level),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )
