"""
Claude Vision provider — používá Anthropic API pro analýzu fotek zakázky.

Aktivace:
  AI_ANALYSIS_PROVIDER=claude
  ANTHROPIC_API_KEY=sk-ant-...   ← přidat do .env

Model: claude-opus-4-6 (výchozí), lze přebít přes CLAUDE_VISION_MODEL v .env.
"""

import asyncio
import base64
import json
import os
from pathlib import Path

import structlog

from app.core.config import get_settings

logger = structlog.get_logger(__name__)

# Retry on transient API errors; permanent errors (auth, bad request) are not retried.
_RETRY_DELAYS = (2.0, 4.0)  # pause between attempt 1→2 and 2→3  (3 attempts total)
# HTTP client timeout — tighter than the job-level timeout in analysis_service.py
_HTTP_TIMEOUT = 120.0

_SYSTEM_PROMPT = """
Jsi expert na stavební diagnostiku a cenové nabídky.
Analyzuješ fotografie stavebního objektu a vracíš strukturovaný JSON.

Výstupní JSON musí mít PŘESNĚ tuto strukturu (bez dalšího textu):
{
  "objectType": "roof" | "facade" | "interior" | "foundation" | "other",
  "surfaceCondition": "good" | "requires_attention" | "critical",
  "recommendedScope": "cleaning" | "local_repair" | "full_reconstruction",
  "estimatedAreaSqm": <číslo>,
  "areaConfidence": <0.0–1.0>,
  "maskPolygon": [{"x": 0.0–1.0, "y": 0.0–1.0}, ...],
  "materials": [
    {
      "name": "<název>",
      "unit": "m2" | "kg" | "l" | "ks",
      "quantity": <číslo>,
      "unitPrice": <číslo v CZK>,
      "totalPrice": <číslo v CZK>
    }
  ],
  "workflowSteps": [
    {
      "step": <int>,
      "name": "<název kroku>",
      "description": "<popis>",
      "estimatedHours": <číslo>
    }
  ],
  "estimatedTotalDays": <číslo>,
  "laborHoursTotal": <číslo>,
  "notes": "<volitelné poznámky>"
}

Pravidla:
- maskPolygon: 4–8 bodů ohraničující poškozenou oblast (relativní souřadnice 0–1)
- areaConfidence: 0.3 pokud je jen 1 fotka, 0.7+ pokud jsou 3+ fotky s GPS
- materials: reálné ceny českého trhu (CZK), materiály pro daný typ práce
- workflowSteps: konkrétní pracovní kroky v logickém pořadí
- Pokud jsou fotky nekvalitní nebo chybí, uveď nižší areaConfidence a notes
""".strip()


class ClaudeVisionProvider:
    key = "claude"

    def __init__(self) -> None:
        settings = get_settings()
        self._api_key: str | None = settings.anthropic_api_key
        self._model: str = os.getenv("CLAUDE_VISION_MODEL", "claude-opus-4-6")
        if not self._api_key:
            logger.warning(
                "claude.provider.init",
                problem="ANTHROPIC_API_KEY not set",
                hint="Add ANTHROPIC_API_KEY to python-backend/.env",
            )

    def _check_ready(self) -> None:
        if not self._api_key:
            raise RuntimeError(
                "AI_ANALYSIS_PROVIDER=claude ale ANTHROPIC_API_KEY není nastavený. "
                "Přidej ANTHROPIC_API_KEY=sk-ant-... do python-backend/.env"
            )

    def _build_content(self, project: dict, photos: list[dict]) -> list[dict]:
        """Sestaví content pole pro Messages API (text + obrázky)."""
        content: list[dict] = []

        # Popis zakázky
        description = project.get("description") or ""
        address = project.get("address_label") or project.get("addressLabel") or ""
        property_type = project.get("property_type") or project.get("propertyType") or ""
        repair_scope = project.get("repair_scope") or project.get("repairScope") or ""

        text_intro = (
            f"Zakázka: {project.get('title', 'bez názvu')}\n"
            f"Adresa: {address or '—'}\n"
            f"Typ objektu: {property_type or '—'}\n"
            f"Požadovaný rozsah: {repair_scope or '—'}\n"
            f"Popis: {description or '—'}\n"
            f"Počet fotek: {len(photos)}\n\n"
            "Analyzuj přiložené fotky a vrať JSON dle instrukcí."
        )
        content.append({"type": "text", "text": text_intro})

        # Přidej fotky
        photos_added = 0
        for photo in photos[:8]:  # max 8 fotek (API limit)
            url = photo.get("url") or ""
            raw_data = photo.get("_raw_bytes")  # bytes nahrané z disku

            if raw_data:
                b64 = base64.standard_b64encode(raw_data).decode()
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/jpeg",
                        "data": b64,
                    },
                })
                photos_added += 1
            elif url and url.startswith("http"):
                content.append({
                    "type": "image",
                    "source": {"type": "url", "url": url},
                })
                photos_added += 1

        if photos_added == 0:
            content.append({
                "type": "text",
                "text": "Poznámka: žádné dostupné fotky. Použij textový popis a vrať odhad s nízkým areaConfidence.",
            })

        return content

    def _parse_response(self, text: str) -> dict:
        """Extrahuje JSON z odpovědi modelu."""
        text = text.strip()
        # Odstraní markdown code block pokud existuje
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1]) if lines[-1].strip() == "```" else "\n".join(lines[1:])
        return json.loads(text)

    async def analyze_project(self, *, project: dict, photos: list[dict]) -> dict:
        self._check_ready()

        try:
            import anthropic
        except ImportError as exc:
            raise RuntimeError(
                "Balíček 'anthropic' není nainstalovaný. "
                "Spusť: pip install anthropic"
            ) from exc

        client = anthropic.AsyncAnthropic(api_key=self._api_key, timeout=_HTTP_TIMEOUT)
        content = self._build_content(project, photos)

        logger.info(
            "claude.vision.analyze",
            model=self._model,
            photo_count=len(photos),
            project_id=project.get("id"),
        )

        response = None
        for attempt, delay in enumerate((*_RETRY_DELAYS, None), start=1):
            try:
                response = await client.messages.create(
                    model=self._model,
                    max_tokens=4096,
                    thinking={"type": "adaptive"},
                    system=_SYSTEM_PROMPT,
                    messages=[{"role": "user", "content": content}],
                )
                break
            except (
                anthropic.APIConnectionError,
                anthropic.RateLimitError,
                anthropic.InternalServerError,
            ) as exc:
                if delay is None:
                    raise  # exhausted retries
                logger.warning(
                    "claude.vision.retry",
                    attempt=attempt,
                    delay_s=delay,
                    error=str(exc),
                )
                await asyncio.sleep(delay)

        # Najdi text blok (přeskočí thinking bloky)
        result_text = ""
        for block in response.content:
            if block.type == "text":
                result_text = block.text
                break

        if not result_text:
            raise RuntimeError("Claude nevrátil žádný textový blok.")

        parsed = self._parse_response(result_text)

        # Spočítej laborHoursTotal pokud chybí
        if "laborHoursTotal" not in parsed and "workflowSteps" in parsed:
            parsed["laborHoursTotal"] = round(
                sum(s.get("estimatedHours", 0) for s in parsed["workflowSteps"]), 1
            )

        return {
            "providerKey": "claude",
            "jobType": "vision_claude",
            "modelName": self._model,
            "modelVersion": "1.0",
            **parsed,
        }
