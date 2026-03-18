from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    AnalysisJob,
    AnalysisResult,
    Client,
    MaterialCatalog,
    Organization,
    PricingProfile,
    Project,
    ProjectPhoto,
    QuoteItem,
    QuoteVariant,
    Supplier,
    SupplierMaterialPrice,
    User,
)


async def ensure_dev_seed(session: AsyncSession) -> None:
    organization = await session.get(Organization, "org_1")
    if organization is None:
        session.add(
            Organization(
                id="org_1",
                name="NOVU Demo",
                ico="12345678",
                email="info@novu.local",
                phone="+420777000111",
                default_currency="CZK",
            )
        )

    user = await session.get(User, "usr_1")
    if user is None:
        session.add(
            User(
                id="usr_1",
                organization_id="org_1",
                email="demo@novu.local",
                password_hash="demo-hash",
                full_name="Demo Manager",
                role="manager",
                is_active=True,
            )
        )

    client = await session.get(Client, "cli_1")
    if client is None:
        session.add(
            Client(
                id="cli_1",
                organization_id="org_1",
                full_name="Petr Novak",
                company_name=None,
                email="petr.novak@example.com",
                phone="+420777111222",
                notes="",
            )
        )

    profile = await session.get(PricingProfile, "price_default")
    if profile is None:
        session.add(
            PricingProfile(
                id="price_default",
                organization_id="org_1",
                name="Default profile",
                hourly_rate=520,
                daily_rate=4200,
                labor_hours_per_sqm=0.3,
                margin_economy_pct=12,
                margin_standard_pct=18,
                margin_premium_pct=28,
                vat_pct=21,
                currency="CZK",
                is_default=True,
            )
        )

    suppliers = [
        {
            "id": "sup_dek",
            "name": "DEK",
            "code": "dek",
            "website_url": "https://www.dek.cz",
            "integration_type": "manual",
            "is_active": True,
            "contact_name": "",
            "contact_email": "",
        },
        {
            "id": "sup_stavmat",
            "name": "Stavmat",
            "code": "stavmat",
            "website_url": "https://www.stavmat.cz",
            "integration_type": "manual",
            "is_active": True,
            "contact_name": "",
            "contact_email": "",
        },
        {
            "id": "sup_invest",
            "name": "Invest",
            "code": "invest",
            "website_url": "",
            "integration_type": "manual",
            "is_active": True,
            "contact_name": "",
            "contact_email": "",
        },
    ]

    for supplier_data in suppliers:
        supplier = await session.get(Supplier, supplier_data["id"])
        if supplier is None:
            session.add(Supplier(organization_id="org_1", **supplier_data))

    materials = [
        {
            "id": "mat_penetrace",
            "name": "Penetrace",
            "category": "coating",
            "unit": "l",
            "norm_per_sqm": 0.35,
            "default_unit_price": 82,
            "default_supplier_id": "sup_dek",
            "is_active": True,
            "notes": "Zakladni priprava podkladu",
        },
        {
            "id": "mat_opravna_smes",
            "name": "Opravna smes",
            "category": "repair",
            "unit": "kg",
            "norm_per_sqm": 2.8,
            "default_unit_price": 24,
            "default_supplier_id": "sup_stavmat",
            "is_active": True,
            "notes": "Lokalni opravy prasklin a odstreku",
        },
        {
            "id": "mat_fasadni_nater",
            "name": "Fasadni nater",
            "category": "coating",
            "unit": "kg",
            "norm_per_sqm": 0.45,
            "default_unit_price": 118,
            "default_supplier_id": "sup_dek",
            "is_active": True,
            "notes": "Finalni vrstva pro standardni realizaci",
        },
    ]

    for material_data in materials:
        material = await session.get(MaterialCatalog, material_data["id"])
        if material is None:
            session.add(MaterialCatalog(organization_id="org_1", **material_data))

    supplier_prices = [
        {
            "id": "smp_1",
            "material_catalog_id": "mat_penetrace",
            "supplier_id": "sup_dek",
            "supplier_product_name": "Penetrace DEK",
            "supplier_sku": "DEK-PEN-01",
            "unit": "l",
            "unit_price": 79,
            "currency": "CZK",
            "availability_status": "in_stock",
            "source_type": "manual",
            "source_url": "https://www.dek.cz",
        },
        {
            "id": "smp_2",
            "material_catalog_id": "mat_penetrace",
            "supplier_id": "sup_stavmat",
            "supplier_product_name": "Penetrace Stavmat",
            "supplier_sku": "STM-PEN-77",
            "unit": "l",
            "unit_price": 84,
            "currency": "CZK",
            "availability_status": "in_stock",
            "source_type": "manual",
            "source_url": "https://www.stavmat.cz",
        },
        {
            "id": "smp_3",
            "material_catalog_id": "mat_opravna_smes",
            "supplier_id": "sup_invest",
            "supplier_product_name": "Opravna smes Invest",
            "supplier_sku": "INV-REP-12",
            "unit": "kg",
            "unit_price": 23,
            "currency": "CZK",
            "availability_status": "limited",
            "source_type": "manual",
            "source_url": None,
        },
    ]

    for supplier_price_data in supplier_prices:
        supplier_price = await session.get(SupplierMaterialPrice, supplier_price_data["id"])
        if supplier_price is None:
            session.add(SupplierMaterialPrice(**supplier_price_data))

    existing_project = await session.get(Project, "prj_1")
    if existing_project is None:
        session.add(
            Project(
                id="prj_1",
                organization_id="org_1",
                client_id="cli_1",
                created_by_user_id="usr_1",
                title="Fasada domu Novak",
                description="Znecistena severni stena a lokalni praskliny kolem oken.",
                status="analysed",
                property_type="facade",
                repair_scope="local_repair",
                location_lat=50.087,
                location_lng=14.421,
                address_label="Praha 1",
            )
        )

    seeded_photos = [
        {
            "id": "pho_1",
            "storage_key": "projects/prj_1/front-view.jpg",
            "preview_storage_key": "projects/prj_1/preview/front-view.jpg",
            "ai_input_storage_key": "projects/prj_1/ai/front-view.jpg",
            "original_filename": "front-view.jpg",
            "mime_type": "image/jpeg",
            "file_size": 2450000,
            "width": 1600,
            "height": 1200,
            "preview_file_size": 440000,
            "preview_width": 1600,
            "preview_height": 1200,
            "ai_input_file_size": 210000,
            "ai_input_width": 1280,
            "ai_input_height": 960,
            "processing_status": "ready",
            "exif_lat": 50.087,
            "exif_lng": 14.421,
            "is_primary": True,
            "sort_order": 1,
        },
        {
            "id": "pho_2",
            "storage_key": "projects/prj_1/wide-angle.jpg",
            "preview_storage_key": "projects/prj_1/preview/wide-angle.jpg",
            "ai_input_storage_key": "projects/prj_1/ai/wide-angle.jpg",
            "original_filename": "wide-angle.jpg",
            "mime_type": "image/jpeg",
            "file_size": 2680000,
            "width": 1800,
            "height": 1200,
            "preview_file_size": 500000,
            "preview_width": 1600,
            "preview_height": 1067,
            "ai_input_file_size": 240000,
            "ai_input_width": 1280,
            "ai_input_height": 853,
            "processing_status": "ready",
            "exif_lat": 50.087,
            "exif_lng": 14.421,
            "is_primary": False,
            "sort_order": 2,
        },
        {
            "id": "pho_3",
            "storage_key": "projects/prj_1/detail-window.jpg",
            "preview_storage_key": "projects/prj_1/preview/detail-window.jpg",
            "ai_input_storage_key": "projects/prj_1/ai/detail-window.jpg",
            "original_filename": "detail-window.jpg",
            "mime_type": "image/jpeg",
            "file_size": 1980000,
            "width": 900,
            "height": 1400,
            "preview_file_size": 360000,
            "preview_width": 900,
            "preview_height": 1400,
            "ai_input_file_size": 190000,
            "ai_input_width": 823,
            "ai_input_height": 1280,
            "processing_status": "ready",
            "exif_lat": 50.087,
            "exif_lng": 14.421,
            "is_primary": False,
            "sort_order": 3,
        },
    ]

    for photo_data in seeded_photos:
        seeded_photo = await session.get(ProjectPhoto, photo_data["id"])
        if seeded_photo is None:
            session.add(ProjectPhoto(project_id="prj_1", **photo_data))

    analysis_job = await session.get(AnalysisJob, "job_1")
    if analysis_job is None:
        session.add(
            AnalysisJob(
                id="job_1",
                project_id="prj_1",
                status="completed",
                job_type="vision_mock",
                requested_by_user_id="usr_1",
            )
        )

    analysis_result = await session.get(AnalysisResult, "ana_1")
    if analysis_result is None:
        session.add(
            AnalysisResult(
                id="ana_1",
                project_id="prj_1",
                analysis_job_id="job_1",
                reference_photo_id="pho_1",
                object_type="facade",
                surface_condition="requires_attention",
                recommended_scope="local_repair",
                estimated_area_sqm=54.9,
                area_confidence=0.77,
                selected_repair_polygon_json='[{"x":0.18,"y":0.22},{"x":0.58,"y":0.24},{"x":0.56,"y":0.68},{"x":0.2,"y":0.7}]',
                manual_area_sqm=18.5,
                final_area_source="manual",
                mask_polygon_json='[{"x":0.12,"y":0.16},{"x":0.84,"y":0.17},{"x":0.88,"y":0.86},{"x":0.14,"y":0.87}]',
                materials_suggestion_json='[{"name":"Penetrace","unit":"l","quantity":19},{"name":"Opravna smes","unit":"kg","quantity":154}]',
                workflow_suggestion_json='["Vizualni kontrola povrchu","Ocisteni a priprava podkladu","Lokalni oprava a finalni vrstva"]',
                model_name="mock-vision",
                model_version="0.2",
            )
        )

    quote_variants = [
        {
            "id": "qv_1",
            "project_id": "prj_1",
            "analysis_result_id": "ana_1",
            "pricing_profile_id": "price_default",
            "variant_type": "economy",
            "labor_cost": 16800,
            "material_cost": 13800,
            "other_cost": 4200,
            "margin_pct": 12,
            "total_ex_vat": 38976,
            "vat_amount": 8184.96,
            "total_inc_vat": 47160.96,
        },
        {
            "id": "qv_2",
            "project_id": "prj_1",
            "analysis_result_id": "ana_1",
            "pricing_profile_id": "price_default",
            "variant_type": "standard",
            "labor_cost": 19320,
            "material_cost": 18630,
            "other_cost": 4700,
            "margin_pct": 18,
            "total_ex_vat": 50248.60,
            "vat_amount": 10552.21,
            "total_inc_vat": 60800.81,
        },
        {
            "id": "qv_3",
            "project_id": "prj_1",
            "analysis_result_id": "ana_1",
            "pricing_profile_id": "price_default",
            "variant_type": "premium",
            "labor_cost": 21840,
            "material_cost": 24840,
            "other_cost": 5500,
            "margin_pct": 28,
            "total_ex_vat": 66890.20,
            "vat_amount": 14046.94,
            "total_inc_vat": 80937.14,
        },
    ]

    for variant_data in quote_variants:
        quote_variant = await session.get(QuoteVariant, variant_data["id"])
        if quote_variant is None:
            session.add(QuoteVariant(**variant_data))

    quote_items = [
        {
            "id": "qi_1",
            "quote_variant_id": "qv_1",
            "item_type": "labor",
            "name": "Cisteni a oprava fasady",
            "description": "Zakladni pracovni rozsah",
            "quantity": 42.5,
            "unit": "m2",
            "unit_price": 395.29,
            "total_price": 16800,
            "material_catalog_id": None,
            "supplier_id": None,
            "price_source": "company_catalog",
            "is_manual_override": False,
            "ai_suggested_unit_price": 395.29,
            "supplier_reference_unit_price": None,
            "company_default_unit_price": 395.29,
            "sort_order": 1,
        },
        {
            "id": "qi_2",
            "quote_variant_id": "qv_2",
            "item_type": "material",
            "name": "Penetrace",
            "description": "AI navrzeny material pro pripravu podkladu",
            "quantity": 18,
            "unit": "l",
            "unit_price": 82,
            "total_price": 1476,
            "material_catalog_id": "mat_penetrace",
            "supplier_id": "sup_dek",
            "price_source": "company_catalog",
            "is_manual_override": False,
            "ai_suggested_unit_price": 80,
            "supplier_reference_unit_price": 79,
            "company_default_unit_price": 82,
            "sort_order": 1,
        },
        {
            "id": "qi_3",
            "quote_variant_id": "qv_3",
            "item_type": "material",
            "name": "Opravna smes",
            "description": "Rucne upravena cena materialu pro premium variantu",
            "quantity": 120,
            "unit": "kg",
            "unit_price": 26,
            "total_price": 3120,
            "material_catalog_id": "mat_opravna_smes",
            "supplier_id": "sup_invest",
            "price_source": "manual_override",
            "is_manual_override": True,
            "ai_suggested_unit_price": 24,
            "supplier_reference_unit_price": 23,
            "company_default_unit_price": 24,
            "sort_order": 1,
        },
    ]

    for quote_item_data in quote_items:
        quote_item = await session.get(QuoteItem, quote_item_data["id"])
        if quote_item is None:
            session.add(QuoteItem(**quote_item_data))

    await session.commit()
