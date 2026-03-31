"""
OpenAI Vision provider skeleton.

Set AI_ANALYSIS_PROVIDER=openai and OPENAI_API_KEY=sk-... in .env to activate.
The analyze_project method raises NotImplementedError until a real implementation
is added here — swap in your OpenAI API call and it will be picked up automatically.
"""

import os


class OpenAIVisionProvider:
    key = "openai"

    def __init__(self) -> None:
        self._api_key: str | None = os.getenv("OPENAI_API_KEY")

    async def analyze_project(
        self,
        *,
        project: dict,
        photos: list[dict],
        analysis_config: dict | None = None,
    ) -> dict:
        if not self._api_key:
            raise RuntimeError(
                "AI_ANALYSIS_PROVIDER is set to 'openai' but OPENAI_API_KEY is not configured. "
                "Add OPENAI_API_KEY=sk-... to your .env file, or switch to AI_ANALYSIS_PROVIDER=mock."
            )
        raise NotImplementedError(
            "OpenAI vision provider is configured but not yet implemented. "
            "Implement analyze_project() in openai_vision_provider.py."
        )
