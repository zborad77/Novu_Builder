"""AI provider abstraction layer.

OfferService never calls an AI provider directly.
It calls AgentRuntime, which delegates to a ProviderAdapter.

Hierarchy:
    AgentRuntime
        → selects ProviderAdapter by key (or fallback chain)
        → ProviderAdapter.complete(input_snapshot) → ProviderResponse

Contract (full price separation — see NOVU_MASTER_PRODUCT_BOOK §AI):
    The AI agent returns ONLY measurements (quantities, units, surface
    condition, confidence) derived from the photos and parameters. It does
    NOT produce prices — pricing is computed deterministically server-side
    from the tenant catalog/pricing profile. Letting the model invent CZK
    prices would bypass the pricing subsystem and create a second source of
    pricing truth.

Structured output:
    We use *strict tool use* (`strict: true` on the tool definition) so the
    model's output is schema-validated by the API itself, not parsed from
    free-form prose. Two tools express the branch in the offer state machine:
        submit_measurements → outcome "offer_generated"
        request_more_info   → outcome "insufficient_data"
    `tool_choice = {"type": "any"}` forces the model to pick exactly one.

Fallback routing rules:
    Only retryable transport errors trigger fallback:
        - 503 Service Unavailable
        - 429 Rate Limited (when no retry-after is acceptable)
    Schema/validation errors (400) are NOT retried on fallback — same bad
    input will produce the same bad result on another provider.
"""
from __future__ import annotations

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
    photo_urls: list[str]          # presigned, short-lived GET URLs
    work_type_definition: dict[str, Any]
    pricing_context: dict[str, Any]
    prompt_version: str = "offer-v2"


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
            ProviderRequestError      — 400 / bad input / refusal (not retryable)
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
# Tool schemas — strict structured output (no prices)
# ---------------------------------------------------------------------------

# Strict tool use requires every property listed in `required` and
# `additionalProperties: false`. Numeric bounds (min/max) are NOT supported in
# strict mode — they are enforced server-side by the Pydantic validation layer.

_MEASUREMENT_ITEM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "work_type_code",
        "quantity",
        "unit",
        "surface_condition",
        "recommended_scope",
        "description",
        "confidence",
    ],
    "properties": {
        "work_type_code": {"type": "string"},
        "quantity": {"type": "number"},
        "unit": {"type": "string"},
        "surface_condition": {
            "type": "string",
            "enum": ["good", "requires_attention", "critical"],
        },
        "recommended_scope": {
            "type": "string",
            "enum": ["cleaning", "local_repair", "full_reconstruction"],
        },
        "description": {"type": "string"},
        "confidence": {"type": "number"},
    },
}

_SUBMIT_MEASUREMENTS_TOOL: dict[str, Any] = {
    "name": "submit_measurements",
    "description": (
        "Submit the measured quantities for the work items detected on the "
        "photos. Return quantities, units and condition ONLY — never prices."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["measurements", "overall_confidence", "warnings"],
        "properties": {
            "measurements": {
                "type": "array",
                "items": _MEASUREMENT_ITEM_SCHEMA,
            },
            "overall_confidence": {"type": "number"},
            "warnings": {"type": "array", "items": {"type": "string"}},
        },
    },
}

_REQUEST_MORE_INFO_TOOL: dict[str, Any] = {
    "name": "request_more_info",
    "description": (
        "Use this when the photos or parameters are insufficient to measure "
        "the work reliably. Return the specific questions that would unblock "
        "the measurement."
    ),
    "strict": True,
    "input_schema": {
        "type": "object",
        "additionalProperties": False,
        "required": ["questions"],
        "properties": {
            "questions": {"type": "array", "items": {"type": "string"}},
        },
    },
}

_OFFER_TOOLS: list[dict[str, Any]] = [_SUBMIT_MEASUREMENTS_TOOL, _REQUEST_MORE_INFO_TOOL]

_SYSTEM_PROMPT = (
    "Jsi expert na stavební diagnostiku. Z přiložených fotek a parametrů "
    "stanovíš MĚŘENÍ jednotlivých pracovních položek: množství, jednotku, "
    "stav povrchu, doporučený rozsah a spolehlivost odhadu.\n\n"
    "PRAVIDLA:\n"
    "- NIKDY neuváděj ceny, sazby ani peněžní částky. Ceny dopočítá systém.\n"
    "- Měř jen to, co je na fotkách skutečně vidět; nedomýšlej.\n"
    "- quantity je číslo v dané jednotce (m2, m, ks, ...).\n"
    "- confidence 0.0–1.0: nižší při málo nebo nekvalitních fotkách.\n"
    "- Pokud data nestačí ke spolehlivému měření, použij nástroj "
    "request_more_info s konkrétními dotazy.\n"
    "- Jinak vždy zavolej nástroj submit_measurements."
)


# ---------------------------------------------------------------------------
# Anthropic / Claude adapter
# ---------------------------------------------------------------------------


class AnthropicAdapter(ProviderAdapter):
    """Calls Claude via the Anthropic SDK using strict tool use."""

    _DEFAULT_MODEL_ID = "claude-opus-5"
    _MAX_TOKENS = 8192
    _MAX_PHOTOS = 8           # Anthropic image-per-request soft limit
    _HTTP_TIMEOUT_S = 120.0

    def __init__(self, api_key: str, model_id: str | None = None) -> None:
        self._api_key = api_key
        self._model_id = model_id or self._DEFAULT_MODEL_ID

    @property
    def key(self) -> str:
        return "claude"

    @property
    def model_id(self) -> str:
        return self._model_id

    def _build_content(self, request: ProviderRequest) -> list[dict[str, Any]]:
        """Build the user content: instruction text first, then image blocks."""
        import json  # noqa: PLC0415

        text = (
            f"Typ práce: {request.work_type_code}\n"
            f"Parametry: {json.dumps(request.parameters, ensure_ascii=False)}\n"
            f"Definice typu práce (katalog): "
            f"{json.dumps(request.work_type_definition, ensure_ascii=False)}\n"
            f"Počet fotek: {len(request.photo_urls)}\n\n"
            "Změř pracovní položky a zavolej příslušný nástroj."
        )
        content: list[dict[str, Any]] = [{"type": "text", "text": text}]
        for url in request.photo_urls[: self._MAX_PHOTOS]:
            if url and url.startswith("http"):
                content.append(
                    {"type": "image", "source": {"type": "url", "url": url}}
                )
        return content

    async def complete(self, request: ProviderRequest) -> ProviderResponse:
        try:
            import anthropic  # noqa: PLC0415
        except ImportError as exc:
            raise ProviderUnavailableError("anthropic SDK not installed") from exc

        if not self._api_key:
            raise ProviderRequestError(
                "ANTHROPIC_API_KEY is not configured for the offer provider."
            )

        client = anthropic.AsyncAnthropic(api_key=self._api_key, timeout=self._HTTP_TIMEOUT_S)

        t0 = time.monotonic()
        try:
            message = await client.messages.create(  # type: ignore[call-overload]  # dict literals for tools/thinking are valid at the API; SDK overloads want typed params
                model=self._model_id,
                max_tokens=self._MAX_TOKENS,
                thinking={"type": "adaptive"},
                system=_SYSTEM_PROMPT,
                tools=_OFFER_TOOLS,
                tool_choice={"type": "any"},
                messages=[{"role": "user", "content": self._build_content(request)}],
            )
        except anthropic.APIStatusError as exc:
            if exc.status_code == 429:
                retry_after = _safe_retry_after(exc)
                raise ProviderRateLimitedError(str(exc), retry_after_seconds=retry_after) from exc
            if exc.status_code >= 500:
                raise ProviderUnavailableError(str(exc)) from exc
            raise ProviderRequestError(str(exc)) from exc
        except (anthropic.APIConnectionError, anthropic.APITimeoutError) as exc:
            raise ProviderUnavailableError(str(exc)) from exc

        duration_ms = int((time.monotonic() - t0) * 1000)

        if message.stop_reason == "refusal":
            raise ProviderRequestError("Model refused the offer measurement request.")

        raw_output = _extract_tool_output(message)

        return ProviderResponse(
            raw_output=raw_output,
            prompt_tokens=message.usage.input_tokens,
            completion_tokens=message.usage.output_tokens,
            model_id=self._model_id,
            model_build=self._model_id,
            provider_key=self.key,
            duration_ms=duration_ms,
        )


def _safe_retry_after(exc: Any) -> int:
    try:
        return int(exc.response.headers.get("retry-after", 60))
    except Exception:  # noqa: BLE001 — header parsing is best-effort
        return 60


def _extract_tool_output(message: Any) -> dict[str, Any]:
    """Map the model's forced tool call into the validation-layer raw output.

    Returns a dict with an `outcome` discriminator the validator understands.
    """
    for block in message.content:
        if getattr(block, "type", None) != "tool_use":
            continue
        tool_input = dict(block.input or {})
        if block.name == "submit_measurements":
            return {"outcome": "offer_generated", **tool_input}
        if block.name == "request_more_info":
            return {"outcome": "insufficient_data", **tool_input}
    raise ProviderRequestError("Model returned no tool call.")


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
            completion_tokens=300,
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
        model_id = getattr(settings, "claude_offer_model", None) or AnthropicAdapter._DEFAULT_MODEL_ID
        return AnthropicAdapter(api_key=api_key, model_id=model_id)
    raise ValueError(f"Unknown AI provider key: {key!r}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_offer_response(req: ProviderRequest) -> dict[str, Any]:
    """Deterministic measurements-only mock output (no prices)."""
    return {
        "outcome": "offer_generated",
        "measurements": [
            {
                "work_type_code": req.work_type_code,
                "quantity": 1.0,
                "unit": "ks",
                "surface_condition": "requires_attention",
                "recommended_scope": "local_repair",
                "description": f"Mock measurement: {req.work_type_code}",
                "confidence": 0.95,
            }
        ],
        "overall_confidence": 0.95,
        "warnings": [],
    }
