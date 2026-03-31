from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AnalysisProviderCapability:
    key: str
    implemented: bool
    runtime_mode: str
    required_env_vars: tuple[str, ...] = ()
    startup_block_reason: str | None = None


_PROVIDER_CAPABILITIES: dict[str, AnalysisProviderCapability] = {
    "mock": AnalysisProviderCapability(
        key="mock",
        implemented=True,
        runtime_mode="development",
    ),
    "claude": AnalysisProviderCapability(
        key="claude",
        implemented=True,
        runtime_mode="external",
        required_env_vars=("ANTHROPIC_API_KEY",),
    ),
    "openai": AnalysisProviderCapability(
        key="openai",
        implemented=False,
        runtime_mode="external",
        startup_block_reason=(
            "OpenAI vision provider is not implemented yet and is blocked at startup."
        ),
    ),
}


def supported_analysis_provider_keys() -> tuple[str, ...]:
    return tuple(_PROVIDER_CAPABILITIES.keys())


def normalize_analysis_provider_key(provider_key: str) -> str:
    normalized = provider_key.strip().lower()
    if not normalized:
        raise ValueError("AI_ANALYSIS_PROVIDER must not be empty.")
    return normalized


def get_analysis_provider_capability(provider_key: str) -> AnalysisProviderCapability:
    normalized = normalize_analysis_provider_key(provider_key)
    capability = _PROVIDER_CAPABILITIES.get(normalized)
    if capability is None:
        allowed = ", ".join(supported_analysis_provider_keys())
        raise ValueError(
            f"AI_ANALYSIS_PROVIDER={provider_key!r} is not supported. "
            f"Allowed values: {allowed}."
        )
    return capability


def validate_selected_analysis_provider(
    provider_key: str,
    *,
    env_values: dict[str, str | None] | None = None,
) -> AnalysisProviderCapability:
    capability = get_analysis_provider_capability(provider_key)
    if not capability.implemented:
        raise ValueError(
            f"AI_ANALYSIS_PROVIDER={capability.key!r} is blocked. "
            f"{capability.startup_block_reason}"
        )

    values = env_values or {}
    missing = [
        key
        for key in capability.required_env_vars
        if not str(values.get(key) or "").strip()
    ]
    if missing:
        joined = ", ".join(missing)
        raise ValueError(
            f"AI_ANALYSIS_PROVIDER={capability.key!r} requires {joined} to be set."
        )
    return capability
