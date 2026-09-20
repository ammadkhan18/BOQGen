"""
Unit-system conversion helpers.

DESIGN RULE (mirrors the "AI never calculates" rule in engineering/): every
number is stored and calculated internally in SI/metric units (m, m2/sqm,
m3, kg) exactly as before. Nothing in engineering/calculations.py,
mto_boq/boq_generator.py, or models/schemas.py changes its unit
convention. This module is a pure DISPLAY/INPUT conversion layer:

  - The UI shows values in feet/inches/sqft/cft when the user picks the
    "FPS" unit system, but immediately converts them back to SI before
    storing them in an Estimate or MaterialRate.
  - The MTO/BOQ tables and exports convert SI quantities/rates to
    FPS-equivalent values purely for display; the underlying arithmetic
    (quantity * rate = amount) is unaffected because both quantity and
    rate are converted by the same factor in opposite directions, so
    amounts always come out identical regardless of which unit system is
    selected.

Unit conventions used when "FPS" is selected (standard Pakistani
construction practice):
  - length            -> feet (ft)
  - small "thickness"-type dimensions (slab/wall thickness, column &
    beam cross-section) -> inches (in), since these are conventionally
    quoted in inches even in FPS-speaking markets (e.g. "9 inch wall",
    "5 inch slab", "9x18 column")
  - area              -> square feet (sqft)
  - volume            -> cubic feet (cft)
  - weight (steel)    -> kilograms (kg) - unchanged in both systems,
    since Pakistani steel markets always quote/sell by the kg regardless
    of whether the rest of the job is being measured in feet or metres.
  - counts / lump-sum -> unchanged
"""
from __future__ import annotations

import re
from typing import Tuple

SI = "SI"
FPS = "FPS"

UNIT_SYSTEM_LABELS = {
    SI: "SI (Metric - m, m², m³)",
    FPS: "FPS (Feet-Inch, Pakistani practice - ft, sqft, cft)",
}

# --------------------------------------------------------------------------
# Base conversion factors
# --------------------------------------------------------------------------
FT_PER_M = 3.280839895
M_PER_FT = 1.0 / FT_PER_M

IN_PER_M = 39.37007874
M_PER_IN = 1.0 / IN_PER_M

SQFT_PER_SQM = FT_PER_M ** 2  # 10.76391...
SQM_PER_SQFT = 1.0 / SQFT_PER_SQM

CFT_PER_CUM = FT_PER_M ** 3  # 35.31467...
CUM_PER_CFT = 1.0 / CFT_PER_CUM


def is_fps(unit_system: str) -> bool:
    return unit_system == FPS


# --------------------------------------------------------------------------
# Scalar dimension conversion (used on the Step-3 edit form). "kind" is one
# of "length", "thickness", "area", or None (no conversion - counts etc.)
# --------------------------------------------------------------------------


def to_display(value_si: float, kind: str | None, unit_system: str) -> float:
    """Convert a canonical SI value to the display value for unit_system."""
    if not is_fps(unit_system) or kind is None:
        return value_si
    if kind == "length":
        return value_si * FT_PER_M
    if kind == "thickness":
        return value_si * IN_PER_M
    if kind == "area":
        return value_si * SQFT_PER_SQM
    return value_si


def to_si(value_display: float, kind: str | None, unit_system: str) -> float:
    """Convert a display value (already in the user's chosen system) back
    to canonical SI for storage in an Estimate."""
    if not is_fps(unit_system) or kind is None:
        return value_display
    if kind == "length":
        return value_display * M_PER_FT
    if kind == "thickness":
        return value_display * M_PER_IN
    if kind == "area":
        return value_display * SQM_PER_SQFT
    return value_display


def dimension_unit_label(kind: str | None, unit_system: str) -> str:
    if kind is None:
        return ""
    if not is_fps(unit_system):
        return {"length": "m", "thickness": "m", "area": "sqm"}.get(kind, "")
    return {"length": "ft", "thickness": "in", "area": "sqft"}.get(kind, "")


# --------------------------------------------------------------------------
# MTO/BOQ line-item unit conversion. Canonical units used throughout
# QuantityLineItem / BOQLineItem / MaterialRate are "m3", "m2", "kg",
# "Nos", "LS" - only "m3" and "m2" have an FPS equivalent.
# --------------------------------------------------------------------------

_CANONICAL_TO_FPS_UNIT = {"m3": "cft", "m2": "sqft"}
_QTY_FACTOR = {"m3": CFT_PER_CUM, "m2": SQFT_PER_SQM}


def display_unit(canonical_unit: str, unit_system: str) -> str:
    """The unit label to show for a given canonical unit + unit system."""
    if not is_fps(unit_system):
        return canonical_unit
    return _CANONICAL_TO_FPS_UNIT.get(canonical_unit, canonical_unit)


def display_quantity(value_si: float, canonical_unit: str, unit_system: str) -> float:
    """Convert an SI quantity (m3/m2/kg/Nos/LS) to its display equivalent."""
    if not is_fps(unit_system):
        return value_si
    factor = _QTY_FACTOR.get(canonical_unit)
    return value_si * factor if factor else value_si


def display_rate(rate_si: float, canonical_unit: str, unit_system: str) -> float:
    """Convert a rate quoted per canonical SI unit (e.g. PKR/m3) into the
    equivalent rate per display unit (e.g. PKR/cft), such that
    display_quantity * display_rate == si_quantity * si_rate (the amount
    is always unit-system-invariant)."""
    if not is_fps(unit_system):
        return rate_si
    factor = _QTY_FACTOR.get(canonical_unit)
    return rate_si / factor if factor else rate_si


def rate_to_si(rate_display: float, canonical_unit: str, unit_system: str) -> float:
    """Inverse of display_rate - used when the user edits a rate in the
    rate-book editor while FPS is selected, to convert back to the
    canonical per-m3/per-m2 rate that generate_boq() expects."""
    if not is_fps(unit_system):
        return rate_display
    factor = _QTY_FACTOR.get(canonical_unit)
    return rate_display * factor if factor else rate_display


def quantity_and_unit_for_display(value_si: float, canonical_unit: str, unit_system: str) -> Tuple[float, str]:
    return display_quantity(value_si, canonical_unit, unit_system), display_unit(canonical_unit, unit_system)


# --------------------------------------------------------------------------
# Wall-material label relabeling. The wall_material STRING itself is a
# lookup key into engineering.rules.MASONRY_UNIT_SIZES_M /
# MORTAR_VOLUME_FRACTION, so it must never change - only how it's
# displayed in the selectbox. This appends an inch-equivalent to any
# "NxNxNmm" dimension pattern embedded in the label for FPS display.
# --------------------------------------------------------------------------
_MM_DIMS_RE = re.compile(r"(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)x(\d+(?:\.\d+)?)mm")


def relabel_wall_material(label: str, unit_system: str) -> str:
    if not is_fps(unit_system):
        return label

    def _sub(m: "re.Match[str]") -> str:
        mm_vals = m.groups()
        in_vals = [f"{float(v) / 25.4:.1f}" for v in mm_vals]
        return "x".join(in_vals) + "in (" + "x".join(mm_vals) + "mm)"

    return _MM_DIMS_RE.sub(_sub, label)
