"""Blocked OpenAI Vision provider placeholder.

The real OpenAI implementation does not exist yet. Startup validation must
reject AI_ANALYSIS_PROVIDER=openai before any job can be enqueued or executed.
This runtime stub stays fail-closed as a final safety net.
"""


class OpenAIVisionProvider:
    key = "openai"
    implemented = False

    async def analyze_project(
        self,
        *,
        project: dict,
        photos: list[dict],
        analysis_config: dict | None = None,
    ) -> dict:
        raise NotImplementedError(
            "OpenAI vision provider is intentionally blocked because it is not implemented yet. "
            "Startup validation should reject AI_ANALYSIS_PROVIDER='openai' before runtime."
        )
