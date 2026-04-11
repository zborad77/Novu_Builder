from __future__ import annotations

import json
import unicodedata
from datetime import UTC, datetime, timedelta
from fastapi import HTTPException
from io import BytesIO
from pathlib import Path
from uuid import uuid4
from xml.sax.saxutils import escape
from zipfile import ZIP_DEFLATED, ZipFile

import structlog

from app.core.backpressure import (
    collect_backpressure_snapshot,
    effective_backpressure_max_queued_jobs,
    ensure_heavy_intake_capacity,
    heavy_job_priority_for_type,
    require_worker_capacity,
)
from app.core.config import get_settings
from app.models import ProjectExport
from app.repositories.export_repository import ExportRepository
from app.schemas.export import ExportRead
from app.schemas.project import ProjectDetail, ProposalDraftField, ProposalDraftItem, ProposalDraftSection
from app.storage.backend import (
    delete_storage_file,
    generate_presigned_url,
    read_storage_file,
    sanitize_filename,
    storage_key_exists,
    write_storage_file,
)
from app.worker.heavy_queue import HeavyJobQueueCapacityExceededError, enqueue_heavy_job

logger = structlog.get_logger(__name__)

# Export metadata is authoritative in the database; storage holds only artifacts.
def _default_export_expires_at(created_at: datetime) -> datetime:
    settings = get_settings()
    return created_at + timedelta(days=settings.export_ttl_days)


def _as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)

def _to_export_read(export: ProjectExport) -> ExportRead:
    """Render API export metadata from the authoritative DB export record."""
    return ExportRead(
        id=export.id,
        caseId=export.project_id,
        exportType=export.export_type,
        status=export.status,
        fileName=export.file_name,
        storageKey=export.storage_key,
        downloadUrl=(
            generate_presigned_url(export.storage_key)
            if export.status == "completed" and export.storage_key
            else None
        ),
        createdAt=_as_utc(export.created_at),
        completedAt=_as_utc(export.completed_at),
        expiresAt=_as_utc(export.expires_at),
    )


def _analysis_lines(case_detail: ProjectDetail) -> list[str]:
    a = case_detail.latestAnalysis
    if not a:
        return []
    lines = [
        "",
        "--- Vysledky AI analyzy ---",
        f"Typ objektu: {a.get('objectType') or '-'}",
        f"Stav povrchu: {a.get('surfaceCondition') or '-'}",
        f"Doporuceny rozsah: {a.get('recommendedScope') or '-'}",
    ]
    area = a.get("estimatedAreaSqm")
    confidence = a.get("areaConfidence")
    if area is not None:
        conf_str = f"  (spolehlivost: {confidence:.0%})" if confidence is not None else ""
        lines.append(f"Odhadovana plocha: {area:.1f} m2{conf_str}")
    duration = a.get("estimatedDurationDays")
    labor = a.get("laborHoursTotal")
    if duration is not None:
        lines.append(f"Odhadovana doba: {duration} dni")
    if labor is not None:
        lines.append(f"Celkem clovekohod: {labor:.1f} h")

    workflow_steps = a.get("workflowSteps") or []
    if workflow_steps:
        lines.append("")
        lines.append("Technologicky postup:")
        for idx, step in enumerate(workflow_steps, start=1):
            if isinstance(step, str):
                lines.append(f"  {idx}. {step}")
            else:
                step_num = step.get("step", idx)
                name = step.get("name", "")
                hours = step.get("estimatedHours")
                desc = step.get("description", "")
                hours_str = f" ({hours} h)" if hours is not None else ""
                lines.append(f"  {step_num}. {name}{hours_str}")
                if desc:
                    lines.append(f"     {desc}")

    materials = a.get("materials") or []
    if materials:
        lines.append("")
        lines.append("Potrebne materialy:")
        for mat in materials:
            name = mat.get("name", "")
            qty = mat.get("quantity")
            unit = mat.get("unit", "")
            total = mat.get("totalPrice")
            qty_str = f" {qty:.1f} {unit}" if qty is not None else ""
            price_str = f" = {total:.2f} CZK" if total is not None else ""
            lines.append(f"  - {name}{qty_str}{price_str}")

    return lines


def _quote_variant_lines(case_detail: ProjectDetail) -> list[str]:
    variants = case_detail.quoteVariants
    if not variants:
        return []
    lines = ["", "--- Cenove varianty ---"]
    for v in variants:
        vtype = v.get("variantType", "")
        total = v.get("totalIncVat") or v.get("totalExVat")
        labor = v.get("laborCost")
        material = v.get("materialCost")
        total_str = f"{total:.2f} CZK" if total is not None else "-"
        lines.append(f"  {vtype.upper()}: celkem {total_str}")
        if labor is not None:
            lines.append(f"    Prace: {labor:.2f} CZK")
        if material is not None:
            lines.append(f"    Material: {material:.2f} CZK")
    return lines


def _itemized_price_lines(case_detail: ProjectDetail) -> list[str]:
    """Polozkovany soupis praci, materialu a dopravy."""
    draft = case_detail.proposalDraft
    if draft is None:
        return []

    lines = ["", "=" * 60, "POLOZKOVANY SOUPIS", "=" * 60]

    # Práce
    lines.append("")
    lines.append("PRACE:")
    work_items = draft.suggestedWorkItems or []
    if work_items:
        for idx, item in enumerate(work_items, start=1):
            note = f" - {item.note}" if item.note else ""
            lines.append(f"  {idx}. {item.name}{note}")
    else:
        lines.append("  (viz popis zakazky)")
    labor_total = draft.laborCost or 0.0
    lines.append(f"  Prace celkem: {labor_total:,.2f} CZK")

    # Materiály
    lines.append("")
    lines.append("MATERIALY:")
    materials = draft.materials or []
    if materials:
        for mat in materials:
            qty_str = f"{mat.quantity:.1f} {mat.unit}" if mat.quantity is not None else ""
            price_str = f"x {mat.unitPrice:.2f}" if mat.unitPrice is not None else ""
            total_str = f"= {mat.totalPrice:.2f} CZK" if mat.totalPrice is not None else ""
            lines.append(f"  {mat.name:<30} {qty_str:<12} {price_str:<14} {total_str}")
    material_total = draft.materialCost or 0.0
    lines.append(f"  Material celkem: {material_total:,.2f} CZK")

    # Doprava
    transport_total = draft.transportCost or 0.0
    lines.append("")
    lines.append("DOPRAVA A OSTATNI:")
    lines.append(f"  Doprava celkem: {transport_total:,.2f} CZK")

    # Amortizace + marže
    amortization = draft.amortization or 0.0
    margin_pct = draft.margin or 0.0
    base = labor_total + material_total + transport_total + amortization
    margin_amount = round(base * margin_pct / 100.0, 2)
    subtotal = round(base + margin_amount, 2)
    lines.append("")
    lines.append(f"Amortizace:        {amortization:,.2f} CZK")
    lines.append(f"Marze ({margin_pct:.0f} %):      {margin_amount:,.2f} CZK")

    # Souhrn
    vat = round(subtotal * 0.21, 2)
    total_inc_vat = round(subtotal + vat, 2)
    lines.append("")
    lines.append("-" * 50)
    lines.append(f"Celkem bez DPH:    {subtotal:,.2f} CZK")
    lines.append(f"DPH 21 %:          {vat:,.2f} CZK")
    lines.append(f"CELKEM S DPH:      {total_inc_vat:,.2f} CZK")
    lines.append("=" * 60)
    return lines


def _proposal_lines(case_detail: ProjectDetail) -> list[str]:
    final_proposal = case_detail.finalProposal
    assert final_proposal is not None

    lines = [
        "NOVU - Cenova nabidka",
        case_detail.title or "Zakazka",
        final_proposal.subject or "Bez predmetu",
        final_proposal.summary or "Bez shrnuti.",
    ]

    lines.extend(_itemized_price_lines(case_detail))
    lines.extend(_analysis_lines(case_detail))
    return lines


def _proposal_draft_lines(case_detail: ProjectDetail) -> list[str]:
    proposal_draft = case_detail.proposalDraft
    assert proposal_draft is not None

    lines = [
        "NOVU - Pracovni navrh nabidky",
        case_detail.title or "Zakazka",
        proposal_draft.subject or "Bez predmetu",
        proposal_draft.summary or "Bez shrnuti.",
        f"Celkem: {proposal_draft.totalPrice:.2f} CZK" if proposal_draft.totalPrice is not None else "Celkem: -",
        f"Stav navrhu: {proposal_draft.status}",
        f"Zdrojovy draft: verze {proposal_draft.version}",
    ]

    for section in proposal_draft.sections:
        lines.append("")
        lines.append(section.title)
        if section.kind == "fields":
            if not section.fields:
                lines.append("Bez polozek.")
            for field in section.fields:
                lines.append(_field_line(field))
        else:
            if not section.items:
                lines.append("Bez polozek.")
            for item in section.items:
                lines.append("- " + _item_line(item))

    lines.extend(_analysis_lines(case_detail))
    lines.extend(_quote_variant_lines(case_detail))
    return lines


def _paragraph_xml(text: str, *, style: str | None = None, bold: bool = False) -> str:
    escaped_text = escape(text or "")
    style_xml = f"<w:pStyle w:val=\"{style}\"/>" if style else ""
    bold_xml = "<w:b/>" if bold else ""
    return (
        "<w:p>"
        "<w:pPr>"
        f"{style_xml}"
        "</w:pPr>"
        "<w:r>"
        "<w:rPr>"
        f"{bold_xml}"
        "</w:rPr>"
        f"<w:t xml:space=\"preserve\">{escaped_text}</w:t>"
        "</w:r>"
        "</w:p>"
    )


def _field_line(field: ProposalDraftField) -> str:
    value = field.displayValue or ("" if field.value is None else str(field.value))
    return f"{field.label}: {value or '-'}"


def _item_line(item: ProposalDraftItem) -> str:
    parts = [item.label]
    if item.quantity is not None and item.unit:
        parts.append(f"{item.quantity:.1f} {item.unit}")
    if item.totalPrice is not None:
        parts.append(f"{item.totalPrice:.2f} CZK")
    line = " | ".join(parts)
    if item.description:
        line += f" - {item.description}"
    return line


def _section_paragraphs(section: ProposalDraftSection) -> list[str]:
    paragraphs = [_paragraph_xml(section.title, style="Heading2")]
    if section.kind == "fields":
        for field in section.fields:
            paragraphs.append(_paragraph_xml(_field_line(field)))
    else:
        if not section.items:
            paragraphs.append(_paragraph_xml("Bez polozek."))
        for item in section.items:
            paragraphs.append(_paragraph_xml("- " + _item_line(item)))
    return paragraphs


def _analysis_paragraphs(case_detail: ProjectDetail) -> list[str]:
    a = case_detail.latestAnalysis
    if not a:
        return []
    paragraphs = [_paragraph_xml("Vysledky AI analyzy", style="Heading2")]
    paragraphs.append(_paragraph_xml(f"Typ objektu: {a.get('objectType') or '-'}"))
    paragraphs.append(_paragraph_xml(f"Stav povrchu: {a.get('surfaceCondition') or '-'}"))
    paragraphs.append(_paragraph_xml(f"Doporuceny rozsah: {a.get('recommendedScope') or '-'}"))
    area = a.get("estimatedAreaSqm")
    confidence = a.get("areaConfidence")
    if area is not None:
        conf_str = f"  (spolehlivost: {confidence:.0%})" if confidence is not None else ""
        paragraphs.append(_paragraph_xml(f"Odhadovana plocha: {area:.1f} m2{conf_str}"))
    duration = a.get("estimatedDurationDays")
    labor = a.get("laborHoursTotal")
    if duration is not None:
        paragraphs.append(_paragraph_xml(f"Odhadovana doba: {duration} dni"))
    if labor is not None:
        paragraphs.append(_paragraph_xml(f"Celkem clovekohod: {labor:.1f} h"))

    workflow_steps = a.get("workflowSteps") or []
    if workflow_steps:
        paragraphs.append(_paragraph_xml("Technologicky postup", style="Heading2"))
        for idx, step in enumerate(workflow_steps, start=1):
            if isinstance(step, str):
                paragraphs.append(_paragraph_xml(f"{idx}. {step}", bold=True))
            else:
                step_num = step.get("step", idx)
                name = step.get("name", "")
                hours = step.get("estimatedHours")
                desc = step.get("description", "")
                hours_str = f" ({hours} h)" if hours is not None else ""
                paragraphs.append(_paragraph_xml(f"{step_num}. {name}{hours_str}", bold=True))
                if desc:
                    paragraphs.append(_paragraph_xml(desc))

    materials = a.get("materials") or []
    if materials:
        paragraphs.append(_paragraph_xml("Potrebne materialy", style="Heading2"))
        for mat in materials:
            name = mat.get("name", "")
            qty = mat.get("quantity")
            unit = mat.get("unit", "")
            total = mat.get("totalPrice")
            qty_str = f" {qty:.1f} {unit}" if qty is not None else ""
            price_str = f" = {total:.2f} CZK" if total is not None else ""
            paragraphs.append(_paragraph_xml(f"- {name}{qty_str}{price_str}"))

    return paragraphs


def _quote_variant_paragraphs(case_detail: ProjectDetail) -> list[str]:
    variants = case_detail.quoteVariants
    if not variants:
        return []
    paragraphs = [_paragraph_xml("Cenove varianty", style="Heading2")]
    for v in variants:
        vtype = v.get("variantType", "")
        total = v.get("totalIncVat") or v.get("totalExVat")
        labor = v.get("laborCost")
        material = v.get("materialCost")
        total_str = f"{total:.2f} CZK" if total is not None else "-"
        paragraphs.append(_paragraph_xml(f"{vtype.upper()}: celkem {total_str}", bold=True))
        if labor is not None:
            paragraphs.append(_paragraph_xml(f"  Prace: {labor:.2f} CZK"))
        if material is not None:
            paragraphs.append(_paragraph_xml(f"  Material: {material:.2f} CZK"))
    return paragraphs


def _itemized_price_paragraphs(case_detail: ProjectDetail) -> list[str]:
    """Polozkovany soupis praci, materialu a dopravy pro DOCX."""
    draft = case_detail.proposalDraft
    if draft is None:
        return []

    paragraphs = [_paragraph_xml("Polozkovany soupis", style="Heading1")]

    # Práce
    paragraphs.append(_paragraph_xml("Prace", style="Heading2"))
    work_items = draft.suggestedWorkItems or []
    for idx, item in enumerate(work_items, start=1):
        note = f" - {item.note}" if item.note else ""
        paragraphs.append(_paragraph_xml(f"{idx}. {item.name}{note}"))
    if not work_items:
        paragraphs.append(_paragraph_xml("(viz popis zakazky)"))
    labor_total = draft.laborCost or 0.0
    paragraphs.append(_paragraph_xml(f"Prace celkem: {labor_total:,.2f} CZK", bold=True))

    # Materiály
    paragraphs.append(_paragraph_xml("Materialy", style="Heading2"))
    materials = draft.materials or []
    for mat in materials:
        qty_str = f"{mat.quantity:.1f} {mat.unit}" if mat.quantity is not None else ""
        price_str = f"x {mat.unitPrice:.2f}" if mat.unitPrice is not None else ""
        total_str = f"= {mat.totalPrice:.2f} CZK" if mat.totalPrice is not None else ""
        paragraphs.append(_paragraph_xml(f"{mat.name}  {qty_str}  {price_str}  {total_str}"))
    if not materials:
        paragraphs.append(_paragraph_xml("(materialy budou doplneny)"))
    material_total = draft.materialCost or 0.0
    paragraphs.append(_paragraph_xml(f"Material celkem: {material_total:,.2f} CZK", bold=True))

    # Doprava
    transport_total = draft.transportCost or 0.0
    paragraphs.append(_paragraph_xml("Doprava a ostatni", style="Heading2"))
    paragraphs.append(_paragraph_xml(f"Doprava: {transport_total:,.2f} CZK"))

    # Souhrn
    amortization = draft.amortization or 0.0
    margin_pct = draft.margin or 0.0
    base = labor_total + material_total + transport_total + amortization
    margin_amount = round(base * margin_pct / 100.0, 2)
    subtotal = round(base + margin_amount, 2)
    vat = round(subtotal * 0.21, 2)
    total_inc_vat = round(subtotal + vat, 2)
    paragraphs.append(_paragraph_xml("Souhrn cen", style="Heading2"))
    paragraphs.append(_paragraph_xml(f"Amortizace: {amortization:,.2f} CZK"))
    paragraphs.append(_paragraph_xml(f"Marze ({margin_pct:.0f} %): {margin_amount:,.2f} CZK"))
    paragraphs.append(_paragraph_xml(f"Celkem bez DPH: {subtotal:,.2f} CZK", bold=True))
    paragraphs.append(_paragraph_xml(f"DPH 21 %: {vat:,.2f} CZK"))
    paragraphs.append(_paragraph_xml(f"CELKEM S DPH: {total_inc_vat:,.2f} CZK", bold=True))
    return paragraphs


def _build_document_xml(case_detail: ProjectDetail) -> str:
    final_proposal = case_detail.finalProposal
    assert final_proposal is not None

    paragraphs = [
        _paragraph_xml("NOVU - Cenova nabidka", style="Title"),
        _paragraph_xml(case_detail.title or "Zakazka", style="Heading1"),
        _paragraph_xml(final_proposal.subject or "Bez predmetu", bold=True),
        _paragraph_xml(final_proposal.summary or "Bez shrnuti."),
    ]

    paragraphs.extend(_itemized_price_paragraphs(case_detail))
    paragraphs.extend(_analysis_paragraphs(case_detail))

    body = "".join(paragraphs) + (
        "<w:sectPr>"
        "<w:pgSz w:w=\"11906\" w:h=\"16838\"/>"
        "<w:pgMar w:top=\"1440\" w:right=\"1440\" w:bottom=\"1440\" w:left=\"1440\" w:header=\"708\" w:footer=\"708\" w:gutter=\"0\"/>"
        "</w:sectPr>"
    )

    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<w:document "
        "xmlns:wpc=\"http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas\" "
        "xmlns:mc=\"http://schemas.openxmlformats.org/markup-compatibility/2006\" "
        "xmlns:o=\"urn:schemas-microsoft-com:office:office\" "
        "xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\" "
        "xmlns:m=\"http://schemas.openxmlformats.org/officeDocument/2006/math\" "
        "xmlns:v=\"urn:schemas-microsoft-com:vml\" "
        "xmlns:wp14=\"http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing\" "
        "xmlns:wp=\"http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing\" "
        "xmlns:w10=\"urn:schemas-microsoft-com:office:word\" "
        "xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\" "
        "xmlns:w14=\"http://schemas.microsoft.com/office/word/2010/wordml\" "
        "xmlns:wpg=\"http://schemas.microsoft.com/office/word/2010/wordprocessingGroup\" "
        "xmlns:wpi=\"http://schemas.microsoft.com/office/word/2010/wordprocessingInk\" "
        "xmlns:wne=\"http://schemas.microsoft.com/office/word/2006/wordml\" "
        "xmlns:wps=\"http://schemas.microsoft.com/office/word/2010/wordprocessingShape\" "
        "mc:Ignorable=\"w14 wp14\">"
        f"<w:body>{body}</w:body>"
        "</w:document>"
    )


def _build_proposal_document_xml(case_detail: ProjectDetail) -> str:
    proposal_draft = case_detail.proposalDraft
    assert proposal_draft is not None

    paragraphs = [
        _paragraph_xml("NOVU - Pracovni navrh nabidky", style="Title"),
        _paragraph_xml(case_detail.title or "Zakazka", style="Heading1"),
        _paragraph_xml(proposal_draft.subject or "Bez predmetu", bold=True),
        _paragraph_xml(proposal_draft.summary or "Bez shrnuti."),
    ]

    paragraphs.extend(_itemized_price_paragraphs(case_detail))
    paragraphs.extend(_analysis_paragraphs(case_detail))

    body = "".join(paragraphs) + (
        "<w:sectPr>"
        "<w:pgSz w:w=\"11906\" w:h=\"16838\"/>"
        "<w:pgMar w:top=\"1440\" w:right=\"1440\" w:bottom=\"1440\" w:left=\"1440\" w:header=\"708\" w:footer=\"708\" w:gutter=\"0\"/>"
        "</w:sectPr>"
    )

    return (
        "<?xml version=\"1.0\" encoding=\"UTF-8\" standalone=\"yes\"?>"
        "<w:document "
        "xmlns:wpc=\"http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas\" "
        "xmlns:mc=\"http://schemas.openxmlformats.org/markup-compatibility/2006\" "
        "xmlns:o=\"urn:schemas-microsoft-com:office:office\" "
        "xmlns:r=\"http://schemas.openxmlformats.org/officeDocument/2006/relationships\" "
        "xmlns:m=\"http://schemas.openxmlformats.org/officeDocument/2006/math\" "
        "xmlns:v=\"urn:schemas-microsoft-com:vml\" "
        "xmlns:wp14=\"http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing\" "
        "xmlns:wp=\"http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing\" "
        "xmlns:w10=\"urn:schemas-microsoft-com:office:word\" "
        "xmlns:w=\"http://schemas.openxmlformats.org/wordprocessingml/2006/main\" "
        "xmlns:w14=\"http://schemas.microsoft.com/office/word/2010/wordml\" "
        "xmlns:wpg=\"http://schemas.microsoft.com/office/word/2010/wordprocessingGroup\" "
        "xmlns:wpi=\"http://schemas.microsoft.com/office/word/2010/wordprocessingInk\" "
        "xmlns:wne=\"http://schemas.microsoft.com/office/word/2006/wordml\" "
        "xmlns:wps=\"http://schemas.microsoft.com/office/word/2010/wordprocessingShape\" "
        "mc:Ignorable=\"w14 wp14\">"
        f"<w:body>{body}</w:body>"
        "</w:document>"
    )


def _build_docx_bytes(case_detail: ProjectDetail) -> bytes:
    now = datetime.now(UTC).replace(microsecond=0)
    core_created = now.isoformat().replace("+00:00", "Z")
    document_xml = _build_document_xml(case_detail)

    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>"""

    root_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""

    document_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

    styles_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Title">
    <w:name w:val="Title"/>
    <w:basedOn w:val="Normal"/>
    <w:qFormat/>
    <w:rPr><w:b/><w:sz w:val="36"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="heading 1"/>
    <w:basedOn w:val="Normal"/>
    <w:qFormat/>
    <w:rPr><w:b/><w:sz w:val="28"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading2">
    <w:name w:val="heading 2"/>
    <w:basedOn w:val="Normal"/>
    <w:qFormat/>
    <w:rPr><w:b/><w:sz w:val="24"/></w:rPr>
  </w:style>
</w:styles>"""

    core_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>{escape(case_detail.finalProposal.subject or case_detail.title or "Nabidka")}</dc:title>
  <dc:creator>NOVU Builder</dc:creator>
  <cp:lastModifiedBy>NOVU Builder</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{core_created}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{core_created}</dcterms:modified>
</cp:coreProperties>"""

    app_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>NOVU Builder</Application>
</Properties>"""

    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("word/_rels/document.xml.rels", document_rels)
        archive.writestr("word/styles.xml", styles_xml)
        archive.writestr("docProps/core.xml", core_xml)
        archive.writestr("docProps/app.xml", app_xml)
    return buffer.getvalue()


def _build_proposal_docx_bytes(case_detail: ProjectDetail) -> bytes:
    now = datetime.now(UTC).replace(microsecond=0)
    core_created = now.isoformat().replace("+00:00", "Z")
    document_xml = _build_proposal_document_xml(case_detail)

    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
  <Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
  <Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>
  <Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>
</Types>"""

    root_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
  <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>
  <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>
</Relationships>"""

    document_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""

    styles_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:type="paragraph" w:default="1" w:styleId="Normal">
    <w:name w:val="Normal"/>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Title">
    <w:name w:val="Title"/>
    <w:basedOn w:val="Normal"/>
    <w:qFormat/>
    <w:rPr><w:b/><w:sz w:val="36"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading1">
    <w:name w:val="heading 1"/>
    <w:basedOn w:val="Normal"/>
    <w:qFormat/>
    <w:rPr><w:b/><w:sz w:val="28"/></w:rPr>
  </w:style>
  <w:style w:type="paragraph" w:styleId="Heading2">
    <w:name w:val="heading 2"/>
    <w:basedOn w:val="Normal"/>
    <w:qFormat/>
    <w:rPr><w:b/><w:sz w:val="24"/></w:rPr>
  </w:style>
</w:styles>"""

    core_xml = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:dcmitype="http://purl.org/dc/dcmitype/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:title>{escape(case_detail.proposalDraft.subject or case_detail.title or "Pracovni navrh nabidky")}</dc:title>
  <dc:creator>NOVU Builder</dc:creator>
  <cp:lastModifiedBy>NOVU Builder</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">{core_created}</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">{core_created}</dcterms:modified>
</cp:coreProperties>"""

    app_xml = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">
  <Application>NOVU Builder</Application>
</Properties>"""

    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", root_rels)
        archive.writestr("word/document.xml", document_xml)
        archive.writestr("word/_rels/document.xml.rels", document_rels)
        archive.writestr("word/styles.xml", styles_xml)
        archive.writestr("docProps/core.xml", core_xml)
        archive.writestr("docProps/app.xml", app_xml)
    return buffer.getvalue()


def _to_winansi(text: str) -> str:
    """Convert text to cp1252 (WinAnsiEncoding), replacing chars outside the range."""
    result = []
    for char in text:
        try:
            char.encode("cp1252")
            result.append(char)
        except (UnicodeEncodeError, UnicodeDecodeError):
            # Try to strip diacritics via NFD decomposition
            decomposed = unicodedata.normalize("NFD", char)
            base = decomposed[0]
            try:
                base.encode("cp1252")
                result.append(base)
            except (UnicodeEncodeError, UnicodeDecodeError):
                result.append("?")
    return "".join(result)


def _escape_pdf_text(text: str) -> str:
    safe = _to_winansi(text)
    return safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _build_pdf_bytes(case_detail: ProjectDetail) -> bytes:
    lines = _proposal_lines(case_detail)
    lines_per_page = 42
    page_width = 595
    page_height = 842
    left_margin = 50
    top_margin = 790
    line_height = 16

    def build_content_stream(page_lines: list[str]) -> bytes:
        commands = ["BT", "/F1 11 Tf"]
        y = top_margin
        for line in page_lines:
            safe_line = _escape_pdf_text(line)
            commands.append(f"1 0 0 1 {left_margin} {y} Tm ({safe_line}) Tj")
            y -= line_height
        commands.append("ET")
        return "\n".join(commands).encode("cp1252", errors="replace")

    pages = [lines[index:index + lines_per_page] for index in range(0, max(1, len(lines)), lines_per_page)]
    pdf = BytesIO()
    offsets: list[int] = []

    def write_line(text: str) -> None:
        pdf.write(text.encode("latin-1"))

    write_line("%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")

    content_object_ids: list[int] = []
    page_object_ids: list[int] = []
    next_object_id = 4
    for _ in pages:
        content_object_ids.append(next_object_id)
        next_object_id += 1
        page_object_ids.append(next_object_id)
        next_object_id += 1

    total_objects = next_object_id - 1

    offsets.append(pdf.tell())
    write_line("1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")

    kids = " ".join(f"{page_id} 0 R" for page_id in page_object_ids)
    offsets.append(pdf.tell())
    write_line(f"2 0 obj\n<< /Type /Pages /Kids [ {kids} ] /Count {len(page_object_ids)} >>\nendobj\n")

    offsets.append(pdf.tell())
    write_line("3 0 obj\n<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>\nendobj\n")

    for page_lines, content_id, page_id in zip(pages, content_object_ids, page_object_ids, strict=True):
        content_bytes = build_content_stream(page_lines)
        offsets.append(pdf.tell())
        write_line(f"{content_id} 0 obj\n<< /Length {len(content_bytes)} >>\nstream\n")
        pdf.write(content_bytes)
        write_line("\nendstream\nendobj\n")

        offsets.append(pdf.tell())
        write_line(
            f"{page_id} 0 obj\n"
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page_width} {page_height}] "
            f"/Resources << /Font << /F1 3 0 R >> >> /Contents {content_id} 0 R >>\n"
            "endobj\n"
        )

    xref_offset = pdf.tell()
    write_line(f"xref\n0 {total_objects + 1}\n")
    write_line("0000000000 65535 f \n")
    for offset in offsets:
        write_line(f"{offset:010d} 00000 n \n")
    write_line(
        f"trailer\n<< /Size {total_objects + 1} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF"
    )
    return pdf.getvalue()


async def _build_case_zip_bytes(case_detail: ProjectDetail) -> bytes:
    """Sestaví ZIP archiv zakázky: project.json + analysis.json + photos/."""
    buffer = BytesIO()
    with ZipFile(buffer, "w", compression=ZIP_DEFLATED) as archive:
        # project.json
        project_data = case_detail.model_dump(mode="json")
        archive.writestr("project.json", json.dumps(project_data, ensure_ascii=False, indent=2))

        # analysis.json
        if case_detail.latestAnalysis:
            archive.writestr(
                "analysis.json",
                json.dumps(case_detail.latestAnalysis, ensure_ascii=False, indent=2),
            )

        # photos/
        for photo in case_detail.photos:
            storage_key = photo.get("storageKey") if isinstance(photo, dict) else getattr(photo, "storageKey", None)
            if not storage_key:
                raise FileNotFoundError("Case ZIP export requires a valid photo storageKey for every included photo.")
            photo_bytes = await read_storage_file(relative_storage_key=storage_key)
            if photo_bytes is None:
                raise FileNotFoundError(f"Case ZIP export is missing storage object: {storage_key}")
            archive_name = f"photos/{Path(storage_key).name}"
            archive.writestr(archive_name, photo_bytes)

    return buffer.getvalue()


class ExportService:
    def __init__(self, repository: ExportRepository, *, work_queue=None):
        self.repository = repository
        self.work_queue = work_queue

    async def _artifact_exists(self, storage_key: str | None) -> bool:
        if not storage_key:
            return False
        try:
            return await storage_key_exists(relative_storage_key=storage_key)
        except Exception as exc:
            logger.error(
                "export.artifact_probe_failed",
                storage_key=storage_key,
                error=str(exc),
                exc_info=True,
            )
            return False

    async def _create_export_record(
        self,
        *,
        export_id: str,
        project_id: str,
        export_type: str,
        status: str,
        file_name: str,
        storage_key: str | None,
        created_at: datetime,
        completed_at: datetime | None,
    ) -> ExportRead:
        export = await self.repository.create(
            export_id=export_id,
            project_id=project_id,
            export_type=export_type,
            status=status,
            file_name=file_name,
            storage_key=storage_key,
            created_at=created_at,
            completed_at=completed_at,
            expires_at=_default_export_expires_at(created_at),
        )
        return _to_export_read(export)

    async def _create_pending_export_record(
        self,
        *,
        export_id: str,
        project_id: str,
        export_type: str,
        file_name: str,
        created_at: datetime,
    ) -> ProjectExport:
        return await self.repository.create(
            export_id=export_id,
            project_id=project_id,
            export_type=export_type,
            status="pending",
            file_name=file_name,
            storage_key=None,
            created_at=created_at,
            completed_at=None,
            expires_at=_default_export_expires_at(created_at),
        )

    @staticmethod
    def _storage_key_for_export(export: ProjectExport) -> str:
        return (Path("exports") / export.project_id / f"{export.id}-{export.file_name}").as_posix()

    async def _enqueue_export_generation(self, export: ProjectExport) -> None:
        await enqueue_heavy_job(
            self.work_queue,
            job_type="export_generate",
            project_id=export.project_id,
            export_id=export.id,
            max_depth=get_settings().heavy_queue_max_depth,
            max_global_queued=effective_backpressure_max_queued_jobs(get_settings()),
            priority=heavy_job_priority_for_type("export_generate"),
        )

    async def _enforce_export_backpressure(self, *, surface: str) -> None:
        settings = get_settings()
        require_worker_capacity(surface, settings=settings)
        snapshot = await collect_backpressure_snapshot(
            settings=settings,
            job_queue=self.work_queue,
        )
        ensure_heavy_intake_capacity(snapshot, settings=settings, surface=surface)

    async def _fail_export(self, export: ProjectExport) -> ExportRead:
        export = await self.repository.update_state(
            export,
            status="failed",
            storage_key=None,
            completed_at=None,
        )
        return _to_export_read(export)

    async def _create_storage_backed_export(
        self,
        *,
        export_id: str,
        project_id: str,
        export_type: str,
        file_name: str,
        storage_key: str,
        content: bytes,
        now: datetime,
    ) -> ExportRead:
        export = await self._create_pending_export_record(
            export_id=export_id,
            project_id=project_id,
            export_type=export_type,
            file_name=file_name,
            created_at=now,
        )
        await self.repository.update_state(
            export,
            status="generating",
            storage_key=None,
            completed_at=None,
        )
        return await self._write_generated_export(
            export,
            project_id=project_id,
            export_type=export_type,
            storage_key=storage_key,
            content=content,
            now=now,
        )

    async def _write_generated_export(
        self,
        export: ProjectExport,
        *,
        project_id: str,
        export_type: str,
        storage_key: str,
        content: bytes,
        now: datetime,
    ) -> ExportRead:
        completed = False
        try:
            await write_storage_file(
                relative_storage_key=storage_key,
                content=content,
            )
            completed = await self._artifact_exists(storage_key)
        except Exception as exc:
            logger.error(
                "export.write_failed",
                export_id=export.id,
                project_id=project_id,
                export_type=export_type,
                storage_key=storage_key,
                error=str(exc),
                exc_info=True,
            )
            completed = False

        if not completed:
            try:
                await delete_storage_file(relative_storage_key=storage_key)
            except Exception as exc:
                logger.warning(
                    "export.failed_artifact_cleanup_failed",
                    export_id=export.id,
                    project_id=project_id,
                    export_type=export_type,
                    storage_key=storage_key,
                    error=str(exc),
                )
            logger.error(
                "export.fail_closed",
                export_id=export.id,
                project_id=project_id,
                export_type=export_type,
                storage_key=storage_key,
                reason="artifact_missing_or_unverified",
            )
            return await self._fail_export(export)

        export = await self.repository.update_state(
            export,
            status="completed",
            storage_key=storage_key,
            completed_at=now,
        )
        return _to_export_read(export)

    async def _mark_export_failed_if_artifact_missing(self, export: ProjectExport) -> ProjectExport:
        artifact_ready = await self._artifact_exists(export.storage_key)
        if artifact_ready:
            return export

        logger.error(
            "export.invalid_completed_state",
            export_id=export.id,
            project_id=export.project_id,
            export_type=export.export_type,
            storage_key=export.storage_key,
        )
        return await self.repository.update_state(
            export,
            status="failed",
            storage_key=None,
            completed_at=None,
        )

    async def process_export_by_id(self, export_id: str, *, case_detail: ProjectDetail) -> ExportRead | None:
        export = await self.repository.get_by_id(export_id)
        if export is None:
            return None
        if export.status == "completed":
            export = await self._mark_export_failed_if_artifact_missing(export)
            return _to_export_read(export)
        if export.status == "failed":
            return _to_export_read(export)

        export = await self.repository.update_state(
            export,
            status="generating",
            storage_key=None,
            completed_at=None,
        )
        now = datetime.now(UTC)
        storage_key = self._storage_key_for_export(export)
        try:
            if export.export_type == "quote-docx":
                if case_detail.finalProposal is None:
                    raise ValueError("Final proposal is required for DOCX export.")
                content = _build_docx_bytes(case_detail)
            elif export.export_type == "proposal-docx":
                if case_detail.proposalDraft is None:
                    raise ValueError("Proposal draft is required for proposal DOCX export.")
                content = _build_proposal_docx_bytes(case_detail)
            elif export.export_type == "quote-pdf":
                if case_detail.finalProposal is None:
                    raise ValueError("Final proposal is required for PDF export.")
                content = _build_pdf_bytes(case_detail)
            elif export.export_type == "case-zip":
                content = await _build_case_zip_bytes(case_detail)
            else:
                raise ValueError(f"Unsupported export type: {export.export_type!r}")
        except Exception as exc:
            logger.error(
                "export.generation_failed",
                export_id=export.id,
                project_id=export.project_id,
                export_type=export.export_type,
                error=str(exc),
                exc_info=True,
            )
            return await self._fail_export(export)

        return await self._write_generated_export(
            export,
            project_id=export.project_id,
            export_type=export.export_type,
            storage_key=storage_key,
            content=content,
            now=now,
        )

    async def create_export(self, *, case_id: str, export_type: str) -> ExportRead:
        export_id = f"exp_{uuid4().hex[:8]}"
        now = datetime.now(UTC)
        logger.error(
            "export.unsupported_generation",
            export_id=export_id,
            project_id=case_id,
            export_type=export_type,
        )
        export = await self._create_pending_export_record(
            export_id=export_id,
            project_id=case_id,
            export_type=export_type,
            file_name=f"{case_id}-{export_type}.pdf",
            created_at=now,
        )
        return await self._fail_export(export)

    async def create_quote_docx_export(self, *, case_detail: ProjectDetail) -> ExportRead:
        if case_detail.finalProposal is None:
            raise ValueError("Final proposal is required for DOCX export.")

        export_id = f"exp_{uuid4().hex[:8]}"
        now = datetime.now(UTC)
        base_name = sanitize_filename(case_detail.finalProposal.subject or case_detail.title or "nabidka")
        file_name = f"{base_name}.docx"
        await self._enforce_export_backpressure(surface="export_api")
        export = await self._create_pending_export_record(
            export_id=export_id,
            project_id=case_detail.id,
            export_type="quote-docx",
            file_name=file_name,
            created_at=now,
        )
        try:
            await self._enqueue_export_generation(export)
            return _to_export_read(export)
        except HeavyJobQueueCapacityExceededError as exc:
            await self._fail_export(export)
            logger.warning(
                "export.queue_enqueue_rejected",
                export_id=export.id,
                project_id=case_detail.id,
                export_type="quote-docx",
                error=str(exc),
                queued=exc.queued,
                processing=exc.processing,
                max_depth=exc.max_depth,
            )
            raise HTTPException(status_code=429, detail="Export queue is full. Please retry later.")
        except Exception as exc:
            await self._fail_export(export)
            logger.warning(
                "export.queue_enqueue_unavailable",
                export_id=export.id,
                project_id=case_detail.id,
                export_type="quote-docx",
                error=str(exc),
                exc_info=True,
            )
            raise HTTPException(status_code=503, detail="Export queue is unavailable.")

    async def create_proposal_docx_export(self, *, case_detail: ProjectDetail) -> ExportRead:
        if case_detail.proposalDraft is None:
            raise ValueError("Proposal draft is required for proposal DOCX export.")

        export_id = f"exp_{uuid4().hex[:8]}"
        now = datetime.now(UTC)
        base_name = sanitize_filename(case_detail.proposalDraft.subject or case_detail.title or "pracovni-navrh")
        file_name = f"{base_name}.docx"
        await self._enforce_export_backpressure(surface="export_api")
        export = await self._create_pending_export_record(
            export_id=export_id,
            project_id=case_detail.id,
            export_type="proposal-docx",
            file_name=file_name,
            created_at=now,
        )
        try:
            await self._enqueue_export_generation(export)
            return _to_export_read(export)
        except HeavyJobQueueCapacityExceededError as exc:
            await self._fail_export(export)
            logger.warning(
                "export.queue_enqueue_rejected",
                export_id=export.id,
                project_id=case_detail.id,
                export_type="proposal-docx",
                error=str(exc),
                queued=exc.queued,
                processing=exc.processing,
                max_depth=exc.max_depth,
            )
            raise HTTPException(status_code=429, detail="Export queue is full. Please retry later.")
        except Exception as exc:
            await self._fail_export(export)
            logger.warning(
                "export.queue_enqueue_unavailable",
                export_id=export.id,
                project_id=case_detail.id,
                export_type="proposal-docx",
                error=str(exc),
                exc_info=True,
            )
            raise HTTPException(status_code=503, detail="Export queue is unavailable.")

    async def create_quote_pdf_export(self, *, case_detail: ProjectDetail) -> ExportRead:
        if case_detail.finalProposal is None:
            raise ValueError("Final proposal is required for PDF export.")

        export_id = f"exp_{uuid4().hex[:8]}"
        now = datetime.now(UTC)
        base_name = sanitize_filename(case_detail.finalProposal.subject or case_detail.title or "nabidka")
        file_name = f"{base_name}.pdf"
        await self._enforce_export_backpressure(surface="export_api")
        export = await self._create_pending_export_record(
            export_id=export_id,
            project_id=case_detail.id,
            export_type="quote-pdf",
            file_name=file_name,
            created_at=now,
        )
        try:
            await self._enqueue_export_generation(export)
            return _to_export_read(export)
        except HeavyJobQueueCapacityExceededError as exc:
            await self._fail_export(export)
            logger.warning(
                "export.queue_enqueue_rejected",
                export_id=export.id,
                project_id=case_detail.id,
                export_type="quote-pdf",
                error=str(exc),
                queued=exc.queued,
                processing=exc.processing,
                max_depth=exc.max_depth,
            )
            raise HTTPException(status_code=429, detail="Export queue is full. Please retry later.")
        except Exception as exc:
            await self._fail_export(export)
            logger.warning(
                "export.queue_enqueue_unavailable",
                export_id=export.id,
                project_id=case_detail.id,
                export_type="quote-pdf",
                error=str(exc),
                exc_info=True,
            )
            raise HTTPException(status_code=503, detail="Export queue is unavailable.")

    async def create_final_proposal_exports(self, *, case_detail: ProjectDetail) -> list[ExportRead]:
        return [
            await self.create_quote_docx_export(case_detail=case_detail),
            await self.create_quote_pdf_export(case_detail=case_detail),
        ]

    async def create_case_zip_export(self, *, case_detail: ProjectDetail) -> ExportRead:
        export_id = f"exp_{uuid4().hex[:8]}"
        now = datetime.now(UTC)
        base_name = sanitize_filename(case_detail.title or case_detail.id)
        file_name = f"{base_name}.zip"
        await self._enforce_export_backpressure(surface="export_api")
        export = await self._create_pending_export_record(
            export_id=export_id,
            project_id=case_detail.id,
            export_type="case-zip",
            file_name=file_name,
            created_at=now,
        )
        try:
            await self._enqueue_export_generation(export)
            return _to_export_read(export)
        except HeavyJobQueueCapacityExceededError as exc:
            await self._fail_export(export)
            logger.warning(
                "export.queue_enqueue_rejected",
                export_id=export.id,
                project_id=case_detail.id,
                export_type="case-zip",
                error=str(exc),
                queued=exc.queued,
                processing=exc.processing,
                max_depth=exc.max_depth,
            )
            raise HTTPException(status_code=429, detail="Export queue is full. Please retry later.")
        except Exception as exc:
            await self._fail_export(export)
            logger.warning(
                "export.queue_enqueue_unavailable",
                export_id=export.id,
                project_id=case_detail.id,
                export_type="case-zip",
                error=str(exc),
                exc_info=True,
            )
            raise HTTPException(status_code=503, detail="Export queue is unavailable.")

    async def get_export(
        self,
        export_id: str,
        *,
        organization_id: str | None = None,
        is_superadmin_context: bool = False,
    ) -> ExportRead | None:
        if organization_id is not None:
            export = await self.repository.get_by_id_in_org(export_id, organization_id)
        elif is_superadmin_context:
            export = await self.repository.get_by_id(export_id)
        else:
            return None
        if export is None:
            return None
        expires_at = _as_utc(export.expires_at)
        assert expires_at is not None
        if expires_at <= datetime.now(UTC):
            logger.info(
                "export.expired_access_rejected",
                export_id=export.id,
                project_id=export.project_id,
                expires_at=expires_at.isoformat(),
            )
            return None
        if export.status == "completed":
            export = await self._mark_export_failed_if_artifact_missing(export)
        return _to_export_read(export)

    async def delete_expired_exports(self, *, now: datetime | None = None) -> int:
        current_time = now or datetime.now(UTC)
        expired_exports = await self.repository.list_expired(now=current_time)
        if not expired_exports:
            return 0

        export_ids: list[str] = []
        for export in expired_exports:
            if export.storage_key:
                await delete_storage_file(relative_storage_key=export.storage_key)
            logger.info(
                "export.cleanup.deleted",
                org_id=export.organization_id,
                key=export.storage_key,
                action="delete_expired_export",
                export_id=export.export_id,
                project_id=export.project_id,
                expires_at=_as_utc(export.expires_at).isoformat(),
            )
            export_ids.append(export.export_id)

        deleted_rows = await self.repository.delete_by_ids(export_ids)
        if deleted_rows != len(export_ids):
            raise RuntimeError(
                f"Expired export cleanup deleted {deleted_rows} DB rows, expected {len(export_ids)}."
            )
        return deleted_rows
