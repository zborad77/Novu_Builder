from collections.abc import Sequence

from app.ai.providers.claude_vision_provider import ClaudeVisionProvider
from app.ai.providers.mock_vision_provider import MockVisionProvider
from app.ai.providers.openai_vision_provider import OpenAIVisionProvider
from app.models import ProjectPhoto
from app.storage.backend import generate_presigned_url as _generate_presigned_url, read_storage_file


PROVIDERS = {
    "mock": MockVisionProvider(),
    "openai": OpenAIVisionProvider(),
    "claude": ClaudeVisionProvider(),
}


def get_analysis_provider(provider_key: str):
    if not provider_key or not provider_key.strip():
        raise ValueError("AI analysis provider key is not configured (AI_ANALYSIS_PROVIDER is empty)")
    normalized_key = provider_key.strip().lower()
    provider = PROVIDERS.get(normalized_key)
    if provider is None:
        raise ValueError(f"Unknown AI analysis provider: {normalized_key}")
    return provider


async def _load_photo_bytes(photo: ProjectPhoto) -> bytes | None:
    """Load photo bytes via the active storage backend, preferring the AI input variant."""
    for key in (photo.ai_input_storage_key, photo.storage_key):
        if key:
            content = await read_storage_file(relative_storage_key=key)
            if content is not None:
                return content
    return None


async def normalize_photo_inputs(photos: Sequence[ProjectPhoto], *, load_bytes: bool = False) -> list[dict]:
    normalized_inputs = []
    for photo in photos:
        width = photo.width if isinstance(photo.width, int) else None
        height = photo.height if isinstance(photo.height, int) else None
        entry: dict = {
            "id": photo.id,
            "originalFilename": photo.original_filename,
            "mimeType": photo.mime_type,
            "fileSize": photo.file_size,
            "width": width,
            "height": height,
            "orientation": (
                "landscape"
                if width is not None and height is not None and width >= height
                else "portrait"
                if width is not None and height is not None
                else "unknown"
            ),
            "takenAt": photo.taken_at,
            "hasGps": photo.exif_lat is not None and photo.exif_lng is not None,
            "location": {
                "lat": photo.exif_lat,
                "lng": photo.exif_lng,
            },
            "url": _generate_presigned_url(photo.storage_key) if photo.storage_key else None,
        }
        if load_bytes:
            entry["_raw_bytes"] = await _load_photo_bytes(photo)
        normalized_inputs.append(entry)
    return normalized_inputs


async def run_project_analysis(*, provider_key: str, project: dict, photos: Sequence[ProjectPhoto]) -> dict:
    provider = get_analysis_provider(provider_key)
    load_bytes = provider_key == "claude"
    normalized_photos = await normalize_photo_inputs(photos, load_bytes=load_bytes)
    result = await provider.analyze_project(project=project, photos=normalized_photos)
    return {
        "providerKey": result.get("providerKey", provider.key),
        "jobType": result.get("jobType", "manual_trigger"),
        "objectType": result.get("objectType"),
        "surfaceCondition": result.get("surfaceCondition"),
        "recommendedScope": result.get("recommendedScope"),
        "estimatedAreaSqm": result.get("estimatedAreaSqm"),
        "areaConfidence": result.get("areaConfidence"),
        "maskPolygon": result.get("maskPolygon"),
        "materials": result.get("materials"),
        "workflowSteps": result.get("workflowSteps"),
        "estimatedTotalDays": result.get("estimatedTotalDays"),
        "laborHoursTotal": result.get("laborHoursTotal"),
        "modelName": result.get("modelName", provider.key),
        "modelVersion": result.get("modelVersion", "1.0"),
    }


def describe_analysis_provider(provider_key: str) -> dict:
    provider = get_analysis_provider(provider_key)
    return {
        "providerKey": provider.key,
        "mode": "development" if provider.key == "mock" else "external",
    }
