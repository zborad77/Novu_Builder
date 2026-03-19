from __future__ import annotations

from collections.abc import Sequence
import json

from app.models import Project, ProjectFinalProposal, ProjectPhoto, ProjectProposalDraft
from app.schemas.project import (
    ProjectFinalProposal as ProjectFinalProposalSchema,
    ProjectProposalDraft as ProjectProposalDraftSchema,
    ProposalDraftField,
    ProposalDraftItem,
    ProposalDraftMaterial,
    ProposalDraftSection,
    ProposalDraftWorkItem,
)


def _scope_defaults(repair_scope: str | None) -> tuple[list[tuple[str, str]], list[tuple[str, str, float, str]], str, str]:
    normalized = (repair_scope or "").lower()

    if "roof" in normalized or "strech" in normalized:
        return (
            [
                ("Vstupni prohlidka strechy", "Overit rozsah znecisteni a pristupove body."),
                ("Cisteni krytiny", "Mechanicke a chemicke odstraneni necistot."),
                ("Aplikace ochranneho nateru", "Pripravit podklad pro finalni cenovou variantu."),
            ],
            [
                ("Cistic strech", "l", 168.0, "Koncentrat pro zakladni cisteni."),
                ("Biocidni ochrana", "l", 214.0, "Ochrana proti dalsimu biologickemu rustu."),
                ("Stresni nater", "kg", 189.0, "Zakladni navrh finalni povrchove vrstvy."),
            ],
            "Stavebniny NOVU Partner",
            "NOVU strechy servis",
        )

    if "facade" in normalized or "fasad" in normalized:
        return (
            [
                ("Vstupni prohlidka fasady", "Zkontrolovat praskliny, degradaci a pristupnost."),
                ("Myti a priprava podkladu", "Ocistit povrch a pripravit plochu pro dalsi zasah."),
                ("Lokalni opravy a finalni nater", "Predpripravit cenovou variantu pro opravy a obnovu."),
            ],
            [
                ("Fasadni penetrace", "l", 96.0, "Zakladni sjednoceni savosti podkladu."),
                ("Fasadni barva", "kg", 142.0, "Dvouvrstvy nater pro exterier."),
                ("Opravna sterka", "kg", 121.0, "Lokalni opravy prasklin a nerovnosti."),
            ],
            "Barvy Laky Partner",
            "NOVU fasady servis",
        )

    return (
        [
            ("Vstupni prohlidka objektu", "Zkontrolovat stav, pristup a potrebne zabezpeceni."),
            ("Priprava podkladu", "Ocistit a pripravit plochu pro navazujici prace."),
            ("Dokoncovaci povrchove prace", "Sestavit prvni navrh cenove nabidky."),
        ],
        [
            ("Zakladni cistic", "l", 84.0, "Prvni priprava povrchu."),
            ("Univerzalni penetrace", "l", 91.0, "Sjednoceni podkladu pred dalsimi vrstvami."),
            ("Povrchovy material", "kg", 136.0, "Zakladni navrh finalniho materialu."),
        ],
        "NOVU material partner",
        "NOVU realizacni tym",
    )


def proposal_draft_changes_from_record(record: ProjectProposalDraft | None) -> dict:
    if record is None:
        return {}

    return {
        "subject": record.subject,
        "summary": record.summary,
        "materialCost": record.material_cost,
        "laborCost": record.labor_cost,
        "amortization": record.amortization,
        "margin": record.margin,
        "recommendedSupplier": record.recommended_supplier,
        "recommendedCompany": record.recommended_company,
    }


def proposal_draft_manual_fields_from_record(record: ProjectProposalDraft | None) -> set[str]:
    if record is None:
        return set()

    manual_fields: set[str] = set()
    if record.subject is not None:
        manual_fields.add("subject")
    if record.summary is not None:
        manual_fields.add("summary")
    if record.material_cost is not None:
        manual_fields.add("materialCost")
    if record.labor_cost is not None:
        manual_fields.add("laborCost")
    if record.amortization is not None:
        manual_fields.add("amortization")
    if record.margin is not None:
        manual_fields.add("margin")
    if record.recommended_supplier is not None:
        manual_fields.add("recommendedSupplier")
    if record.recommended_company is not None:
        manual_fields.add("recommendedCompany")
    return manual_fields


def _normalize_cost_value(value: object) -> float | None:
    if not isinstance(value, (int, float)):
        return None
    return round(max(0.0, float(value)), 2)


def normalize_proposal_patch_payload(payload: dict) -> dict:
    normalized: dict = {}
    string_fields = {
        "subject": "subject",
        "summary": "summary",
        "recommendedSupplier": "recommended_supplier",
        "recommendedCompany": "recommended_company",
    }
    numeric_fields = {
        "materialCost": "material_cost",
        "laborCost": "labor_cost",
        "amortization": "amortization",
        "margin": "margin",
    }

    for payload_field, model_field in string_fields.items():
        if payload_field in payload:
            normalized[model_field] = payload[payload_field]

    for payload_field, model_field in numeric_fields.items():
        if payload_field in payload:
            normalized[model_field] = _normalize_cost_value(payload[payload_field])

    return normalized


def _apply_proposal_overrides(
    draft: ProjectProposalDraftSchema,
    overrides: dict | None,
) -> ProjectProposalDraftSchema:
    if not overrides:
        return draft

    merged = draft.model_copy(deep=True)
    string_fields = ("subject", "summary", "recommendedSupplier", "recommendedCompany")
    numeric_fields = ("materialCost", "laborCost", "amortization", "margin")

    for field_name in string_fields:
        if field_name in overrides and isinstance(overrides[field_name], str):
            setattr(merged, field_name, overrides[field_name])

    for field_name in numeric_fields:
        if field_name in overrides:
            normalized = _normalize_cost_value(overrides[field_name])
            if normalized is not None:
                setattr(merged, field_name, normalized)

    merged.totalPrice = round(
        sum(
            value or 0.0
            for value in (
                merged.materialCost,
                merged.laborCost,
                merged.amortization,
                merged.margin,
            )
        ),
        2,
    )
    return merged


def _format_display_value(value: str | float | int | None, *, unit: str | None = None) -> str | None:
    if value is None:
        return None
    if isinstance(value, float):
        rendered = f"{value:.2f}"
    else:
        rendered = str(value)
    return f"{rendered} {unit}".strip() if unit else rendered


def _build_field(
    *,
    field_id: str,
    label: str,
    value: str | float | int | None,
    source: str,
    editable: bool,
    manual_override: bool,
    unit: str | None = None,
) -> ProposalDraftField:
    return ProposalDraftField(
        id=field_id,
        label=label,
        value=value,
        displayValue=_format_display_value(value, unit=unit),
        source=source,
        editable=editable,
        manualOverride=manual_override,
    )


def _build_sections(
    draft: ProjectProposalDraftSchema,
    *,
    manual_fields: set[str],
) -> list[ProposalDraftSection]:
    overview_fields = [
        _build_field(
            field_id="subject",
            label="Predmet",
            value=draft.subject,
            source="manual" if "subject" in manual_fields else "ai",
            editable=True,
            manual_override="subject" in manual_fields,
        ),
        _build_field(
            field_id="summary",
            label="Shrnuti",
            value=draft.summary,
            source="manual" if "summary" in manual_fields else "ai",
            editable=True,
            manual_override="summary" in manual_fields,
        ),
        _build_field(
            field_id="status",
            label="Stav navrhu",
            value=draft.status,
            source="server",
            editable=False,
            manual_override=False,
        ),
        _build_field(
            field_id="source_photo_count",
            label="Pocet zdrojovych fotek",
            value=draft.sourcePhotoCount,
            source="server",
            editable=False,
            manual_override=False,
        ),
        _build_field(
            field_id="ready_photo_count",
            label="Pripravenych fotek",
            value=draft.readyPhotoCount,
            source="server",
            editable=False,
            manual_override=False,
        ),
    ]

    pricing_fields = [
        _build_field(
            field_id="material_cost",
            label="Cena materialu",
            value=draft.materialCost,
            source="manual" if "materialCost" in manual_fields else "server_calculation",
            editable=True,
            manual_override="materialCost" in manual_fields,
            unit="CZK",
        ),
        _build_field(
            field_id="labor_cost",
            label="Cena prace",
            value=draft.laborCost,
            source="manual" if "laborCost" in manual_fields else "server_calculation",
            editable=True,
            manual_override="laborCost" in manual_fields,
            unit="CZK",
        ),
        _build_field(
            field_id="amortization",
            label="Amortizace",
            value=draft.amortization,
            source="manual" if "amortization" in manual_fields else "server_calculation",
            editable=True,
            manual_override="amortization" in manual_fields,
            unit="CZK",
        ),
        _build_field(
            field_id="margin",
            label="Marze",
            value=draft.margin,
            source="manual" if "margin" in manual_fields else "server_calculation",
            editable=True,
            manual_override="margin" in manual_fields,
            unit="CZK",
        ),
        _build_field(
            field_id="total_price",
            label="Celkem",
            value=draft.totalPrice,
            source="server_total",
            editable=False,
            manual_override=False,
            unit="CZK",
        ),
    ]

    supplier_fields = [
        _build_field(
            field_id="recommended_supplier",
            label="Dodavatel materialu",
            value=draft.recommendedSupplier,
            source="manual" if "recommendedSupplier" in manual_fields else "server_catalog",
            editable=True,
            manual_override="recommendedSupplier" in manual_fields,
        ),
        _build_field(
            field_id="recommended_company",
            label="Realizacni firma",
            value=draft.recommendedCompany,
            source="manual" if "recommendedCompany" in manual_fields else "server_catalog",
            editable=True,
            manual_override="recommendedCompany" in manual_fields,
        ),
    ]

    work_items = [
        ProposalDraftItem(
            id=f"wrk_{index}",
            label=item.name,
            description=item.note,
            source="ai",
            editable=False,
            manualOverride=False,
        )
        for index, item in enumerate(draft.suggestedWorkItems, start=1)
    ]

    material_items = [
        ProposalDraftItem(
            id=f"mat_{index}",
            label=item.name,
            description=item.note,
            quantity=item.quantity,
            unit=item.unit,
            unitPrice=item.unitPrice,
            totalPrice=item.totalPrice,
            source="server_catalog",
            editable=False,
            manualOverride=False,
        )
        for index, item in enumerate(draft.materials, start=1)
    ]

    return [
        ProposalDraftSection(
            id="overview",
            title="Zaklad navrhu",
            kind="fields",
            fields=overview_fields,
        ),
        ProposalDraftSection(
            id="pricing",
            title="Cenovy ramec",
            kind="fields",
            fields=pricing_fields,
        ),
        ProposalDraftSection(
            id="partners",
            title="Dodavatele a realizace",
            kind="fields",
            fields=supplier_fields,
        ),
        ProposalDraftSection(
            id="work_items",
            title="Navrzene kroky",
            kind="items",
            items=work_items,
        ),
        ProposalDraftSection(
            id="materials",
            title="Navrzene materialy",
            kind="items",
            items=material_items,
        ),
    ]


def build_final_proposal_snapshot_payload(draft: ProjectProposalDraftSchema) -> dict:
    return {
        "status": "ready_for_export",
        "draftVersion": draft.version,
        "currency": "CZK",
        "subject": draft.subject,
        "summary": draft.summary,
        "totalPrice": draft.totalPrice,
        "sections": [section.model_dump(mode="json") for section in draft.sections],
    }


def serialize_final_proposal_snapshot(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=True)


def build_final_proposal_from_record(record: ProjectFinalProposal | None) -> ProjectFinalProposalSchema | None:
    if record is None:
        return None

    snapshot: dict = {}
    try:
        snapshot = json.loads(record.snapshot_json)
    except json.JSONDecodeError:
        snapshot = {}

    return ProjectFinalProposalSchema(
        id=record.id,
        status=snapshot.get("status", record.status),
        draftVersion=snapshot.get("draftVersion", record.draft_version),
        currency=snapshot.get("currency", record.currency),
        subject=snapshot.get("subject", record.subject),
        summary=snapshot.get("summary", record.summary),
        totalPrice=snapshot.get("totalPrice", record.total_price),
        sections=[ProposalDraftSection.model_validate(section) for section in snapshot.get("sections", [])],
        createdAt=record.created_at,
    )


def build_project_proposal_draft(
    project: Project,
    photos: Sequence[ProjectPhoto],
    *,
    proposal_record: ProjectProposalDraft | None = None,
) -> ProjectProposalDraftSchema:
    total_photo_count = len(photos)
    ready_photos = [photo for photo in photos if photo.processing_status == "ready"]
    ready_photo_count = len(ready_photos)
    has_pending_processing = any(photo.processing_status in {"uploaded", "processing"} for photo in photos)
    primary_photo = next((photo for photo in ready_photos if photo.is_primary), None)

    scope_label = (project.repair_scope or "obecny zasah").replace("_", " ")
    property_label = (project.property_type or "objekt").replace("_", " ")
    location_label = project.address_label or "bez adresy"

    overrides = proposal_draft_changes_from_record(proposal_record)
    manual_fields = proposal_draft_manual_fields_from_record(proposal_record)
    draft_version = proposal_record.version if proposal_record else 1

    if total_photo_count == 0:
        draft = _apply_proposal_overrides(ProjectProposalDraftSchema(
            status="waiting_for_photos",
            version=draft_version,
            sourcePhotoCount=0,
            readyPhotoCount=0,
            primaryPhotoId=None,
            subject="Ceka se na fotodokumentaci",
            summary="Zakazka zatim nema zadne fotky. Pro prvni navrh nabidky nahraj alespon 3 fotografie objektu.",
            suggestedWorkItems=[],
            materials=[],
            materialCost=0.0,
            laborCost=0.0,
            amortization=0.0,
            margin=0.0,
            recommendedSupplier=None,
            recommendedCompany=None,
            totalPrice=0.0,
        ), overrides)
        draft.sections = _build_sections(draft, manual_fields=manual_fields)
        return draft

    if has_pending_processing:
        draft = _apply_proposal_overrides(ProjectProposalDraftSchema(
            status="processing_photos",
            version=draft_version,
            sourcePhotoCount=total_photo_count,
            readyPhotoCount=ready_photo_count,
            primaryPhotoId=primary_photo.id if primary_photo else None,
            subject=f"Zpracovava se navrh pro {scope_label}",
            summary="Fotky jsou na serveru a probiha jejich zpracovani. Navrh nabidky se doplni po dokonceni derivatu.",
            suggestedWorkItems=[],
            materials=[],
            materialCost=0.0,
            laborCost=0.0,
            amortization=0.0,
            margin=0.0,
            recommendedSupplier=None,
            recommendedCompany=None,
            totalPrice=0.0,
        ), overrides)
        draft.sections = _build_sections(draft, manual_fields=manual_fields)
        return draft

    work_item_defaults, material_defaults, supplier_name, company_name = _scope_defaults(project.repair_scope)
    estimated_area_sqm = round(14.0 + ready_photo_count * 11.5, 1)

    if ready_photo_count < 3:
        draft = _apply_proposal_overrides(ProjectProposalDraftSchema(
            status="awaiting_more_photos",
            version=draft_version,
            sourcePhotoCount=total_photo_count,
            readyPhotoCount=ready_photo_count,
            primaryPhotoId=primary_photo.id if primary_photo else None,
            subject=f"Predbezny navrh pro {scope_label} na {location_label}",
            summary=(
                f"Server uz pripravil zakladni navrh, ale pro spolehlivejsi odhad doporucuje alespon 3 hotove fotky. "
                f"Zatim jsou pripraveny {ready_photo_count}."
            ),
            suggestedWorkItems=[
                ProposalDraftWorkItem(name=item_name, note=item_note)
                for item_name, item_note in work_item_defaults[:2]
            ],
            materials=[],
            materialCost=0.0,
            laborCost=0.0,
            amortization=0.0,
            margin=0.0,
            recommendedSupplier=supplier_name,
            recommendedCompany=company_name,
            totalPrice=0.0,
        ), overrides)
        draft.sections = _build_sections(draft, manual_fields=manual_fields)
        return draft

    material_items: list[ProposalDraftMaterial] = []
    quantity_factor = max(1.0, estimated_area_sqm / 10.0)
    for index, (material_name, unit, unit_price, note) in enumerate(material_defaults, start=1):
        quantity = round(quantity_factor * (0.75 + index * 0.35), 1)
        total_price = round(quantity * unit_price, 2)
        material_items.append(
            ProposalDraftMaterial(
                name=material_name,
                quantity=quantity,
                unit=unit,
                unitPrice=unit_price,
                totalPrice=total_price,
                note=note,
            )
        )

    material_cost = round(sum(item.totalPrice for item in material_items), 2)
    labor_hours = estimated_area_sqm * 0.42
    labor_cost = round(labor_hours * 425.0, 2)
    amortization = round(max(350.0, labor_cost * 0.08), 2)
    margin = round((material_cost + labor_cost + amortization) * 0.18, 2)
    total_price = round(material_cost + labor_cost + amortization + margin, 2)

    draft = _apply_proposal_overrides(ProjectProposalDraftSchema(
        status="ready",
        version=draft_version,
        sourcePhotoCount=total_photo_count,
        readyPhotoCount=ready_photo_count,
        primaryPhotoId=primary_photo.id if primary_photo else None,
        subject=f"Navrh cenove nabidky pro {scope_label} - {property_label}",
        summary=(
            f"Server pripravil prvni navrh z {ready_photo_count} hotovych fotek. "
            f"Odhadovana plocha pro naceneni je {estimated_area_sqm:.1f} m2."
        ),
        suggestedWorkItems=[
            ProposalDraftWorkItem(name=item_name, note=item_note)
            for item_name, item_note in work_item_defaults
        ],
        materials=material_items,
        materialCost=material_cost,
        laborCost=labor_cost,
        amortization=amortization,
        margin=margin,
        recommendedSupplier=supplier_name,
        recommendedCompany=company_name,
        totalPrice=total_price,
    ), overrides)
    draft.sections = _build_sections(draft, manual_fields=manual_fields)
    return draft
