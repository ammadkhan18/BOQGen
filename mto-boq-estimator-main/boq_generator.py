"""
BOQ (Bill of Quantities) generation.

Takes the deterministic MTO quantities and applies:
1. Category-specific wastage/allowance percentages (editable)
2. Unit rates (editable rate book)
3. A "Preliminaries & rough MEP allowance" lump-sum line, because a
   residential estimate that silently omits site overheads, plumbing, and
   electrical rough-in would understate cost significantly - the MVP does
   not compute MEP quantities, so this is clearly flagged as a placeholder.
4. Overall contingency percentage -> grand total

Quantity items flagged `informational=True` (the cement/sand/aggregate
breakdown of each concrete/mortar pour - see engineering/calculations.py)
are skipped entirely here: their cost already lives inside their parent
item's composite rate, so pricing them again would double-count. They're
still fully visible in the MTO (Step 4) - that's a deliberate MTO-vs-BOQ
split: MTO is the full procurement-grade material list, BOQ is the priced
summary using composite pay items.

No AI involvement here either - pure arithmetic over user-approved inputs.
"""
from __future__ import annotations

from typing import Dict, List

import pandas as pd

from engineering.rules import FINISH_LEVEL_RATE_MULTIPLIERS
from models.schemas import (
    BOQLineItem,
    ConfidenceLevel,
    CostSummary,
    MaterialRate,
    ProjectInputs,
    QuantityLineItem,
    WastageFactors,
)
from utils import units

# Maps a quantity item's category to the relevant wastage-factor field name.
# "Concrete Materials" and "Procurement Summary" items are always
# `informational=True` and skipped entirely in generate_boq() before this
# lookup would even matter (see the loop below) - listed here anyway so the
# mapping stays a complete, self-documenting reference of every category.
CATEGORY_TO_WASTAGE_FIELD = {
    "Excavation": None,  # no wastage applied to excavated earth
    "PCC": "concrete_pct",
    "Footing": "concrete_pct",
    "Column": "concrete_pct",
    "Beam": "concrete_pct",
    "Slab": "concrete_pct",
    "Reinforcement": "steel_pct",
    "Formwork": "formwork_pct",
    "Masonry": "brick_block_pct",
    "Plaster": "plaster_pct",
    "Flooring": "flooring_pct",
    "Waterproofing": "misc_pct",
    "Painting": "paint_pct",
    "DPC": "concrete_pct",
    "Anti-termite": "misc_pct",
    "Doors": None,  # supply+install rate is already an exact per-unit/per-area price
    "Windows": None,
    "Concrete Materials": None,  # informational-only; never priced (see generate_boq)
    "Procurement Summary": None,  # informational-only; never priced (see generate_boq)
}

PRELIMINARIES_PCT_OF_CIVIL_SUBTOTAL = 8.0


def _wastage_for(item: QuantityLineItem, wastage: WastageFactors) -> float:
    field = CATEGORY_TO_WASTAGE_FIELD.get(item.category, "misc_pct")
    if field is None:
        return 0.0
    return getattr(wastage, field, wastage.misc_pct)


def _finish_level_multiplier(category: str, finish_level: str) -> float:
    """Only Flooring/Painting/Plaster categories are finish-grade-sensitive
    (see engineering.rules.FINISH_LEVEL_RATE_MULTIPLIERS) - every other
    category (structural concrete, steel, excavation, etc.) is unaffected
    by Finish Level and always returns 1.0 (no-op)."""
    return FINISH_LEVEL_RATE_MULTIPLIERS.get(finish_level, {}).get(category, 1.0)


def generate_boq(
    mto_items: List[QuantityLineItem],
    rate_book: Dict[str, MaterialRate],
    wastage: WastageFactors,
    project_inputs: ProjectInputs,
    include_preliminaries: bool = True,
    preliminaries_pct: float = PRELIMINARIES_PCT_OF_CIVIL_SUBTOTAL,
) -> tuple[List[BOQLineItem], CostSummary]:
    boq_items: List[BOQLineItem] = []

    for item in mto_items:
        if item.informational:
            # Procurement-reference-only line (e.g. the cement/sand/
            # aggregate that make up a concrete pour) - its cost is
            # already inside its parent item's composite rate, so pricing
            # it again here would double-count. It still shows up in the
            # MTO (Step 4) - that's the whole point of these lines.
            continue

        wastage_pct = _wastage_for(item, wastage)
        qty_with_wastage = item.quantity * (1 + wastage_pct / 100.0)

        rate_row = rate_book.get(item.item_code)
        if rate_row is None:
            rate = 0.0
            remarks = "No rate found in rate book - please add a rate."
        else:
            rate = rate_row.rate
            remarks = ""

        finish_mult = _finish_level_multiplier(item.category, project_inputs.finish_level)
        if finish_mult != 1.0:
            rate = rate * finish_mult
            note = f"Rate x{finish_mult:.2f} for '{project_inputs.finish_level}' finish level."
            remarks = f"{remarks} {note}".strip()

        amount = qty_with_wastage * rate
        boq_items.append(
            BOQLineItem(
                item_code=item.item_code,
                description=item.description,
                category=item.category,
                unit=item.unit,
                quantity=round(item.quantity, 3),
                wastage_pct=wastage_pct,
                quantity_with_wastage=round(qty_with_wastage, 3),
                rate=rate,
                amount=round(amount, 2),
                confidence=item.confidence,
                remarks=remarks,
            )
        )

    civil_subtotal = sum(b.amount for b in boq_items)

    if include_preliminaries:
        prelim_amount = civil_subtotal * preliminaries_pct / 100.0
        boq_items.append(
            BOQLineItem(
                item_code="PRELIM-01",
                description=(
                    f"Preliminaries, site overheads & rough MEP allowance "
                    f"({preliminaries_pct:.1f}% of civil subtotal - placeholder, NOT a detailed MEP estimate)"
                ),
                category="Preliminaries",
                unit="LS",
                quantity=1.0,
                wastage_pct=0.0,
                quantity_with_wastage=1.0,
                rate=round(prelim_amount, 2),
                amount=round(prelim_amount, 2),
                confidence=ConfidenceLevel.LOW,
                remarks="Lump-sum placeholder only. Electrical/plumbing/HVAC quantities are NOT computed in this MVP.",
            )
        )

    subtotal = sum(b.amount for b in boq_items)
    contingency_amount = subtotal * project_inputs.contingency_pct / 100.0
    grand_total = subtotal + contingency_amount

    cost_summary = CostSummary(
        subtotal=round(subtotal, 2),
        contingency_pct=project_inputs.contingency_pct,
        contingency_amount=round(contingency_amount, 2),
        grand_total=round(grand_total, 2),
        currency=project_inputs.currency,
    )
    return boq_items, cost_summary


def boq_to_dataframe(items: List[BOQLineItem], unit_system: str = units.SI) -> pd.DataFrame:
    """`unit_system` only affects the displayed Unit/Quantity/Rate columns.
    Quantity and Rate are converted by inverse factors (see
    utils/units.py), so Quantity x Rate always reproduces the same
    Amount regardless of which unit system is selected - Amount itself
    (a currency figure) is never converted."""
    rows = []
    for i in items:
        qty, unit = units.quantity_and_unit_for_display(i.quantity, i.unit, unit_system)
        qty_wastage, _ = units.quantity_and_unit_for_display(i.quantity_with_wastage, i.unit, unit_system)
        rate = units.display_rate(i.rate, i.unit, unit_system)
        rows.append(
            {
                "Item Code": i.item_code,
                "Category": i.category,
                "Description": i.description,
                "Unit": unit,
                "Quantity": round(qty, 3),
                "Wastage %": i.wastage_pct,
                "Qty incl. Wastage": round(qty_wastage, 3),
                "Rate": round(rate, 2),
                "Amount": i.amount,
                "Confidence": i.confidence.value,
                "Remarks": i.remarks,
            }
        )
    return pd.DataFrame(rows)


def cost_by_category(items: List[BOQLineItem]) -> pd.DataFrame:
    # Category totals are pure currency amounts - unaffected by unit
    # system - so this always uses the canonical (SI) dataframe.
    df = boq_to_dataframe(items, unit_system=units.SI)
    if df.empty:
        return df
    grouped = df.groupby("Category", as_index=False)["Amount"].sum().sort_values("Amount", ascending=False)
    return grouped
