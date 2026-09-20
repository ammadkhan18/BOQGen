"""
PDF export via ReportLab.

Produces a printable summary report: cover/disclaimer page, MTO table,
BOQ table, and cost summary. Kept visually simple (no external fonts/
images) to stay dependency-free and reliable on Streamlit Community Cloud.
"""
from __future__ import annotations

import io
from typing import List

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

import config
from models.schemas import BOQLineItem, CostSummary, ExtractedBuildingParams, ProjectInputs, QuantityLineItem
from utils import units

styles = getSampleStyleSheet()
TITLE_STYLE = ParagraphStyle("TitleX", parent=styles["Title"], fontSize=18)
H2_STYLE = ParagraphStyle("H2X", parent=styles["Heading2"], spaceBefore=12, spaceAfter=6)
NORMAL = styles["Normal"]
SMALL = ParagraphStyle("Small", parent=styles["Normal"], fontSize=8, leading=10)
# Used for Code/Category/Unit/Confidence cells: plain strings in a ReportLab
# Table do NOT wrap - a value wider than its column just overlaps the next
# cell. Item codes now go up to ~20 chars (e.g. "FTG-CONC-01-CEMENT" from
# the cement/sand/aggregate breakdown) and categories up to ~19 chars
# ("Procurement Summary"), so every text cell is wrapped in a Paragraph
# using this style rather than passed as a raw string.
CODE_STYLE = ParagraphStyle("Code", parent=styles["Normal"], fontSize=7.5, leading=9, fontName="Helvetica-Bold")
CELL_STYLE = ParagraphStyle("Cell", parent=styles["Normal"], fontSize=7.5, leading=9)
DISCLAIMER_STYLE = ParagraphStyle(
    "Disclaimer", parent=styles["Normal"], fontSize=9, textColor=colors.HexColor("#8a1c1c"),
    borderColor=colors.HexColor("#8a1c1c"), borderWidth=0.5, borderPadding=8, backColor=colors.HexColor("#fdf0f0"),
)

TABLE_HEADER_BG = colors.HexColor("#1F6FEB")
LOW_CONF_BG = colors.HexColor("#FFF3CD")


def _project_info_table(project_inputs: ProjectInputs) -> Table:
    unit_system_label = units.UNIT_SYSTEM_LABELS.get(project_inputs.unit_system, project_inputs.unit_system)
    data = [
        ["Project", project_inputs.project_name, "Location", project_inputs.location],
        ["Client", project_inputs.client_name or "-", "Soil Type", project_inputs.soil_type],
        ["Concrete (Ftg/Col/Beam/Slab)", f"{project_inputs.concrete_grade_footing}/{project_inputs.concrete_grade_column}/{project_inputs.concrete_grade_beam}/{project_inputs.concrete_grade_slab}", "Steel Grade", project_inputs.steel_grade],
        ["Wall Material", project_inputs.wall_material, "Finish Level", project_inputs.finish_level],
        ["Unit System", unit_system_label, "Currency", project_inputs.currency],
    ]
    t = Table(data, colWidths=[45 * mm, 65 * mm, 30 * mm, 40 * mm])
    t.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F0F4F8")),
                ("BACKGROUND", (2, 0), (2, -1), colors.HexColor("#F0F4F8")),
            ]
        )
    )
    return t


def _mto_table(mto_items: List[QuantityLineItem], unit_system: str = units.SI) -> Table:
    # Column widths sum to 224mm, comfortably inside the ~267mm usable width
    # of a landscape A4 page with 15mm margins on each side. Every text
    # column uses a Paragraph (wraps) rather than a raw string (doesn't) -
    # see the CODE_STYLE/CELL_STYLE comment above.
    header = ["Code", "Category", "Description", "Unit", "Qty", "Conf."]
    data = [header]
    row_confidences = []
    for i in mto_items:
        qty, unit = units.quantity_and_unit_for_display(i.quantity, i.unit, unit_system)
        data.append(
            [
                Paragraph(i.item_code, CODE_STYLE),
                Paragraph(i.category, CELL_STYLE),
                Paragraph(i.description, SMALL),
                Paragraph(unit, CELL_STYLE),
                f"{qty:,.2f}",
                Paragraph(i.confidence.value, CELL_STYLE),
            ]
        )
        row_confidences.append(i.confidence.value)

    t = Table(data, colWidths=[34 * mm, 30 * mm, 108 * mm, 14 * mm, 22 * mm, 16 * mm], repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), TABLE_HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CCCCCC")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (4, 1), (4, -1), "RIGHT"),
        ("TOPPADDING", (0, 1), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
    ]
    for idx, conf in enumerate(row_confidences, start=1):
        if conf == "Low":
            style.append(("BACKGROUND", (0, idx), (-1, idx), LOW_CONF_BG))
    t.setStyle(TableStyle(style))
    return t


def _boq_table(boq_items: List[BOQLineItem], currency_symbol: str, unit_system: str = units.SI) -> Table:
    # Column widths sum to 259mm (landscape A4, 15mm margins -> ~267mm
    # usable). Remarks (e.g. "Rate x1.85 for 'Premium' finish level.") is
    # new - it carries information that used to be silently dropped from
    # the PDF - and every text column wraps via Paragraph.
    header = ["Code", "Description", "Unit", "Qty (+wastage)", "Rate", "Amount", "Remarks"]
    data = [header]
    row_confidences = []
    for i in boq_items:
        qty_wastage, unit = units.quantity_and_unit_for_display(i.quantity_with_wastage, i.unit, unit_system)
        rate = units.display_rate(i.rate, i.unit, unit_system)
        data.append(
            [
                Paragraph(i.item_code, CODE_STYLE),
                Paragraph(i.description, SMALL),
                Paragraph(unit, CELL_STYLE),
                f"{qty_wastage:,.2f}",
                f"{currency_symbol}{rate:,.2f}",
                f"{currency_symbol}{i.amount:,.2f}",
                Paragraph(i.remarks, CELL_STYLE) if i.remarks else "",
            ]
        )
        row_confidences.append(i.confidence.value)

    t = Table(data, colWidths=[24 * mm, 68 * mm, 13 * mm, 26 * mm, 24 * mm, 26 * mm, 78 * mm], repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), TABLE_HEADER_BG),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#CCCCCC")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (3, 1), (5, -1), "RIGHT"),
        ("TOPPADDING", (0, 1), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 1), (-1, -1), 3),
    ]
    for idx, conf in enumerate(row_confidences, start=1):
        if conf == "Low":
            style.append(("BACKGROUND", (0, idx), (-1, idx), LOW_CONF_BG))
    t.setStyle(TableStyle(style))
    return t


def _cost_summary_table(cost_summary: CostSummary, currency_symbol: str) -> Table:
    data = [
        ["Subtotal", f"{currency_symbol}{cost_summary.subtotal:,.2f}"],
        [f"Contingency ({cost_summary.contingency_pct:.1f}%)", f"{currency_symbol}{cost_summary.contingency_amount:,.2f}"],
        ["GRAND TOTAL", f"{currency_symbol}{cost_summary.grand_total:,.2f}"],
    ]
    t = Table(data, colWidths=[60 * mm, 50 * mm])
    t.setStyle(
        TableStyle(
            [
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
                ("FONTSIZE", (0, 2), (-1, 2), 12),
                ("LINEABOVE", (0, 2), (-1, 2), 1, colors.black),
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return t


def build_pdf_report(
    project_inputs: ProjectInputs,
    params: ExtractedBuildingParams,
    mto_items: List[QuantityLineItem],
    boq_items: List[BOQLineItem],
    cost_summary: CostSummary,
) -> bytes:
    unit_system = project_inputs.unit_system
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=landscape(A4),
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        leftMargin=15 * mm,
        rightMargin=15 * mm,
        title=f"{project_inputs.project_name} - MTO/BOQ Estimate",
    )

    story = []
    story.append(Paragraph(config.APP_NAME, TITLE_STYLE))
    story.append(Paragraph(f"Preliminary MTO / BOQ / Cost Estimate &nbsp;&nbsp;|&nbsp;&nbsp; v{config.APP_VERSION}", NORMAL))
    story.append(Spacer(1, 8))
    story.append(Paragraph(config.DISCLAIMER_TEXT, DISCLAIMER_STYLE))
    story.append(Spacer(1, 10))
    story.append(_project_info_table(project_inputs))
    story.append(Spacer(1, 10))

    if params.overall_notes:
        story.append(Paragraph("<b>AI Extraction Notes:</b> " + params.overall_notes, SMALL))
    if params.extraction_warnings:
        warn_text = " | ".join(params.extraction_warnings)
        story.append(Paragraph("<b>Warnings:</b> " + warn_text, SMALL))

    unit_note = (
        f"Quantities shown in {units.UNIT_SYSTEM_LABELS.get(unit_system, unit_system)}. "
        "All calculations are performed internally in SI/metric units."
    )

    story.append(PageBreak())
    story.append(Paragraph("Material Take-Off (MTO)", H2_STYLE))
    story.append(Paragraph("Rows highlighted yellow are Low-confidence - verify against actual drawings. " + unit_note, SMALL))
    story.append(Spacer(1, 6))
    story.append(_mto_table(mto_items, unit_system))

    story.append(PageBreak())
    story.append(Paragraph("Bill of Quantities (BOQ)", H2_STYLE))
    story.append(Paragraph(unit_note + " Amounts are unaffected by unit system.", SMALL))
    story.append(Spacer(1, 6))
    story.append(_boq_table(boq_items, config.DEFAULT_CURRENCY_SYMBOL, unit_system))
    story.append(Spacer(1, 12))
    story.append(Paragraph("Cost Summary", H2_STYLE))
    story.append(_cost_summary_table(cost_summary, config.DEFAULT_CURRENCY_SYMBOL))
    story.append(Spacer(1, 10))
    story.append(Paragraph(config.DISCLAIMER_TEXT, DISCLAIMER_STYLE))

    doc.build(story)
    return buf.getvalue()
