"""
Single source of truth for every data structure that flows through the
pipeline: AI extraction -> user edits -> engineering calculations ->
MTO -> BOQ -> export.

Keeping everything in Pydantic models (rather than loose dicts) means:
- The Groq JSON output is validated immediately (fail fast on bad AI output)
- Every numeric field can carry a confidence level + provenance note
- Streamlit forms, calculation functions, and exporters all share one
  contract, so a change here can't silently break one module without
  breaking the others too (Pydantic raises).
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ConfidenceLevel(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class Source(str, Enum):
    AI_EXTRACTED = "AI-extracted"
    DEFAULT_ASSUMPTION = "Default assumption"
    USER_EDITED = "User-edited"
    USER_INPUT = "User-input"


class UnitSystem(str, Enum):
    """Which unit system the user sees on input/output screens and in the
    exported MTO/BOQ. Every internal calculation in engineering/ and
    mto_boq/ ALWAYS operates in SI (m, m2, m3, kg) regardless of this
    setting - conversion happens only in the UI/export display layer
    (see utils/units.py)."""

    SI = "SI"
    FPS = "FPS"


class Estimate(BaseModel):
    """A single numeric field with confidence + provenance, editable by the user."""

    value: float
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    source: Source = Source.DEFAULT_ASSUMPTION
    note: str = ""

    def with_value(self, new_value: float) -> "Estimate":
        return Estimate(
            value=new_value,
            confidence=self.confidence,
            source=Source.USER_EDITED,
            note=self.note,
        )


# --------------------------------------------------------------------------
# Building parameters (populated by AI, then edited by the user)
# --------------------------------------------------------------------------


class FootingSpec(BaseModel):
    footing_type: str = "isolated"  # isolated | strip | raft | combined
    count: Estimate
    length_m: Estimate
    width_m: Estimate
    depth_m: Estimate


class ColumnSpec(BaseModel):
    count: Estimate
    width_m: Estimate  # 'b'
    depth_m: Estimate  # 'd'
    height_per_floor_m: Estimate


class BeamSpec(BaseModel):
    count: Estimate
    avg_length_m: Estimate
    width_m: Estimate
    depth_m: Estimate


class SlabSpec(BaseModel):
    area_per_floor_sqm: Estimate
    thickness_m: Estimate


class WallSpec(BaseModel):
    total_length_per_floor_m: Estimate
    height_m: Estimate
    thickness_m: Estimate
    wall_material: str = "Burnt clay brick (modular)"


class OpeningsSpec(BaseModel):
    door_count_per_floor: Estimate
    avg_door_area_sqm: Estimate
    window_count_per_floor: Estimate
    avg_window_area_sqm: Estimate


class ExtractedBuildingParams(BaseModel):
    num_floors: Estimate
    plinth_area_per_floor_sqm: Estimate
    footings: FootingSpec
    columns: ColumnSpec
    beams: BeamSpec
    slabs: SlabSpec
    walls: WallSpec
    openings: OpeningsSpec
    overall_notes: str = ""
    extraction_warnings: List[str] = Field(default_factory=list)


# --------------------------------------------------------------------------
# User-supplied project inputs (technical details, not read from drawing)
# --------------------------------------------------------------------------


class ProjectInputs(BaseModel):
    project_name: str = "Untitled Project"
    client_name: str = ""
    location: str = ""
    soil_type: str = "Ordinary soil"  # Soft/Ordinary/Hard/Murrum/Rock
    concrete_grade_footing: str = "M20"
    concrete_grade_column: str = "M20"
    concrete_grade_beam: str = "M20"
    concrete_grade_slab: str = "M20"
    pcc_grade: str = "M10"
    steel_grade: str = "Fe500"
    wall_material: str = "Burnt clay brick (modular 190x90x90mm)"
    wall_thickness_mm: int = 230
    plaster_thickness_internal_mm: int = 12
    plaster_thickness_external_mm: int = 18
    finish_level: str = "Standard"  # Basic | Standard | Premium
    include_flooring: bool = True
    include_waterproofing: bool = True
    include_painting: bool = True
    include_dpc: bool = True
    include_anti_termite: bool = True
    contingency_pct: float = 5.0
    currency: str = "PKR"
    unit_system: str = UnitSystem.SI.value  # "SI" or "FPS" - see UnitSystem


class WastageFactors(BaseModel):
    concrete_pct: float = 5.0
    steel_pct: float = 3.0
    brick_block_pct: float = 5.0
    plaster_pct: float = 10.0
    formwork_pct: float = 5.0
    flooring_pct: float = 5.0
    paint_pct: float = 5.0
    misc_pct: float = 5.0


# --------------------------------------------------------------------------
# Rates
# --------------------------------------------------------------------------


class MaterialRate(BaseModel):
    item_code: str
    description: str
    unit: str
    rate: float
    category: str


# --------------------------------------------------------------------------
# MTO / BOQ line items
# --------------------------------------------------------------------------


class QuantityLineItem(BaseModel):
    item_code: str
    description: str
    category: str
    unit: str
    quantity: float
    confidence: ConfidenceLevel
    formula: str
    inputs_used: Dict[str, float] = Field(default_factory=dict)
    assumptions: List[str] = Field(default_factory=list)
    # True for a derived procurement-reference line (e.g. the cement/sand/
    # aggregate that make up a concrete pour already priced as one composite
    # m3 rate) - its cost is already counted in `parent_item_code`'s BOQ
    # line, so generate_boq() must NOT create a separate priced line for it
    # (that would double-count the cost). Still shown in the MTO (Step 4)
    # because that's exactly the quantity someone needs to go buy cement/
    # sand/aggregate. See mto_boq/boq_generator.py and engineering/
    # calculations.py:concrete_material_breakdown()/mortar_material_breakdown().
    informational: bool = False
    parent_item_code: str = ""


class BOQLineItem(BaseModel):
    item_code: str
    description: str
    category: str
    unit: str
    quantity: float
    wastage_pct: float
    quantity_with_wastage: float
    rate: float
    amount: float
    confidence: ConfidenceLevel
    remarks: str = ""


class CostSummary(BaseModel):
    subtotal: float
    contingency_pct: float
    contingency_amount: float
    grand_total: float
    currency: str = "PKR"


class ProjectResult(BaseModel):
    project_inputs: ProjectInputs
    extracted_params: ExtractedBuildingParams
    mto_items: List[QuantityLineItem]
    boq_items: List[BOQLineItem]
    cost_summary: CostSummary
    generated_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
