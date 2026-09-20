"""
MTO (Material Take-Off) generation.

This module is a thin orchestration layer: it calls the deterministic
engineering functions (engineering/calculations.py) and organizes the
result for display/export. It performs NO calculation of its own -
that separation is intentional so all engineering formulas live in one
auditable place.
"""
from __future__ import annotations

from typing import Dict, List

import pandas as pd

from engineering.calculations import generate_all_quantities, steel_sanity_check
from models.schemas import ExtractedBuildingParams, ProjectInputs, QuantityLineItem
from utils import units


def generate_mto(params: ExtractedBuildingParams, project_inputs: ProjectInputs) -> List[QuantityLineItem]:
    return generate_all_quantities(params, project_inputs)


def group_by_category(items: List[QuantityLineItem]) -> Dict[str, List[QuantityLineItem]]:
    grouped: Dict[str, List[QuantityLineItem]] = {}
    for item in items:
        grouped.setdefault(item.category, []).append(item)
    return grouped


def mto_to_dataframe(items: List[QuantityLineItem], unit_system: str = units.SI) -> pd.DataFrame:
    """`unit_system` only affects the displayed Quantity/Unit columns - the
    underlying QuantityLineItem.quantity always stays in SI (see
    utils/units.py); this keeps every calculation upstream untouched."""
    rows = []
    for i in items:
        qty, unit = units.quantity_and_unit_for_display(i.quantity, i.unit, unit_system)
        rows.append(
            {
                "Item Code": i.item_code,
                "Category": i.category,
                "Description": i.description,
                "Unit": unit,
                "Quantity": round(qty, 3),
                "Confidence": i.confidence.value,
                "Formula": i.formula,
                "Procurement Note": (
                    f"Reference qty only - priced under {i.parent_item_code} above" if i.informational else ""
                ),
            }
        )
    return pd.DataFrame(rows)


def compute_reinforcement_summary(items: List[QuantityLineItem]) -> dict:
    structural_categories = {"Footing", "Column", "Beam", "Slab"}
    structural_concrete = sum(
        i.quantity for i in items if i.category in structural_categories and i.unit == "m3" and not i.informational
    )
    total_steel = sum(i.quantity for i in items if i.category == "Reinforcement" and not i.informational)
    return steel_sanity_check(structural_concrete, total_steel)


def compute_procurement_totals(items: List[QuantityLineItem]) -> dict:
    """Pulls out the 3 project-wide SUMMARY-* rows (see
    engineering/calculations.py:compute_procurement_summary) for a compact
    "Procurement Summary" metrics row in the UI (Step 4)."""
    by_code = {i.item_code: i for i in items}
    return {
        "cement_bags": by_code["SUMMARY-CEMENT"].quantity if "SUMMARY-CEMENT" in by_code else 0.0,
        "sand_m3": by_code["SUMMARY-SAND"].quantity if "SUMMARY-SAND" in by_code else 0.0,
        "aggregate_m3": by_code["SUMMARY-AGG"].quantity if "SUMMARY-AGG" in by_code else 0.0,
    }
