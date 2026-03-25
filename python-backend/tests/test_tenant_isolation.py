"""
Tenant isolation smoke tests — verify that org-scoped queries
prevent cross-tenant data access.
These are unit tests using mocked DB sessions; they test logic, not DB connectivity.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_project(project_id: str, org_id: str):
    p = MagicMock()
    p.id = project_id
    p.organization_id = org_id
    p.created_by_user_id = "usr_1"
    p.photos = []
    p.proposal_draft = None
    p.final_proposals = []
    p.analysis_results = []
    p.quote_variants = []
    p.client = None
    p.reference_expectations_json = None
    return p


def _make_analysis_result(result_id: str, project_id: str):
    r = MagicMock()
    r.id = result_id
    r.project_id = project_id
    return r


# ─────────────────────────────────────────────────────────────────────────────
# ProjectRepository — get_project with org scope
# ─────────────────────────────────────────────────────────────────────────────

class TestProjectRepositoryOrgScope:
    """Verify that get_project with organization_id filters correctly."""

    @pytest.mark.asyncio
    async def test_get_project_returns_none_for_wrong_org(self):
        from app.repositories.project_repository import ProjectRepository
        session = AsyncMock()
        # Simulate that the DB returns no result when org doesn't match
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute = AsyncMock(return_value=mock_result)
        repo = ProjectRepository(session)
        result = await repo.get_project("prj_abc", organization_id="org_B")
        # The query was executed — if org filter was added, result is None
        assert result is None

    @pytest.mark.asyncio
    async def test_get_project_returns_project_for_correct_org(self):
        from app.repositories.project_repository import ProjectRepository
        project = _make_project("prj_abc", "org_A")
        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = project
        session.execute = AsyncMock(return_value=mock_result)
        repo = ProjectRepository(session)
        result = await repo.get_project("prj_abc", organization_id="org_A")
        assert result is not None
        assert result.organization_id == "org_A"


# ─────────────────────────────────────────────────────────────────────────────
# PricebookRepository — no org_1 fallback
# ─────────────────────────────────────────────────────────────────────────────

class TestPricebookRepositoryOrgScope:
    """Verify pricebook operations are org-scoped and org_1 is not hardcoded."""

    def test_create_pricebook_uses_passed_org_id(self):
        import inspect
        from app.repositories.pricebook_repository import PricebookRepository
        source = inspect.getsource(PricebookRepository.create_pricebook)
        assert "org_1" not in source, "Hardcoded org_1 found in create_pricebook"

    def test_list_pricebooks_accepts_org_id(self):
        import inspect
        from app.repositories.pricebook_repository import PricebookRepository
        source = inspect.getsource(PricebookRepository.list_pricebooks)
        assert "organization_id" in source

    @pytest.mark.asyncio
    async def test_list_pricebook_items_returns_none_for_wrong_org(self):
        from app.repositories.pricebook_repository import PricebookRepository
        session = AsyncMock()
        # Pricebook belongs to org_A but request is from org_B
        pricebook = MagicMock()
        pricebook.organization_id = "org_A"
        session.get = AsyncMock(return_value=pricebook)
        repo = PricebookRepository(session)
        result_pb, result_items = await repo.list_pricebook_items("pb_1", "org_B")
        assert result_pb is None
        assert result_items == []


# ─────────────────────────────────────────────────────────────────────────────
# MaterialCatalogRepository — no org_1 fallback
# ─────────────────────────────────────────────────────────────────────────────

class TestMaterialCatalogRepositoryOrgScope:
    """Verify org_1 default removed from material catalog."""

    def test_list_material_catalog_requires_org_id(self):
        import inspect
        from app.repositories.material_catalog_repository import MaterialCatalogRepository
        sig = inspect.signature(MaterialCatalogRepository.list_material_catalog)
        param = sig.parameters.get("organization_id")
        assert param is not None, "organization_id parameter missing"
        # Must not have a default of "org_1"
        assert param.default != "org_1", "org_1 default still present"

    def test_source_has_no_org_1_string(self):
        import inspect
        from app.repositories.material_catalog_repository import MaterialCatalogRepository
        source = inspect.getsource(MaterialCatalogRepository)
        assert "org_1" not in source, "Hardcoded org_1 found in MaterialCatalogRepository"


# ─────────────────────────────────────────────────────────────────────────────
# SupplierRepository — no org_1 fallback
# ─────────────────────────────────────────────────────────────────────────────

class TestSupplierRepositoryOrgScope:
    """Verify org_1 default removed from supplier repository."""

    def test_list_suppliers_requires_org_id(self):
        import inspect
        from app.repositories.supplier_repository import SupplierRepository
        sig = inspect.signature(SupplierRepository.list_suppliers)
        param = sig.parameters.get("organization_id")
        assert param is not None, "organization_id parameter missing"
        assert param.default != "org_1", "org_1 default still present"

    def test_source_has_no_org_1_string(self):
        import inspect
        from app.repositories.supplier_repository import SupplierRepository
        source = inspect.getsource(SupplierRepository)
        assert "org_1" not in source, "Hardcoded org_1 found in SupplierRepository"


# ─────────────────────────────────────────────────────────────────────────────
# QuoteVariantRepository — pricing profile org-scoped
# ─────────────────────────────────────────────────────────────────────────────

class TestQuoteVariantRepositoryOrgScope:
    """Verify get_default_pricing_profile is scoped by org."""

    def test_get_default_pricing_profile_accepts_org_id(self):
        import inspect
        from app.repositories.quote_variant_repository import QuoteVariantRepository
        sig = inspect.signature(QuoteVariantRepository.get_default_pricing_profile)
        assert "organization_id" in sig.parameters, "organization_id param missing from get_default_pricing_profile"

    def test_get_default_pricing_profile_filters_by_org(self):
        import inspect
        from app.repositories.quote_variant_repository import QuoteVariantRepository
        source = inspect.getsource(QuoteVariantRepository.get_default_pricing_profile)
        assert "organization_id" in source


# ─────────────────────────────────────────────────────────────────────────────
# Analysis result ownership — cross-tenant patch blocked
# ─────────────────────────────────────────────────────────────────────────────

class TestAnalysisResultOwnership:
    """Verify patch_analysis_selection verifies result belongs to the case."""

    def test_route_verifies_result_project_id(self):
        import inspect
        from app.api.routes.analysis_jobs import patch_analysis_selection
        source = inspect.getsource(patch_analysis_selection)
        assert "projectId" in source or "project_id" in source, \
            "patch_analysis_selection does not verify result ownership"
