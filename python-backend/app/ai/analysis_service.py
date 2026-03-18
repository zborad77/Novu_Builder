from collections.abc import Sequence

from app.ai.providers.mock_vision_provider import MockVisionProvider
from app.models import ProjectPhoto


PROVIDERS = {
    "mock": MockVisionProvider(),
}


def get_analysis_provider(provider_key: str):
    normalized_key = (provider_key or "mock").strip().lower()
    provider = PROVIDERS.get(normalized_key)
    if provider is None:
        raise ValueError(f"Unknown AI analysis provider: {normalized_key}")
    return provider


def normalize_photo_inputs(photos: Sequence[ProjectPhoto]) -> list[dict]:
    normalized_inputs = []
    for photo in photos:
        width = photo.width if isinstance(photo.width, int) else None
        height = photo.height if isinstance(photo.height, int) else None
        normalized_inputs.append(
            {
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
                "url": f"/mock-storage/{photo.storage_key}" if photo.storage_key else None,
            }
        )
    return normalized_inputs


async def run_project_analysis(*, provider_key: str, project: dict, photos: Sequence[ProjectPhoto]) -> dict:
    provider = get_analysis_provider(provider_key)
    normalized_photos = normalize_photo_inputs(photos)
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
        "workflow": result.get("workflow"),
        "modelName": result.get("modelName", provider.key),
        "modelVersion": result.get("modelVersion", "1.0"),
    }


def describe_analysis_provider(provider_key: str) -> dict:
    provider = get_analysis_provider(provider_key)
    return {
        "providerKey": provider.key,
        "mode": "development" if provider.key == "mock" else "external",
    }
