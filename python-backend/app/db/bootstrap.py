import base64

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.auth_service import hash_password
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
from app.storage.local_photo_storage import STORAGE_ROOT, ensure_directory


_SEED_PHOTO_BYTES = {
    "pho_1": base64.b64decode(
        "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"
    ),
    "pho_2": base64.b64decode(
        "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAQDAwQDAwQEAwQFBAQFBgoHBgYGBg0JCggKDw0QEA8NDw4RExgUERIXEg4PFRwVFxkZGxsbEBQdHx0aHxgaGxr/2wBDAQQFBQYFBgwHBwwaEQ8RGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhr/wAARCAB4ALQDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD7Ooooryz0AooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACvnWBR4R/aYkU4W31lCQScf6xM/8AoxMV9FV8+ftDRtoXifwZ4qhUbrafZIeefLdZFH6vXPVahKE3snr6PQ6aHvKUO6/FanFfH65ufE3xAv7fTlM8OhaevnbT90ZDO34GRQfpXoXjPxl9s/Z4s77zB9o1G3gs2JP3nDbZP/Rb1l/BnRR48PxC13UlIGttLZoTzsEmWYc+m6PHpivJYNRvNX0PRPALBhPHrsmVx93dtQD8GMh/GuNKSg4dZpP5t6r7md9ouSf8j/C3+aPW9S0bw5ofwI8LQeNF1VbSa4S5P9meV5plkWRxnfxjacevAr1yPxNoPhHwHpeqXt1La6PHZQLAZwGlZSg2LtXq5HXHHU9BmvPv2lIEtfhxpcEIxHFqUKKPYRSAVxvxskk/4QH4awuStk9srS46bhFEB+hauqU+V1OXvFL59zlhT9r7Pm68z/U1PiD8bPDPjr4f6/penC9sr5khaKO8iVfOxMhIUqzDIAzg49s816B8ItTtNG+Duj3+qXCWtnbQSySyv0VRK/8AnHes/wCOOlaTD8I7hYba2jjsvs/9n7FAEZLqMJ6ZUnp2rzXxPNcR/s2eF0t93ky3u2cjptDzEA+24L+IFZynKk6j3asVGMa1OCWibf5HpVn+0d4Lu9VWxY6hbQtIUF7NbqIfZjhi4B914zzjnHrUciTRrJEyyRuAyspyGB6EGvmKbS/ib4n+H1l4ft/BuiHQnt4WtZoZoxIAMMsikz4DHnJxzub1r3L4Zadq2keBdG0/xJCbfUrWIxSRmVZNqqxCfMpI+7t6Gumm5O6l08rHPVhCKTi/xudbRRRWpzhRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABXG/EvwDF8RvDy6VJef2e8dwk8c/k+btIBBG3cuchj3rsqKmUFNcstioycHzR3OV+HngqPwB4Yg0WK6+2skjyST+V5fmMxznbk4wMDr2rj7X4G2tt8Sj4wXVd0P2t7sWH2TGHYH/lpv7Md33fb3r1qihxTkpdVsUqkkpK++5xfxO+H/wDwsfQINK/tH+zPKuluPN8jzs4Vl243L/e657U/WvhzpviPwVZeGNakkljtIYkiuYgEdXjXaHAOQMjPBzwfxrsaKl04tSTW+/yBVJrls9tjwpf2c5rnTGsNa8aahqVvDFtsIXiYQ2r9N3lmQ546AFfx6V3+l/DXT4Ph5D4M1qY6lZpGyNMqeUxJcuGUZO0gkY5PT8K7aihUoJNW3KdacrXex4X/AMM7XbJHp8vjvVm8Pxzb007yzhUDZAB8zYG/2tnXnFe1adYrpthb2cc1xcLBGE824lMsj47sx5JNWqKqMFBWRM6kqnxBRRRVGYUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQB//2Q=="
    ),
    "pho_3": base64.b64decode(
        "/9j/4AAQSkZJRgABAQEAYABgAAD/2wBDAAQDAwQDAwQEAwQFBAQFBgoHBgYGBg0JCggKDw0QEA8NDw4RExgUERIXEg4PFRwVFxkZGxsbEBQdHx0aHxgaGxr/2wBDAQQFBQYFBgwHBwwaEQ8RGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhoaGhr/wAARCACMAFoDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlZaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD7OooornOUKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKKKKACiiigAooooAKK4vxR8WvB/gzVP7M8S6x9ivhGsnl/ZZpPlPQ5RCO3rV7wl8QfDXjlZz4W1aLUGtz+9TY8bqPXY4DY564x2pJqWxLnFO19TpqKKo3+s2Gly2cOoXcVvNezCG2jZvmlc9lHU+/oOTTK21L1FFZHiXxRpPg/SpNU8R3X2OwjZUaXynkwWOAMICf0pNpasDXorBu/Gmh2GraRpV3feXf6wpexi8mQ+aAM5yFwvH94it6mJNPZhRRRQMKKKKAPB9T0fTtc/aTa11qwtdStf7BDeTdQLKm4Hg7WBGareLdG0rwB8bPA974Zs4dLTUo5or23tUEcbIBjOwcDr2AyVB681r+O/ht46v/iKfFngDWNK0qQ2KWu66yz453fKYnXB4561a8F/CnxCfFQ8VfFLXYNd1a3ha3s4rZcQxoVwW+6gzhmGAo65yT0Bike7ZWs2/xf53RyzjdyjbdrXtt/kzy+6/aA1i8ivtds/FtnpssV1/onhl9IaRZoARjfc7eGIzkAjp1XOBr/ESXVfFXxA+GOq6RrZ05dYgE2n5s0lNgxVCx5/1mSRw2MYrrtF+GvxA8Fw3eheB/EOjWvh2e88+K6urd5Ly1ViNyqmDG3Ax83Xr8ueNr4ifD3xBr2reEtc8Mahp8mraAzZGqKyxz5C/OfKHXK9AAOeoxguK+Bu+jXrtr/X3ESjUlGae7Xy39e3l66md8Rdf17Q71Un+Imh+E7C0sVc5tUur68lOAWNuw+VCQcbM45zntyrfF3xRefAabxNFdxWuu22oLZm6jgQiRQVyxRgVBIbnAx6AdK6K++GHjGHx9eeKtDvPDpuNUtIorl76GSV7GTYEdrfA54BxuIyDgjvWbH8EPEUXwk1PwYL7S5LybVRdQXBkkVGjyv3hsJVvl6DI96lqdpf1rzf5eiLfPzaXtr/6Tp+Pz8ybxpM9x8XvhNNM26SS3kdjjGSUya92rzPXPh3qmp+N/AuuQXFmtpoELR3SO7h3JXHyALg/iRXpldC0TX96X3F01JTbfaP5ahRRRQbhRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFABRRRQAUUUUAFFFFAH/9k="
    ),
}


def _ensure_seed_file(relative_path: str | None, content: bytes) -> None:
    if not relative_path:
        return

    target_path = STORAGE_ROOT / relative_path
    if target_path.exists():
        return

    ensure_directory(target_path.parent)
    target_path.write_bytes(content)


def _ensure_seed_photo_files(seeded_photos: list[dict]) -> None:
    for photo_data in seeded_photos:
        content = _SEED_PHOTO_BYTES.get(photo_data["id"])
        if not content:
            continue

        _ensure_seed_file(photo_data.get("storage_key"), content)
        _ensure_seed_file(photo_data.get("preview_storage_key"), content)
        _ensure_seed_file(photo_data.get("ai_input_storage_key"), content)


async def ensure_dev_seed(session: AsyncSession) -> None:
    # NOVU platform organization (super-admin home)
    novu_org = await session.get(Organization, "org_novu")
    if novu_org is None:
        session.add(
            Organization(
                id="org_novu",
                name="NOVU Platform",
                ico="",
                email="admin@novu.cz",
                phone="",
                default_currency="CZK",
            )
        )

    # NOVU super-admin account
    novu_admin = await session.get(User, "usr_novu_admin")
    if novu_admin is None:
        session.add(
            User(
                id="usr_novu_admin",
                organization_id="org_novu",
                email="admin@novu.cz",
                password_hash=hash_password("NovuAdmin2024!"),
                full_name="NOVU Admin",
                role="superadmin",
                is_active=True,
                is_superadmin=True,
            )
        )

    # Demo customer organization
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
                password_hash=hash_password("demo1234"),
                full_name="Demo Manager",
                role="manager",
                is_active=True,
                is_superadmin=False,
            )
        )

    tech = await session.get(User, "usr_2")
    if tech is None:
        session.add(
            User(
                id="usr_2",
                organization_id="org_1",
                email="tech@novu.local",
                password_hash=hash_password("tech1234"),
                full_name="Demo Technician",
                role="technician",
                is_active=True,
                is_superadmin=False,
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
    _ensure_seed_photo_files(seeded_photos)

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
