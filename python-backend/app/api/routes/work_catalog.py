from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user, get_redis, get_work_catalog_service
from app.core.cache import delete_cached, get_cached, set_cached
from app.schemas.auth import AuthUserRead
from app.schemas.work_catalog import (
    EffectiveWorkTypeListResponse,
    EffectiveWorkTypeRead,
    ProjectWorkItemCreate,
    ProjectWorkItemRead,
    ProjectWorkItemListResponse,
    ProjectWorkItemValueInput,
    TenantWorkTypeSettingWithParametersUpsert,
    VisionDetectionCreate,
    VisionDetectionRead,
)
from app.services.work_catalog_service import (
    WorkCatalogNotFoundError,
    WorkCatalogService,
)
from app.work_catalog.domain import CatalogValidationError


router = APIRouter(tags=["work-catalog"])

_CATALOG_TTL_SECONDS = 60


def _tenant_org_id(current_user: AuthUserRead) -> str:
    if not current_user.organizationId:
        raise HTTPException(
            status_code=403,
            detail="Tenant-scoped work catalog routes require an organization context.",
        )
    return current_user.organizationId


def _catalog_list_key(org_id: str) -> str:
    return f"work-catalog:list:{org_id}"


def _catalog_item_key(org_id: str, work_type_code: str) -> str:
    return f"work-catalog:item:{org_id}:{work_type_code}"


@router.get("/work-catalog/work-types", response_model=EffectiveWorkTypeListResponse)
async def list_effective_work_types(
    current_user: AuthUserRead = Depends(get_current_user),
    service: WorkCatalogService = Depends(get_work_catalog_service),
    redis=Depends(get_redis),
):
    org_id = _tenant_org_id(current_user)
    cache_key = _catalog_list_key(org_id)
    cached = await get_cached(redis, cache_key)
    if cached is not None:
        return EffectiveWorkTypeListResponse.model_validate(cached)

    items = await service.list_effective_work_types(org_id)
    response = EffectiveWorkTypeListResponse(items=items, total=len(items))
    await set_cached(redis, cache_key, response.model_dump(mode="json"), _CATALOG_TTL_SECONDS)
    return response


@router.get("/work-catalog/work-types/{work_type_code}/effective", response_model=EffectiveWorkTypeRead)
async def get_effective_work_type(
    work_type_code: str,
    current_user: AuthUserRead = Depends(get_current_user),
    service: WorkCatalogService = Depends(get_work_catalog_service),
    redis=Depends(get_redis),
):
    org_id = _tenant_org_id(current_user)
    cache_key = _catalog_item_key(org_id, work_type_code)
    cached = await get_cached(redis, cache_key)
    if cached is not None:
        return cached

    try:
        item = await service.get_effective_work_type(org_id, work_type_code)
    except WorkCatalogNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    payload = item.model_dump(mode="json")
    await set_cached(redis, cache_key, payload, _CATALOG_TTL_SECONDS)
    return payload


@router.put("/work-catalog/work-types/{work_type_code}/settings", response_model=EffectiveWorkTypeRead)
async def upsert_tenant_work_type_setting(
    work_type_code: str,
    payload: TenantWorkTypeSettingWithParametersUpsert,
    current_user: AuthUserRead = Depends(get_current_user),
    service: WorkCatalogService = Depends(get_work_catalog_service),
    redis=Depends(get_redis),
):
    org_id = _tenant_org_id(current_user)
    try:
        item = await service.upsert_tenant_setting(
            organization_id=org_id,
            work_type_code=work_type_code,
            payload=payload,
            updated_by_user_id=current_user.id,
        )
    except WorkCatalogNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CatalogValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await delete_cached(
        redis,
        _catalog_list_key(org_id),
        _catalog_item_key(org_id, work_type_code),
        _catalog_item_key(org_id, item.code),
    )
    return item.model_dump(mode="json")


@router.get("/cases/{case_id}/work-items", response_model=ProjectWorkItemListResponse)
async def list_project_work_items(
    case_id: str,
    current_user: AuthUserRead = Depends(get_current_user),
    service: WorkCatalogService = Depends(get_work_catalog_service),
):
    org_id = _tenant_org_id(current_user)
    items = await service.list_project_work_items(project_id=case_id, organization_id=org_id)
    return ProjectWorkItemListResponse(items=items, total=len(items))


@router.post("/cases/{case_id}/work-items", response_model=ProjectWorkItemRead)
async def create_project_work_item(
    case_id: str,
    payload: ProjectWorkItemCreate,
    current_user: AuthUserRead = Depends(get_current_user),
    service: WorkCatalogService = Depends(get_work_catalog_service),
):
    org_id = _tenant_org_id(current_user)
    try:
        item = await service.create_project_work_item(
            project_id=case_id,
            organization_id=org_id,
            payload=payload,
            created_by_user_id=current_user.id,
        )
    except WorkCatalogNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CatalogValidationError as exc:
        detail = str(exc)
        status_code = 409 if "disabled for this tenant" in detail else 400
        raise HTTPException(status_code=status_code, detail=detail) from exc
    return item.model_dump(mode="json")


@router.put("/cases/{case_id}/work-items/{project_work_item_id}/values", response_model=ProjectWorkItemRead)
async def replace_project_work_item_values(
    case_id: str,
    project_work_item_id: str,
    values: list[ProjectWorkItemValueInput],
    current_user: AuthUserRead = Depends(get_current_user),
    service: WorkCatalogService = Depends(get_work_catalog_service),
):
    org_id = _tenant_org_id(current_user)
    try:
        item = await service.replace_project_work_item_values(
            project_id=case_id,
            project_work_item_id=project_work_item_id,
            organization_id=org_id,
            values=values,
        )
    except WorkCatalogNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CatalogValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return item.model_dump(mode="json")


@router.post("/cases/{case_id}/work-items/{project_work_item_id}/detections", response_model=VisionDetectionRead)
async def create_vision_detection(
    case_id: str,
    project_work_item_id: str,
    payload: VisionDetectionCreate,
    current_user: AuthUserRead = Depends(get_current_user),
    service: WorkCatalogService = Depends(get_work_catalog_service),
):
    org_id = _tenant_org_id(current_user)
    try:
        detection = await service.create_vision_detection(
            project_id=case_id,
            project_work_item_id=project_work_item_id,
            organization_id=org_id,
            payload=payload,
            created_by_user_id=current_user.id,
        )
    except WorkCatalogNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except CatalogValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return detection.model_dump(mode="json")
