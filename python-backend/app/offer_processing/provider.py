"""AI provider abstraction layer.

OfferService never calls an AI provider directly.
It calls AgentRuntime, which delegates to a ProviderAdapter.

Hierarchy:
    AgentRuntime
        → selects ProviderAdapter by key (or fallback chain)
        → ProviderAdapter.complete(input_snapshot) → ProviderResponse

Fallback routing rules:
    Only retryable transport errors trigger fallback:
        - 503 Service Unavailable
        - 429 Rate Limited (when no retry-after is acceptable)
    Schema/validation errors (400) are NOT retried on fallback — same bad
    input will produce the same bad result on another provider.
"""
from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import structlog

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Data contracts
# ---------------------------------------------------------------------------


@dataclass
class ProviderRequest:
    """Anonymized input sent to the AI provider."""
    work_type_code: str
    parameters: dict[str, Any]
    photo_urls: list[str]          # presigned, short-lived
    work_type_definition: dict[str, Any]
    pricing_context: dict[str, Any]
    prompt_version: str = "offer-v1"


@dataclass
class ProviderResponse:
    raw_output: dict[str, Any]
    prompt_tokens: int
    completion_tokens: int
    model_id: str
    model_build: str
    provider_key: str
    duration_ms: int
    estimated_cost_usd: float = 0.0


# ---------------------------------------------------------------------------
# ProviderAdapter — abstract base
# ---------------------------------------------------------------------------


class ProviderAdapter(ABC):
    """Base class for AI provider adapters.

    Each adapter is stateless — construct once, call many times.
    """

    @property
    @abstractmethod
    def key(self) -> str:
        """Unique identifier, e.g. 'claude', 'openai', 'mock'."""

    @property
    @abstractmethod
    def model_id(self) -> str:
        """Default model ID for this adapter."""

    @abstractmethod
    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        """Call the AI provider and return a raw response.

        Raises:
            ProviderUnavailableError  — 503 / network failure (retryable)
            ProviderRateLimitedError  — 429 (retryable with backoff)
            ProviderRequestError      — 400 / bad input (not retryable)
        """


# ---------------------------------------------------------------------------
# Provider errors
# ---------------------------------------------------------------------------


class ProviderError(RuntimeError):
    retryable: bool = False


class ProviderUnavailableError(ProviderError):
    retryable = True


class ProviderRateLimitedError(ProviderError):
    retryable = True

    def __init__(self, message: str, retry_after_seconds: int | None = None) -> None:
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


class ProviderRequestError(ProviderError):
    retryable = False


# ---------------------------------------------------------------------------
# Anthropic / Claude adapter
# ---------------------------------------------------------------------------


class AnthropicAdapter(ProviderAdapter):
    """Calls Claude via the Anthropic SDK."""

    _MODEL_ID = "claude-opus-4-7"
    _MODEL_BUILD = "claude-opus-4-7-20251001"

    def __init__(self, api_key: str, model_id: str | None = None) -> None:
        self._api_key = api_key
        self._model_id = model_id or self._MODEL_ID

    @property
    def key(self) -> str:
        return "claude"

    @property
    def model_id(self) -> str:
        return self._model_id

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        try:
            import anthropic  # noqa: PLC0415
        except ImportError as exc:
            raise ProviderUnavailableError("anthropic SDK not installed") from exc

        client = anthropic.AsyncAnthropic(api_key=self._api_key)
        prompt = _build_offer_prompt(request)

        t0 = time.monotonic()
        try:
            message = await client.messages.create(
                model=self._model_id,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIStatusError as exc:
            if exc.status_code == 429:
                retry_after = int(exc.response.headers.get("retry-after", 60))
                raise ProviderRateLimitedError(str(exc), retry_after_seconds=retry_after) from exc
            if exc.status_code >= 500:
                raise ProviderUnavailableError(str(exc)) from exc
            raise ProviderRequestError(str(exc)) from exc
        except (anthropic.APIConnectionError, anthropic.APITimeoutError) as exc:
            raise ProviderUnavailableError(str(exc)) from exc

        duration_ms = int((time.monotonic() - t0) * 1000)
        raw_text = message.content[0].text if message.content else ""

        try:
            raw_output = json.loads(raw_text)
        except json.JSONDecodeError:
            raw_output = {"_raw_text": raw_text}

        return ProviderResponse(
            raw_output=raw_output,
            prompt_tokens=message.usage.input_tokens,
            completion_tokens=message.usage.output_tokens,
            model_id=self._model_id,
            model_build=self._MODEL_BUILD,
            provider_key=self.key,
            duration_ms=duration_ms,
        )


# ---------------------------------------------------------------------------
# Mock adapter (tests + development)
# ---------------------------------------------------------------------------


class MockAdapter(ProviderAdapter):
    """Deterministic mock for tests — never calls an external API."""

    def __init__(self, response_override: dict[str, Any] | None = None) -> None:
        self._response_override = response_override

    @property
    def key(self) -> str:
        return "mock"

    @property
    def model_id(self) -> str:
        return "mock-v1"

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        raw = self._response_override or _mock_offer_response(request)
        return ProviderResponse(
            raw_output=raw,
            prompt_tokens=500,
            completion_tokens=800,
            model_id="mock-v1",
            model_build="mock-v1-static",
            provider_key=self.key,
            duration_ms=10,
            estimated_cost_usd=0.0,
        )


# ---------------------------------------------------------------------------
# AgentRuntime — selects adapter, handles fallback
# ---------------------------------------------------------------------------


@dataclass
class AgentRuntime:
    """Selects the right ProviderAdapter and executes with optional fallback.

    Fallback is attempted ONLY for retryable transport errors.
    A bad request (ProviderRequestError) propagates immediately — retrying
    on a different provider would produce the same failure.
    """
    primary: ProviderAdapter
    fallbacks: list[ProviderAdapter] = field(default_factory=list)

    async def run(self, request: ProviderRequest) -> ProviderResponse:
        adapters = [self.primary, *self.fallbacks]
        last_exc: Exception | None = None
        for adapter in adapters:
            try:
                return await adapter.complete(request)
            except ProviderRequestError:
                raise
            except ProviderError as exc:
                last_exc = exc
                logger.warning(
                    "offer.provider_failed_trying_fallback",
                    provider=adapter.key,
                    error=str(exc),
                    retryable=exc.retryable,
                )
                continue
        assert last_exc is not None
        raise last_exc


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def build_agent_runtime(provider_key: str, settings) -> AgentRuntime:
    primary = _build_adapter(provider_key, settings)
    return AgentRuntime(primary=primary)


def _build_adapter(key: str, settings) -> ProviderAdapter:
    if key == "mock":
        return MockAdapter()
    if key == "claude":
        api_key = getattr(settings, "anthropic_api_key", None) or ""
        return AnthropicAdapter(api_key=api_key)
    raise ValueError(f"Unknown AI provider key: {key!r}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_offer_prompt(req: ProviderRequest) -> str:
    return (
        f"You are a construction cost estimation AI. "
        f"Work type: {req.work_type_code}. "
        f"Parameters: {json.dumps(req.parameters, ensure_ascii=False)}. "
        f"Return a JSON object with: line_items (array), total_price_czk (number), "
        f"confidence_score (0.0-1.0), currency ('CZK'), warnings (array of strings). "
        f"If you cannot estimate without more information, return: "
        f'{{ "outcome": "insufficient_data", "questions": ["..."] }}'
    )


def _mock_offer_response(req: ProviderRequest) -> dict[str, Any]:
    return {
        "outcome": "offer_generated",
        "line_items": [
            {
                "work_type_code": req.work_type_code,
                "description": f"Mock: {req.work_type_code}",
                "quantity": 1.0,
                "unit": "ks",
                "unit_price_czk": 10000.0,
                "total_price_czk": 10000.0,
            }
        ],
        "total_price_czk": 10000.0,
        "confidence_score": 0.95,
        "currency": "CZK",
        "warnings": [],
    }
