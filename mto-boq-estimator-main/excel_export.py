"""
Excel export via openpyxl.

Produces a multi-sheet workbook:
  1. Cover / Project Summary + disclaimer
  2. MTO (with formula/assumption/confidence columns for traceability)
  3. BOQ (with rates, wastage, amounts)
  4. Cost Summary
  5. Assumptions & Extraction Notes (everything the AI flagged + defaults used)
"""
from __future__ import annotations

import io
from typing import List

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

import config
from models.schemas import BOQLineItem, CostSummary, ExtractedBuildingParams, ProjectInputs, QuantityLineItem
from utils import units

HEADER_FILL = PatternFill(start_color="1F6FEB", end_color="1F6FEB", fill_type="solid")
HEADER_FONT = Font(color="FFFFFF", bold=True)
TITLE_FONT = Font(bold=True, size=14)
SUBTITLE_FONT = Font(italic=True, size=10, color="666666")
THIN_BORDER = Border(*(Side(style="thin", color="DDDDDD"),) * 4)

LOW_CONF_FILL = PatternFill(start_color="FFF3CD", end_color="FFF3CD", fill_type="solid")


def _style_header_row(ws, row_idx: int, ncols: int):
    for c in range(1, ncols + 1):
        cell = ws.cell(row=row_idx, column=c)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = THIN_BORDER


def _autofit(ws, widths: List[int]):
    for i, w in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(i)].width = w


def _write_cover_sheet(wb: Workbook, project_inputs: ProjectInputs, cost_summary: CostSummary):
    ws = wb.active
    ws.title = "Project Summary"
    ws["A1"] = config.APP_NAME
    ws["A1"].font = TITLE_FONT
    ws["A2"] = f"Version {config.APP_VERSION}"
    ws["A2"].font = SUBTITLE_FONT

    rows = [
        ("", ""),
        ("Project Name", project_inputs.project_name),
        ("Client", project_inputs.client_name),
        ("Location", project_inputs.location),
        ("Soil Type", project_inputs.soil_type),
        ("Concrete Grade (Footing/Column/Beam/Slab)", f"{project_inputs.concrete_grade_footing} / {project_inputs.concrete_grade_column} / {project_inputs.concrete_grade_beam} / {project_inputs.concrete_grade_slab}"),
        ("Steel Grade", project_inputs.steel_grade),
        ("Wall Material", project_inputs.wall_material),
        ("Finish Level", project_inputs.finish_level),
        ("Unit System", units.UNIT_SYSTEM_LABELS.get(project_inputs.unit_system, project_inputs.unit_system)),
        ("", ""),
        ("Subtotal", f"{cost_summary.currency} {cost_summary.subtotal:,.2f}"),
        (f"Contingency ({cost_summary.contingency_pct:.1f}%)", f"{cost_summary.currency} {cost_summary.contingency_amount:,.2f}"),
        ("GRAND TOTAL", f"{cost_summary.currency} {cost_summary.grand_total:,.2f}"),
    ]
    r = 4
    for label, value in rows:
        ws.cell(row=r, column=1, value=label).font = Font(bold=label == "GRAND TOTAL")
        ws.cell(row=r, column=2, value=value).font = Font(bold=label == "GRAND TOTAL")
        r += 1

    r += 1
    ws.cell(row=r, column=1, value="DISCLAIMER").font = Font(bold=True, color="C0392B")
    r += 1
    cell = ws.cell(row=r, column=1, value=config.DISCLAIMER_TEXT)
    cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells(start_row=r, start_column=1, end_row=r + 4, end_column=6)
    _autofit(ws, [38, 30, 14, 14, 14, 14])


def _write_mto_sheet(wb: Workbook, mto_items: List[QuantityLineItem], unit_system: str = units.SI):
    ws = wb.create_sheet("MTO")
    ws.append([
        f"Quantities shown in {units.UNIT_SYSTEM_LABELS.get(unit_system, unit_system)}. "
        "All calculations are performed internally in SI/metric units; Formula/Key Inputs Used describe that underlying metric arithmetic."
    ])
    ws["A1"].font = SUBTITLE_FONT
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=9)
    headers = ["Item Code", "Category", "Description", "Unit", "Quantity", "Confidence", "Formula", "Key Inputs Used", "Assumptions"]
    ws.append(headers)
    _style_header_row(ws, 2, len(headers))

    for item in mto_items:
        qty, unit = units.quantity_and_unit_for_display(item.quantity, item.unit, unit_system)
        inputs_str = "; ".join(f"{k}={v}" for k, v in item.inputs_used.items())
        assumptions_str = " | ".join(item.assumptions)
        ws.append(
            [
                item.item_code,
                item.category,
                item.description,
                unit,
                round(qty, 3),
                item.confidence.value,
                item.formula,
                inputs_str,
                assumptions_str,
            ]
        )
        row = ws.max_row
        if item.confidence.value == "Low":
            for c in range(1, len(headers) + 1):
                ws.cell(row=row, column=c).fill = LOW_CONF_FILL
        for c in range(1, len(headers) + 1):
            ws.cell(row=row, column=c).border = THIN_BORDER
            ws.cell(row=row, column=c).alignment = Alignment(vertical="top", wrap_text=True)

    _autofit(ws, [14, 14, 34, 8, 12, 12, 42, 40, 50])
    ws.freeze_panes = "A3"


def _write_boq_sheet(wb: Workbook, boq_items: List[BOQLineItem], currency_symbol: str, unit_system: str = units.SI):
    ws = wb.create_sheet("BOQ")
    ws.append([
        f"Quantities/Rates shown in {units.UNIT_SYSTEM_LABELS.get(unit_system, unit_system)}. "
        "Amounts are unaffected by unit system (Quantity x Rate always reproduces the same Amount)."
    ])
    ws["A1"].font = SUBTITLE_FONT
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=11)
    headers = ["Item Code", "Category", "Description", "Unit", "Quantity", "Wastage %", "Qty incl. Wastage", "Rate", "Amount", "Confidence", "Remarks"]
    ws.append(headers)
    _style_header_row(ws, 2, len(headers))

    for item in boq_items:
        qty, unit = units.quantity_and_unit_for_display(item.quantity, item.unit, unit_system)
        qty_wastage, _ = units.quantity_and_unit_for_display(item.quantity_with_wastage, item.unit, unit_system)
        rate = units.display_rate(item.rate, item.unit, unit_system)
        ws.append(
            [
                item.item_code,
                item.category,
                item.description,
                unit,
                round(qty, 3),
                item.wastage_pct,
                round(qty_wastage, 3),
                round(rate, 2),
                item.amount,
                item.confidence.value,
                item.remarks,
            ]
        )
        row = ws.max_row
        if item.confidence.value == "Low":
            for c in range(1, len(headers) + 1):
                ws.cell(row=row, column=c).fill = LOW_CONF_FILL
        for c in range(1, len(headers) + 1):
            ws.cell(row=row, column=c).border = THIN_BORDER

    total_row = ws.max_row + 2
    ws.cell(row=total_row, column=8, value="TOTAL").font = Font(bold=True)
    ws.cell(row=total_row, column=9, value=f"=SUM(I3:I{ws.max_row - 1})").font = Font(bold=True)

    _autofit(ws, [14, 14, 40, 8, 12, 10, 16, 12, 14, 12, 40])
    ws.freeze_panes = "A3"


def _write_assumptions_sheet(wb: Workbook, params: ExtractedBuildingParams):
    ws = wb.create_sheet("Assumptions & Notes")
    ws.append(["AI Overall Notes"])
    ws["A1"].font = Font(bold=True)
    ws.append([params.overall_notes or "-"])
    ws.append([])
    ws.append(["Extraction Warnings"])
    ws.cell(row=ws.max_row, column=1).font = Font(bold=True)
    if params.extraction_warnings:
        for w in params.extraction_warnings:
            ws.append([f"- {w}"])
    else:
        ws.append(["(none)"])
    _autofit(ws, [110])
    for row in ws.iter_rows():
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical="top")


def build_excel_workbook(
    project_inputs: ProjectInputs,
    params: ExtractedBuildingParams,
    mto_items: List[QuantityLineItem],
    boq_items: List[BOQLineItem],
    cost_summary: CostSummary,
) -> bytes:
    unit_system = project_inputs.unit_system
    wb = Workbook()
    _write_cover_sheet(wb, project_inputs, cost_summary)
    _write_mto_sheet(wb, mto_items, unit_system)
    _write_boq_sheet(wb, boq_items, config.DEFAULT_CURRENCY_SYMBOL, unit_system)
    _write_assumptions_sheet(wb, params)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
