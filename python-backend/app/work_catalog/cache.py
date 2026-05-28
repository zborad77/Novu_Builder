from __future__ import annotations

from collections.abc import Iterable

from redis.asyncio import Redis

from app.core.cache import delete_cached, invalidate_cache_tag


WORK_CATALOG_CACHE_VERSION = "v2"

GLOBAL_CATALOG_TTL_SECONDS = 900
TENANT_EFFECTIVE_TTL_SECONDS = 180
WORKFLOW_CONFIGURATION_TTL_SECONDS = 180
LOCAL_RESOLUTION_TTL_SECONDS = 30


def _prefix() -> str:
    return f"work-catalog:{WORK_CATALOG_CACHE_VERSION}"


def global_catalog_cache_scope() -> str:
    return f"{_prefix()}:global"


def tenant_effective_cache_scope(organization_id: str) -> str:
    return f"{_prefix()}:tenant:{organization_id}:effective"


def pricing_resolution_cache_scope(organization_id: str) -> str:
    return f"{_prefix()}:tenant:{organization_id}:pricing"


def global_categories_key() -> str:
    return f"{_prefix()}:global:categories"


def global_work_type_list_key() -> str:
    return f"{_prefix()}:global:work-types"


def global_work_type_detail_key(work_type_code: str) -> str:
    return f"{_prefix()}:global:work-type:{work_type_code}"


def global_parameter_schema_key(work_type_code: str, parameter_code: str) -> str:
    return f"{_prefix()}:global:parameter:{work_type_code}:{parameter_code}"


def global_grouped_catalog_key() -> str:
    return f"{_prefix()}:global:grouped"


def effective_work_type_list_key(organization_id: str) -> str:
    return f"{_prefix()}:effective:list:{organization_id}"


def effective_work_type_item_key(organization_id: str, work_type_code: str) -> str:
    return f"{_prefix()}:effective:item:{organization_id}:{work_type_code}"


def effective_workflow_config_key(organization_id: str, work_type_code: str) -> str:
    return f"{_prefix()}:effective:workflow:{organization_id}:{work_type_code}"


def tenant_effective_cache_keys(
    *,
    organization_id: str,
    work_type_codes: Iterable[str] = (),
) -> list[str]:
    keys = [effective_work_type_list_key(organization_id)]
    seen_codes: set[str] = set()
    for code in work_type_codes:
        if code in seen_codes:
            continue
        seen_codes.add(code)
        keys.append(effective_work_type_item_key(organization_id, code))
        keys.append(effective_workflow_config_key(organization_id, code))
    return keys


async def invalidate_tenant_effective_cache(
    redis: Redis | None,
    *,
    organization_id: str,
    work_type_codes: Iterable[str] = (),
) -> None:
    await invalidate_cache_tag(redis, tenant_effective_cache_scope(organization_id))
    await delete_cached(
        redis,
        *tenant_effective_cache_keys(
            organization_id=organization_id,
            work_type_codes=work_type_codes,
        ),
    )


async def invalidate_pricing_resolution_cache(
    redis: Redis | None,
    *,
    organization_id: str,
) -> None:
    await invalidate_cache_tag(redis, pricing_resolution_cache_scope(organization_id))
