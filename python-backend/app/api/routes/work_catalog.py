from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import get_current_user, get_redis, get_work_catalog_service, resolve_org_id
from app.core.cache import get_cached, set_cached
from app.schemas.auth import AuthUserRead
from app.schemas.work_catalog import (
    CatalogCategoryListResponse,
    CatalogWorkTypeDetailRead,
    CatalogWorkTypeListResponse,
    EffectiveWorkTypeListResponse,
    EffectiveWorkTypeRead,
    ParameterSchemaDetailRead,
    ProjectWorkItemCreate,
    ProjectWorkItemDetailRead,
    ProjectWorkItemEffectiveConfigurationRead,
    ProjectWorkItemRead,
    ProjectWorkItemListResponse,
    ProjectWorkItemValueConfirmationInput,
    ProjectWorkItemValueInput,
    TenantWorkTypeSettingWithParametersUpsert,
    VisionDetectionCreate,
    VisionDetectionRead,
)
from app.services.work_catalog_service import (
    WorkCatalogNotFoundError,
    WorkCatalogService,
)
from app.work_catalog.cache import (
    GLOBAL_CATALOG_TTL_SECONDS,
    TENANT_EFFECTIVE_TTL_SECONDS,
    WORKFLOW_CONFIGURATION_TTL_SECONDS,
    effective_workflow_config_key,
    effective_work_type_item_key,
    effective_work_type_list_key,
    global_categories_key,
    global_parameter_schema_key,
    global_work_type_detail_key,
    global_work_type_list_key,
)
from app.work_catalog.domain import CatalogValidationError


router = APIRouter(tags=["work-catalog"])


def _required_org_id(current_user: AuthUserRead) -> str:
    org_id = resolve_org_id(current_user)
    if not org_id:
        raise HTTPException(
            status_code=403,
            detail="Tenant-scoped work catalog routes require an organization context.",
        )
    return org_id


@router.get("/work-catalog/work-types", response_model=EffectiveWorkTypeListResponse)
async def list_effective_work_types(
    current_user: AuthUserRead = Depends(get_current_user),
    service: WorkCatalogService = Depends(get_work_catalog_service),
    redis=Depends(get_redis),
):
    org_id = _required_org_id(current_user)
    cache_key = effective_work_type_list_key(org_id)
    cached = await get_cached(redis, cache_key)
    if cached is not None:
        return EffectiveWorkTypeListResponse.model_validate(cached)

    items = await service.list_effective_work_types(org_id)
    response = EffectiveWorkTypeListResponse(items=items, total=len(items))
    await set_cached(redis, cache_key, response.model_dump(mode="json"), TENANT_EFFECTIVE_TTL_SECONDS)
    return response


@router.get("/work-catalog/catalog/categories", response_model=CatalogCategoryListResponse)
async def list_catalog_categories(
    service: WorkCatalogService = Depends(get_work_catalog_service),
    redis=Depends(get_redis),
):
    cache_key = global_categories_key()
    cached = await get_cached(redis, cache_key)
    if cached is not None:
        return CatalogCategoryListResponse.model_validate(cached)

    items = await service.list_categories()
    response = CatalogCategoryListResponse(items=items, total=len(items))
    await set_cached(redis, cache_key, response.model_dump(mode="json"), GLOBAL_CATALOG_TTL_SECONDS)
    return response


@router.get("/work-catalog/catalog/work-types", response_model=CatalogWorkTypeListResponse)
async def list_catalog_work_types(
    service: WorkCatalogService = Depends(get_work_catalog_service),
    redis=Depends(get_redis),
):
    cache_key = global_work_type_list_key()
    cached = await get_cached(redis, cache_key)
    if cached is not None:
        return CatalogWorkTypeListResponse.model_validate(cached)

    items = await service.list_work_types_global()
    response = CatalogWorkTypeListResponse(items=items, total=len(items))
    await set_cached(redis, cache_key, response.model_dump(mode="json"), GLOBAL_CATALOG_TTL_SECONDS)
    return response


@router.get("/work-catalog/catalog/work-types/{work_type_code}", response_model=CatalogWorkTypeDetailRead)
async def get_catalog_work_type_detail(
    work_type_code: str,
    service: WorkCatalogService = Depends(get_work_catalog_service),
    redis=Depends(get_redis),
):
    cache_key = global_work_type_detail_key(work_type_code)
    cached = await get_cached(redis, cache_key)
    if cached is not None:
        return CatalogWorkTypeDetailRead.model_validate(cached)

    try:
        item = await service.get_work_type_detail(work_type_code)
    except WorkCatalogNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    payload = item.model_dump(mode="json")
    await set_cached(redis, cache_key, payload, GLOBAL_CATALOG_TTL_SECONDS)
    return payload


@router.get(
    "/work-catalog/catalog/work-types/{work_type_code}/parameters/{parameter_code}",
    response_model=ParameterSchemaDetailRead,
)
async def get_parameter_schema_detail(
    work_type_code: str,
    parameter_code: str,
    service: WorkCatalogService = Depends(get_work_catalog_service),
    redis=Depends(get_redis),
):
    cache_key = global_parameter_schema_key(work_type_code, parameter_code)
    cached = await get_cached(redis, cache_key)
    if cached is not None:
        return ParameterSchemaDetailRead.model_validate(cached)

    try:
        item = await service.get_parameter_schema_detail(
            work_type_code=work_type_code,
            parameter_code=parameter_code,
        )
    except WorkCatalogNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    payload = item.model_dump(mode="json")
    await set_cached(redis, cache_key, payload, GLOBAL_CATALOG_TTL_SECONDS)
    return payload


@router.get("/work-catalog/work-types/{work_type_code}/effective", response_model=EffectiveWorkTypeRead)
async def get_effective_work_type(
    work_type_code: str,
    current_user: AuthUserRead = Depends(get_current_user),
    service: WorkCatalogService = Depends(get_work_catalog_service),
    redis=Depends(get_redis),
):
    org_id = _required_org_id(current_user)
    cache_key = effective_work_type_item_key(org_id, work_type_code)
    cached = await get_cached(redis, cache_key)
    if cached is not None:
        return EffectiveWorkTypeRead.model_validate(cached)

    try:
        item = await service.get_effective_work_type(org_id, work_type_code)
    except WorkCatalogNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    payload = item.model_dump(mode="json")
    await set_cached(redis, cache_key, payload, TENANT_EFFECTIVE_TTL_SECONDS)
    return payload


@router.put("/work-catalog/work-types/{work_type_code}/settings", response_model=EffectiveWorkTypeRead)
async def upsert_tenant_work_type_setting(
    work_type_code: str,
    payload: TenantWorkTypeSettingWithParametersUpsert,
    current_user: AuthUserRead = Depends(get_current_user),
    service: WorkCatalogService = Depends(get_work_catalog_service),
    redis=Depends(get_redis),
):
    org_id = _required_org_id(current_user)
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

    return item.model_dump(mode="json")


@router.get("/cases/{case_id}/work-items", response_model=ProjectWorkItemListResponse)
async def list_project_work_items(
    case_id: str,
    current_user: AuthUserRead = Depends(get_current_user),
    service: WorkCatalogService = Depends(get_work_catalog_service),
):
    org_id = _required_org_id(current_user)
    try:
        items = await service.list_project_work_items(project_id=case_id, organization_id=org_id)
    except WorkCatalogNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ProjectWorkItemListResponse(items=items, total=len(items))


@router.get(
    "/cases/{case_id}/work-types/{work_type_code}/effective-configuration",
    response_model=ProjectWorkItemEffectiveConfigurationRead,
)
async def get_project_work_item_effective_configuration(
    case_id: str,
    work_type_code: str,
    current_user: AuthUserRead = Depends(get_current_user),
    service: WorkCatalogService = Depends(get_work_catalog_service),
    redis=Depends(get_redis),
):
    org_id = _required_org_id(current_user)
    try:
        await service.ensure_project_exists(project_id=case_id, organization_id=org_id)
    except WorkCatalogNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    cache_key = effective_workflow_config_key(org_id, work_type_code)
    cached = await get_cached(redis, cache_key)
    if cached is not None:
        return ProjectWorkItemEffectiveConfigurationRead.model_validate(cached)

    try:
        item = await service.get_project_work_item_effective_configuration(
            project_id=case_id,
            organization_id=org_id,
            work_type_code=work_type_code,
        )
    except WorkCatalogNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    payload = item.model_dump(mode="json")
    await set_cached(redis, cache_key, payload, WORKFLOW_CONFIGURATION_TTL_SECONDS)
    return payload


@router.get("/cases/{case_id}/work-items/{project_work_item_id}", response_model=ProjectWorkItemDetailRead)
async def get_project_work_item_detail(
    case_id: str,
    project_work_item_id: str,
    current_user: AuthUserRead = Depends(get_current_user),
    service: WorkCatalogService = Depends(get_work_catalog_service),
):
    org_id = _required_org_id(current_user)
    try:
        item = await service.get_project_work_item_detail(
            project_id=case_id,
            project_work_item_id=project_work_item_id,
            organization_id=org_id,
        )
    except WorkCatalogNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return item.model_dump(mode="json")


@router.post("/cases/{case_id}/work-items", response_model=ProjectWorkItemRead)
async def create_project_work_item(
    case_id: str,
    payload: ProjectWorkItemCreate,
    current_user: AuthUserRead = Depends(get_current_user),
    service: WorkCatalogService = Depends(get_work_catalog_service),
):
    org_id = _required_org_id(current_user)
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
    org_id = _required_org_id(current_user)
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


@router.patch("/cases/{case_id}/work-items/{project_work_item_id}/values", response_model=ProjectWorkItemRead)
async def update_project_work_item_values(
    case_id: str,
    project_work_item_id: str,
    values: list[ProjectWorkItemValueInput],
    current_user: AuthUserRead = Depends(get_current_user),
    service: WorkCatalogService = Depends(get_work_catalog_service),
):
    org_id = _required_org_id(current_user)
    try:
        item = await service.update_project_work_item_values(
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


@router.post("/cases/{case_id}/work-items/{project_work_item_id}/values/merge", response_model=ProjectWorkItemRead)
async def merge_project_work_item_values(
    case_id: str,
    project_work_item_id: str,
    values: list[ProjectWorkItemValueInput],
    current_user: AuthUserRead = Depends(get_current_user),
    service: WorkCatalogService = Depends(get_work_catalog_service),
):
    org_id = _required_org_id(current_user)
    try:
        item = await service.merge_project_work_item_values(
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


@router.post("/cases/{case_id}/work-items/{project_work_item_id}/values/confirm", response_model=ProjectWorkItemRead)
async def confirm_project_work_item_values(
    case_id: str,
    project_work_item_id: str,
    payload: list[ProjectWorkItemValueConfirmationInput],
    current_user: AuthUserRead = Depends(get_current_user),
    service: WorkCatalogService = Depends(get_work_catalog_service),
):
    org_id = _required_org_id(current_user)
    try:
        item = await service.confirm_project_work_item_values(
            project_id=case_id,
            project_work_item_id=project_work_item_id,
            organization_id=org_id,
            confirmations=payload,
            confirmed_by_user_id=current_user.id,
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
    org_id = _required_org_id(current_user)
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
