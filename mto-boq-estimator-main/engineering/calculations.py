"""
Deterministic engineering calculations.

CRITICAL DESIGN RULE: every function in this file is a pure Python
function of plain numbers/Pydantic models. No LLM call happens here or is
ever allowed to happen here. The AI is only used upstream (ai/extraction.py)
to *guess* the input parameters (dimensions/counts); everything downstream
of that guess is standard, auditable civil-engineering arithmetic.

Every public "compute_*" function returns one or more `QuantityLineItem`
objects that carry:
  - the numeric quantity
  - the formula name (human readable)
  - the exact inputs used (so a user/engineer can hand-verify it)
  - a confidence level inherited from the weakest input Estimate
  - a list of assumption strings shown in the UI's traceability panel
"""
from __future__ import annotations

from typing import List

from engineering import rules
from models.schemas import (
    BeamSpec,
    ColumnSpec,
    ConfidenceLevel,
    Estimate,
    ExtractedBuildingParams,
    FootingSpec,
    OpeningsSpec,
    ProjectInputs,
    QuantityLineItem,
    SlabSpec,
    WallSpec,
)
from utils.helpers import combine_confidence

# --------------------------------------------------------------------------
# Excavation
# --------------------------------------------------------------------------


def compute_excavation(footings: FootingSpec, soil_type: str) -> QuantityLineItem:
    slope_factor = rules.SOIL_SIDE_SLOPE_FACTOR.get(soil_type, 1.05)
    ws = rules.EXCAVATION_WORKING_SPACE_M

    L = footings.length_m.value + 2 * ws
    W = footings.width_m.value + 2 * ws
    D = footings.depth_m.value
    n = footings.count.value

    volume = n * L * W * D * slope_factor

    return QuantityLineItem(
        item_code="EXC-01",
        description=f"Earthwork excavation in {soil_type.lower()} for footings (incl. working space)",
        category="Excavation",
        unit="m3",
        quantity=round(volume, 3),
        confidence=combine_confidence(footings.count, footings.length_m, footings.width_m, footings.depth_m),
        formula="V = n × (L + 2×working_space) × (W + 2×working_space) × D × soil_side_slope_factor",
        inputs_used={
            "footing_count": n,
            "footing_length_m": footings.length_m.value,
            "footing_width_m": footings.width_m.value,
            "footing_depth_m": D,
            "working_space_m": ws,
            "soil_side_slope_factor": slope_factor,
        },
        assumptions=[
            f"Isolated pad footing excavation assumed ({footings.footing_type}).",
            f"{ws*100:.0f} mm working space added on each side for shuttering.",
            f"Soil type '{soil_type}' side-slope/bulking factor = {slope_factor}.",
            "Backfill quantity is NOT separately deducted in this MVP (net excavation shown).",
        ],
    )


# --------------------------------------------------------------------------
# Cement / sand / aggregate procurement breakdown
# --------------------------------------------------------------------------
# These functions turn a cast volume (concrete OR mortar) into the raw
# materials someone actually has to go buy: cement bags, sand, and (for
# concrete only) coarse aggregate/crush. They are called right after each
# concrete/mortar QuantityLineItem is built (see the helper functions below
# and generate_all_quantities()) and return QuantityLineItems flagged
# `informational=True` - their cost is already inside the parent item's
# composite BOQ rate (e.g. FTG-CONC-01's PKR/m3 rate already covers its own
# cement+sand+aggregate+labour), so generate_boq() skips pricing them to
# avoid double-counting. They exist purely so the MTO can answer "how many
# bags of cement / how much sand / how much crush do I need to buy."


def concrete_material_breakdown(wet_volume_m3: float, grade_label: str) -> dict:
    """Standard nominal-mix, dry-volume-factor method: dry_volume =
    wet_volume x 1.54, then split by the grade's cement:sand:aggregate
    ratio parts. Indicative preliminary-estimation practice, not a lab mix
    design - see engineering/rules.py for the full method note."""
    cement_parts, sand_parts, agg_parts = rules.resolve_nominal_mix(grade_label)
    total_parts = cement_parts + sand_parts + agg_parts
    dry_volume_m3 = wet_volume_m3 * rules.DRY_VOLUME_FACTOR
    cement_volume_m3 = dry_volume_m3 * (cement_parts / total_parts)
    sand_volume_m3 = dry_volume_m3 * (sand_parts / total_parts)
    aggregate_volume_m3 = dry_volume_m3 * (agg_parts / total_parts)
    cement_bags = (cement_volume_m3 * rules.CEMENT_DENSITY_KG_PER_M3) / rules.CEMENT_BAG_WEIGHT_KG
    return {
        "mix_ratio": (cement_parts, sand_parts, agg_parts),
        "dry_volume_m3": dry_volume_m3,
        "cement_volume_m3": cement_volume_m3,
        "cement_bags": cement_bags,
        "sand_volume_m3": sand_volume_m3,
        "aggregate_volume_m3": aggregate_volume_m3,
    }


def mortar_material_breakdown(mortar_volume_m3: float, mix_ratio: tuple[float, float]) -> dict:
    """Same idea for cement:sand-only mortar (masonry bedding/jointing,
    plaster) - no coarse aggregate, and mortar's own (lower) dry-volume
    factor since there's no coarse material to bulk the loose mix up."""
    cement_parts, sand_parts = mix_ratio
    total_parts = cement_parts + sand_parts
    dry_volume_m3 = mortar_volume_m3 * rules.MORTAR_DRY_VOLUME_FACTOR
    cement_volume_m3 = dry_volume_m3 * (cement_parts / total_parts)
    sand_volume_m3 = dry_volume_m3 * (sand_parts / total_parts)
    cement_bags = (cement_volume_m3 * rules.CEMENT_DENSITY_KG_PER_M3) / rules.CEMENT_BAG_WEIGHT_KG
    return {
        "mix_ratio": (cement_parts, sand_parts),
        "dry_volume_m3": dry_volume_m3,
        "cement_volume_m3": cement_volume_m3,
        "cement_bags": cement_bags,
        "sand_volume_m3": sand_volume_m3,
    }


def _concrete_material_items(parent: QuantityLineItem, grade_label: str) -> List[QuantityLineItem]:
    bd = concrete_material_breakdown(parent.quantity, grade_label)
    c, s, a = bd["mix_ratio"]
    mix_str = f"{c:g}:{s:g}:{a:g}"
    common_inputs = {
        "wet_volume_m3": parent.quantity,
        "dry_volume_factor": rules.DRY_VOLUME_FACTOR,
        "mix_ratio_cement": c,
        "mix_ratio_sand": s,
        "mix_ratio_aggregate": a,
    }
    procurement_note = (
        "Procurement reference quantity only - its cost is already included in "
        f"{parent.item_code}'s composite rate above; do NOT price it again separately."
    )
    wastage_note = (
        "Net theoretical requirement (no site wastage/spillage margin added) - "
        "order a few percent extra for handling losses."
    )
    return [
        QuantityLineItem(
            item_code=f"{parent.item_code}-CEMENT",
            description=f"Cement for {parent.description} (nominal mix {mix_str})",
            category="Concrete Materials",
            unit="bags",
            quantity=round(bd["cement_bags"], 1),
            confidence=parent.confidence,
            formula="bags = wet_volume × dry_volume_factor × cement_ratio/total_ratio × cement_density ÷ bag_weight",
            inputs_used={**common_inputs, "cement_density_kg_per_m3": rules.CEMENT_DENSITY_KG_PER_M3, "bag_weight_kg": rules.CEMENT_BAG_WEIGHT_KG},
            assumptions=[f"Nominal mix {mix_str} (cement:sand:aggregate) assumed for grade {grade_label}.", f"{rules.CEMENT_BAG_WEIGHT_KG:.0f}kg bags @ {rules.CEMENT_DENSITY_KG_PER_M3:.0f} kg/m3 loose cement density.", procurement_note, wastage_note],
            informational=True,
            parent_item_code=parent.item_code,
        ),
        QuantityLineItem(
            item_code=f"{parent.item_code}-SAND",
            description=f"Sand for {parent.description} (nominal mix {mix_str})",
            category="Concrete Materials",
            unit="m3",
            quantity=round(bd["sand_volume_m3"], 3),
            confidence=parent.confidence,
            formula="sand_volume = wet_volume × dry_volume_factor × sand_ratio/total_ratio",
            inputs_used=dict(common_inputs),
            assumptions=[f"Nominal mix {mix_str} (cement:sand:aggregate) assumed for grade {grade_label}.", procurement_note, wastage_note],
            informational=True,
            parent_item_code=parent.item_code,
        ),
        QuantityLineItem(
            item_code=f"{parent.item_code}-AGG",
            description=f"Aggregate/crush for {parent.description} (nominal mix {mix_str})",
            category="Concrete Materials",
            unit="m3",
            quantity=round(bd["aggregate_volume_m3"], 3),
            confidence=parent.confidence,
            formula="aggregate_volume = wet_volume × dry_volume_factor × aggregate_ratio/total_ratio",
            inputs_used=dict(common_inputs),
            assumptions=[f"Nominal mix {mix_str} (cement:sand:aggregate) assumed for grade {grade_label}.", procurement_note, wastage_note],
            informational=True,
            parent_item_code=parent.item_code,
        ),
    ]


def _mortar_material_items(
    parent: QuantityLineItem, mortar_volume_m3: float, mix_ratio: tuple[float, float], mix_purpose: str
) -> List[QuantityLineItem]:
    """`mortar_volume_m3` is passed explicitly rather than read off
    `parent.quantity`, because `parent` isn't always a volume: masonry
    mortar (MAS-02) IS a volume, but plaster (PLAS-01/02) is stored as an
    AREA (m2) - the caller must convert area x thickness to a volume
    before calling this, or the cement/sand figures come out ~80x too
    high (plaster area treated as if it were already a cast volume)."""
    bd = mortar_material_breakdown(mortar_volume_m3, mix_ratio)
    c, s = bd["mix_ratio"]
    mix_str = f"{c:g}:{s:g}"
    common_inputs = {
        "mortar_volume_m3": mortar_volume_m3,
        "dry_volume_factor": rules.MORTAR_DRY_VOLUME_FACTOR,
        "mix_ratio_cement": c,
        "mix_ratio_sand": s,
    }
    procurement_note = (
        "Procurement reference quantity only - its cost is already included in "
        f"{parent.item_code}'s composite rate above; do NOT price it again separately."
    )
    wastage_note = "Net theoretical requirement (no site wastage/spillage margin added)."
    return [
        QuantityLineItem(
            item_code=f"{parent.item_code}-CEMENT",
            description=f"Cement for {mix_purpose} (mix {mix_str})",
            category="Concrete Materials",
            unit="bags",
            quantity=round(bd["cement_bags"], 1),
            confidence=parent.confidence,
            formula="bags = mortar_volume × dry_volume_factor × cement_ratio/total_ratio × cement_density ÷ bag_weight",
            inputs_used={**common_inputs, "cement_density_kg_per_m3": rules.CEMENT_DENSITY_KG_PER_M3, "bag_weight_kg": rules.CEMENT_BAG_WEIGHT_KG},
            assumptions=[f"Standard {mix_str} (cement:sand) mortar mix assumed for {mix_purpose}.", procurement_note, wastage_note],
            informational=True,
            parent_item_code=parent.item_code,
        ),
        QuantityLineItem(
            item_code=f"{parent.item_code}-SAND",
            description=f"Sand for {mix_purpose} (mix {mix_str})",
            category="Concrete Materials",
            unit="m3",
            quantity=round(bd["sand_volume_m3"], 3),
            confidence=parent.confidence,
            formula="sand_volume = mortar_volume × dry_volume_factor × sand_ratio/total_ratio",
            inputs_used=dict(common_inputs),
            assumptions=[f"Standard {mix_str} (cement:sand) mortar mix assumed for {mix_purpose}.", procurement_note, wastage_note],
            informational=True,
            parent_item_code=parent.item_code,
        ),
    ]


def compute_procurement_summary(items: List[QuantityLineItem]) -> List[QuantityLineItem]:
    """Rolls every per-member cement/sand/aggregate breakdown line up into
    one project-wide total each - the numbers most useful to actually hand
    to a supplier ("I need X bags of cement, Y m3 of sand, Z m3 of crush")."""
    cement_bags = sum(i.quantity for i in items if i.item_code.endswith("-CEMENT"))
    sand_m3 = sum(i.quantity for i in items if i.item_code.endswith("-SAND"))
    agg_m3 = sum(i.quantity for i in items if i.item_code.endswith("-AGG"))
    conf = ConfidenceLevel.LOW  # a sum of many thumb-rule-derived figures inherits the weakest confidence
    return [
        QuantityLineItem(
            item_code="SUMMARY-CEMENT",
            description="TOTAL cement required (all concrete + masonry mortar + plaster, project-wide)",
            category="Procurement Summary",
            unit="bags",
            quantity=round(cement_bags, 0),
            confidence=conf,
            formula="sum of every *-CEMENT line above",
            inputs_used={"line_items_summed": float(sum(1 for i in items if i.item_code.endswith("-CEMENT")))},
            assumptions=["Net theoretical requirement - add your own site wastage margin (commonly 3-5%) before ordering."],
            informational=True,
        ),
        QuantityLineItem(
            item_code="SUMMARY-SAND",
            description="TOTAL sand required (all concrete + masonry mortar + plaster, project-wide)",
            category="Procurement Summary",
            unit="m3",
            quantity=round(sand_m3, 2),
            confidence=conf,
            formula="sum of every *-SAND line above",
            inputs_used={"line_items_summed": float(sum(1 for i in items if i.item_code.endswith("-SAND")))},
            assumptions=["Net theoretical requirement - add your own site wastage margin (commonly 5-10%) before ordering."],
            informational=True,
        ),
        QuantityLineItem(
            item_code="SUMMARY-AGG",
            description="TOTAL aggregate/crush required (concrete only, project-wide)",
            category="Procurement Summary",
            unit="m3",
            quantity=round(agg_m3, 2),
            confidence=conf,
            formula="sum of every *-AGG line above",
            inputs_used={"line_items_summed": float(sum(1 for i in items if i.item_code.endswith("-AGG")))},
            assumptions=["Net theoretical requirement - add your own site wastage margin (commonly 5-10%) before ordering."],
            informational=True,
        ),
    ]


# --------------------------------------------------------------------------
# PCC (lean concrete) below footings
# --------------------------------------------------------------------------


def compute_pcc(footings: FootingSpec, pcc_grade: str) -> QuantityLineItem:
    proj = rules.PCC_PROJECTION_BEYOND_FOOTING_M
    t = rules.DEFAULT_PCC_THICKNESS_M

    L = footings.length_m.value + 2 * proj
    W = footings.width_m.value + 2 * proj
    n = footings.count.value

    volume = n * L * W * t

    return QuantityLineItem(
        item_code="PCC-01",
        description=f"PCC ({pcc_grade}) bedding below footings, {t*1000:.0f}mm thick",
        category="PCC",
        unit="m3",
        quantity=round(volume, 3),
        confidence=combine_confidence(footings.count, footings.length_m, footings.width_m),
        formula="V = n × (L + 2×projection) × (W + 2×projection) × thickness",
        inputs_used={
            "footing_count": n,
            "footing_length_m": footings.length_m.value,
            "footing_width_m": footings.width_m.value,
            "pcc_projection_m": proj,
            "pcc_thickness_m": t,
        },
        assumptions=[
            f"PCC projects {proj*1000:.0f} mm beyond footing edge on all sides.",
            f"Default PCC thickness {t*1000:.0f} mm (editable).",
            f"Grade {pcc_grade} assumed (nominal mix, not structurally designed).",
        ],
    )


# --------------------------------------------------------------------------
# Footings — concrete + reinforcement
# --------------------------------------------------------------------------


def compute_footing_concrete(footings: FootingSpec, grade: str) -> QuantityLineItem:
    n = footings.count.value
    L = footings.length_m.value
    W = footings.width_m.value
    D = footings.depth_m.value
    volume = n * L * W * D

    return QuantityLineItem(
        item_code="FTG-CONC-01",
        description=f"RCC {grade} in isolated footings",
        category="Footing",
        unit="m3",
        quantity=round(volume, 3),
        confidence=combine_confidence(footings.count, footings.length_m, footings.width_m, footings.depth_m),
        formula="V = n × L × W × D  (simple rectangular pad; stepped/sloped footings not modelled in MVP)",
        inputs_used={"footing_count": n, "length_m": L, "width_m": W, "depth_m": D},
        assumptions=[
            "Rectangular (non-stepped) pad footing shape assumed for volume calc.",
            f"Concrete grade {grade} assumed as declared by user; not structurally verified.",
        ],
    )


def compute_footing_steel(footing_concrete_qty: QuantityLineItem, footings: FootingSpec) -> QuantityLineItem:
    rate_min, rate_mid, rate_max = rules.STEEL_THUMB_RULE_KG_PER_M3["footing"]
    weight = footing_concrete_qty.quantity * rate_mid

    return QuantityLineItem(
        item_code="FTG-STEEL-01",
        description="Reinforcement steel in footings (thumb-rule allowance)",
        category="Reinforcement",
        unit="kg",
        quantity=round(weight, 1),
        confidence=ConfidenceLevel.LOW,  # thumb-rule steel is always Low-confidence by nature
        formula="Weight = footing_concrete_volume × thumb_rule_kg_per_m3",
        inputs_used={
            "footing_concrete_volume_m3": footing_concrete_qty.quantity,
            "thumb_rule_kg_per_m3": rate_mid,
        },
        assumptions=[
            f"Preliminary allowance only: {rate_min}-{rate_max} kg/m3 typical range, "
            f"mid-value {rate_mid} kg/m3 used.",
            "NOT a substitute for a structural design / bar bending schedule.",
        ],
    )


# --------------------------------------------------------------------------
# Columns — concrete + reinforcement
# --------------------------------------------------------------------------


def compute_column_concrete(columns: ColumnSpec, num_floors: float, grade: str) -> QuantityLineItem:
    n = columns.count.value
    b = columns.width_m.value
    d = columns.depth_m.value
    total_height = columns.height_per_floor_m.value * num_floors + rules.DEFAULT_PLINTH_HEIGHT_M
    volume = n * b * d * total_height

    return QuantityLineItem(
        item_code="COL-CONC-01",
        description=f"RCC {grade} in columns",
        category="Column",
        unit="m3",
        quantity=round(volume, 3),
        confidence=combine_confidence(columns.count, columns.width_m, columns.depth_m, columns.height_per_floor_m),
        formula="V = n × b × d × [(height_per_floor × num_floors) + plinth_height]",
        inputs_used={
            "column_count": n,
            "width_b_m": b,
            "depth_d_m": d,
            "height_per_floor_m": columns.height_per_floor_m.value,
            "num_floors": num_floors,
            "plinth_height_m": rules.DEFAULT_PLINTH_HEIGHT_M,
        },
        assumptions=[
            "Uniform column cross-section assumed across all floors (no staggered/tapering sections).",
            f"Plinth-level column stub height defaulted to {rules.DEFAULT_PLINTH_HEIGHT_M} m.",
        ],
    )


def compute_column_steel(column_concrete_qty: QuantityLineItem) -> QuantityLineItem:
    rate_min, rate_mid, rate_max = rules.STEEL_THUMB_RULE_KG_PER_M3["column"]
    weight = column_concrete_qty.quantity * rate_mid

    return QuantityLineItem(
        item_code="COL-STEEL-01",
        description="Reinforcement steel in columns (main bars + ties, thumb-rule allowance)",
        category="Reinforcement",
        unit="kg",
        quantity=round(weight, 1),
        confidence=ConfidenceLevel.LOW,
        formula="Weight = column_concrete_volume × thumb_rule_kg_per_m3",
        inputs_used={
            "column_concrete_volume_m3": column_concrete_qty.quantity,
            "thumb_rule_kg_per_m3": rate_mid,
        },
        assumptions=[f"Preliminary allowance only: {rate_min}-{rate_max} kg/m3 typical range, mid-value {rate_mid} kg/m3 used."],
    )


# --------------------------------------------------------------------------
# Beams — concrete + reinforcement
# --------------------------------------------------------------------------


def compute_beam_concrete(beams: BeamSpec, num_floors: float, grade: str) -> QuantityLineItem:
    levels = num_floors + 1  # floor beam levels + roof-level beams
    n_total = beams.count.value * levels
    L = beams.avg_length_m.value
    w = beams.width_m.value
    d = beams.depth_m.value
    volume = n_total * L * w * d

    return QuantityLineItem(
        item_code="BEAM-CONC-01",
        description=f"RCC {grade} in beams (incl. plinth & roof-level beams)",
        category="Beam",
        unit="m3",
        quantity=round(volume, 3),
        confidence=combine_confidence(beams.count, beams.avg_length_m, beams.width_m, beams.depth_m),
        formula="V = (beam_count_per_level × (num_floors + 1)) × avg_length × width × depth",
        inputs_used={
            "beam_count_per_level": beams.count.value,
            "levels_incl_roof": levels,
            "avg_length_m": L,
            "width_m": w,
            "depth_m": d,
        },
        assumptions=[
            "Same beam layout (count/size) repeated at every floor level, including one roof-level set.",
            "Does not distinguish plinth beam vs floor beam vs roof beam sizes separately in MVP.",
        ],
    )


def compute_beam_steel(beam_concrete_qty: QuantityLineItem) -> QuantityLineItem:
    rate_min, rate_mid, rate_max = rules.STEEL_THUMB_RULE_KG_PER_M3["beam"]
    weight = beam_concrete_qty.quantity * rate_mid

    return QuantityLineItem(
        item_code="BEAM-STEEL-01",
        description="Reinforcement steel in beams (thumb-rule allowance)",
        category="Reinforcement",
        unit="kg",
        quantity=round(weight, 1),
        confidence=ConfidenceLevel.LOW,
        formula="Weight = beam_concrete_volume × thumb_rule_kg_per_m3",
        inputs_used={"beam_concrete_volume_m3": beam_concrete_qty.quantity, "thumb_rule_kg_per_m3": rate_mid},
        assumptions=[f"Preliminary allowance only: {rate_min}-{rate_max} kg/m3 typical range, mid-value {rate_mid} kg/m3 used."],
    )


# --------------------------------------------------------------------------
# Slabs — concrete + reinforcement
# --------------------------------------------------------------------------


def compute_slab_concrete(slabs: SlabSpec, num_floors: float, grade: str) -> QuantityLineItem:
    area = slabs.area_per_floor_sqm.value
    t = slabs.thickness_m.value
    volume = area * t * num_floors

    return QuantityLineItem(
        item_code="SLAB-CONC-01",
        description=f"RCC {grade} in slabs (all floor slabs incl. roof)",
        category="Slab",
        unit="m3",
        quantity=round(volume, 3),
        confidence=combine_confidence(slabs.area_per_floor_sqm, slabs.thickness_m),
        formula="V = area_per_floor × thickness × num_floors",
        inputs_used={"area_per_floor_sqm": area, "thickness_m": t, "num_floors": num_floors},
        assumptions=[
            "'num_floors' here represents the number of RCC slab levels above plinth, including the roof slab.",
            "One-way vs two-way slab action not distinguished for the concrete volume calc.",
        ],
    )


def compute_slab_steel(slab_concrete_qty: QuantityLineItem) -> QuantityLineItem:
    rate_min, rate_mid, rate_max = rules.STEEL_THUMB_RULE_KG_PER_M3["slab"]
    weight = slab_concrete_qty.quantity * rate_mid

    return QuantityLineItem(
        item_code="SLAB-STEEL-01",
        description="Reinforcement steel in slabs (thumb-rule allowance)",
        category="Reinforcement",
        unit="kg",
        quantity=round(weight, 1),
        confidence=ConfidenceLevel.LOW,
        formula="Weight = slab_concrete_volume × thumb_rule_kg_per_m3",
        inputs_used={"slab_concrete_volume_m3": slab_concrete_qty.quantity, "thumb_rule_kg_per_m3": rate_mid},
        assumptions=[f"Preliminary allowance only: {rate_min}-{rate_max} kg/m3 typical range, mid-value {rate_mid} kg/m3 used."],
    )


# --------------------------------------------------------------------------
# Formwork / shuttering
# --------------------------------------------------------------------------


def compute_formwork(
    footings: FootingSpec,
    columns: ColumnSpec,
    beams: BeamSpec,
    slabs: SlabSpec,
    num_floors: float,
) -> List[QuantityLineItem]:
    items: List[QuantityLineItem] = []

    # Footings: 4 side faces
    ftg_area = footings.count.value * 2 * (footings.length_m.value + footings.width_m.value) * footings.depth_m.value
    items.append(
        QuantityLineItem(
            item_code="FORM-FTG-01",
            description="Formwork/shuttering to sides of footings",
            category="Formwork",
            unit="m2",
            quantity=round(ftg_area, 2),
            confidence=combine_confidence(footings.count, footings.length_m, footings.width_m, footings.depth_m),
            formula="A = n × 2×(L+W) × D  (side faces only)",
            inputs_used={
                "count": footings.count.value,
                "length_m": footings.length_m.value,
                "width_m": footings.width_m.value,
                "depth_m": footings.depth_m.value,
            },
            assumptions=["Only vertical side faces of footing formed; base cast on PCC (no bottom formwork)."],
        )
    )

    # Columns: perimeter x total height
    total_col_height = columns.height_per_floor_m.value * num_floors + rules.DEFAULT_PLINTH_HEIGHT_M
    col_area = columns.count.value * 2 * (columns.width_m.value + columns.depth_m.value) * total_col_height
    items.append(
        QuantityLineItem(
            item_code="FORM-COL-01",
            description="Formwork/shuttering to columns (4 faces)",
            category="Formwork",
            unit="m2",
            quantity=round(col_area, 2),
            confidence=combine_confidence(columns.count, columns.width_m, columns.depth_m, columns.height_per_floor_m),
            formula="A = n × 2×(b+d) × total_height",
            inputs_used={
                "count": columns.count.value,
                "width_b_m": columns.width_m.value,
                "depth_d_m": columns.depth_m.value,
                "total_height_m": total_col_height,
            },
            assumptions=["Full column perimeter formed on all 4 faces for the entire height."],
        )
    )

    # Beams: bottom + 2 sides (top open to receive slab, simplified)
    levels = num_floors + 1
    n_total_beams = beams.count.value * levels
    beam_area = n_total_beams * beams.avg_length_m.value * (beams.width_m.value + 2 * beams.depth_m.value)
    items.append(
        QuantityLineItem(
            item_code="FORM-BEAM-01",
            description="Formwork/shuttering to beams (soffit + 2 sides)",
            category="Formwork",
            unit="m2",
            quantity=round(beam_area, 2),
            confidence=combine_confidence(beams.count, beams.avg_length_m, beams.width_m, beams.depth_m),
            formula="A = n_total × L × (width + 2×depth)",
            inputs_used={
                "n_total_beams": n_total_beams,
                "avg_length_m": beams.avg_length_m.value,
                "width_m": beams.width_m.value,
                "depth_m": beams.depth_m.value,
            },
            assumptions=["Beam top face assumed cast monolithically with slab (no separate top formwork)."],
        )
    )

    # Slabs: soffit only
    slab_area = slabs.area_per_floor_sqm.value * num_floors
    items.append(
        QuantityLineItem(
            item_code="FORM-SLAB-01",
            description="Formwork/shuttering (centering + soffit) to slabs",
            category="Formwork",
            unit="m2",
            quantity=round(slab_area, 2),
            confidence=combine_confidence(slabs.area_per_floor_sqm),
            formula="A = area_per_floor × num_floors  (soffit area ≈ slab plan area)",
            inputs_used={"area_per_floor_sqm": slabs.area_per_floor_sqm.value, "num_floors": num_floors},
            assumptions=["Slab soffit formwork area approximated equal to slab plan area (edge strips ignored)."],
        )
    )

    return items


# --------------------------------------------------------------------------
# Masonry / blockwork
# --------------------------------------------------------------------------


def compute_masonry(walls: WallSpec, openings: OpeningsSpec, num_floors: float) -> tuple[List[QuantityLineItem], float]:
    items: List[QuantityLineItem] = []

    gross_wall_area = walls.total_length_per_floor_m.value * walls.height_m.value * num_floors
    opening_area = (
        openings.door_count_per_floor.value * openings.avg_door_area_sqm.value
        + openings.window_count_per_floor.value * openings.avg_window_area_sqm.value
    ) * num_floors
    net_wall_area = max(gross_wall_area - opening_area, 0.0)
    wall_volume = net_wall_area * walls.thickness_m.value

    mortar_fraction = rules.MORTAR_VOLUME_FRACTION.get(walls.wall_material, 0.30)
    unit_dims = rules.MASONRY_UNIT_SIZES_M.get(walls.wall_material, (0.20, 0.10, 0.10))
    unit_volume = unit_dims[0] * unit_dims[1] * unit_dims[2]

    net_unit_volume = wall_volume * (1 - mortar_fraction)
    mortar_volume = wall_volume * mortar_fraction
    unit_count = net_unit_volume / unit_volume if unit_volume else 0.0

    conf = combine_confidence(
        walls.total_length_per_floor_m,
        walls.height_m,
        openings.door_count_per_floor,
        openings.window_count_per_floor,
    )

    items.append(
        QuantityLineItem(
            item_code="MAS-01",
            description=f"Masonry/blockwork - {walls.wall_material}",
            category="Masonry",
            unit="Nos",
            quantity=round(unit_count),
            confidence=conf,
            formula="units = [ (gross_wall_area − opening_area) × thickness × (1 − mortar_fraction) ] / unit_volume",
            inputs_used={
                "gross_wall_area_sqm": gross_wall_area,
                "opening_area_sqm": opening_area,
                "wall_thickness_m": walls.thickness_m.value,
                "mortar_fraction": mortar_fraction,
                "unit_volume_m3": unit_volume,
            },
            assumptions=[
                f"Unit size assumed {unit_dims[0]*1000:.0f}x{unit_dims[1]*1000:.0f}x{unit_dims[2]*1000:.0f} mm (incl. mortar joint).",
                "Wall openings deducted using average door/window area × count; not per-opening schedule.",
            ],
        )
    )
    items.append(
        QuantityLineItem(
            item_code="MAS-02",
            description="Masonry mortar (bedding/jointing)",
            category="Masonry",
            unit="m3",
            quantity=round(mortar_volume, 3),
            confidence=conf,
            formula="mortar_volume = net_wall_volume × mortar_fraction",
            inputs_used={"net_wall_volume_m3": wall_volume, "mortar_fraction": mortar_fraction},
            assumptions=[f"Mortar fraction {mortar_fraction*100:.0f}% of wall volume for {walls.wall_material}."],
        )
    )
    return items, net_wall_area  # net_wall_area reused by plaster/paint


# --------------------------------------------------------------------------
# Plaster
# --------------------------------------------------------------------------


def compute_plaster(net_wall_area: float, walls: WallSpec, project_inputs: ProjectInputs) -> List[QuantityLineItem]:
    t_int = project_inputs.plaster_thickness_internal_mm / 1000.0
    t_ext = project_inputs.plaster_thickness_external_mm / 1000.0

    # MVP simplification: both internal and external plaster areas are
    # approximated as equal to the net wall area (i.e. one wall face each).
    # A more advanced version would split external-perimeter walls from
    # internal partition walls separately.
    area_each_face = net_wall_area

    items = [
        QuantityLineItem(
            item_code="PLAS-01",
            description=f"Internal cement plaster, {project_inputs.plaster_thickness_internal_mm}mm thick",
            category="Plaster",
            unit="m2",
            quantity=round(area_each_face, 2),
            confidence=ConfidenceLevel.MEDIUM,
            formula="area = net_wall_area (one face) — internal/external split simplified in MVP",
            inputs_used={"net_wall_area_sqm": net_wall_area, "thickness_m": t_int},
            assumptions=["Internal plaster area approximated equal to net wall area (single face); refine with actual internal/external split for higher accuracy."],
        ),
        QuantityLineItem(
            item_code="PLAS-02",
            description=f"External cement plaster, {project_inputs.plaster_thickness_external_mm}mm thick",
            category="Plaster",
            unit="m2",
            quantity=round(area_each_face, 2),
            confidence=ConfidenceLevel.MEDIUM,
            formula="area = net_wall_area (one face) — internal/external split simplified in MVP",
            inputs_used={"net_wall_area_sqm": net_wall_area, "thickness_m": t_ext},
            assumptions=["External plaster area approximated equal to net wall area (single face); refine with actual internal/external split for higher accuracy."],
        ),
    ]
    return items


# --------------------------------------------------------------------------
# Flooring / waterproofing / painting / DPC / anti-termite
# --------------------------------------------------------------------------


def compute_flooring(slabs: SlabSpec, num_floors: float) -> QuantityLineItem:
    area = slabs.area_per_floor_sqm.value * num_floors * rules.FLOORING_COVERAGE_FACTOR
    return QuantityLineItem(
        item_code="FLR-01",
        description="Flooring (tiling/finish) allowance",
        category="Flooring",
        unit="m2",
        quantity=round(area, 2),
        confidence=combine_confidence(slabs.area_per_floor_sqm),
        formula="area = plinth_area_per_floor × num_floors",
        inputs_used={"area_per_floor_sqm": slabs.area_per_floor_sqm.value, "num_floors": num_floors},
        assumptions=["Flooring area assumed equal to built-up floor area on every level (staircase/void areas not deducted in MVP)."],
    )


def compute_waterproofing(slabs: SlabSpec) -> QuantityLineItem:
    area = slabs.area_per_floor_sqm.value
    return QuantityLineItem(
        item_code="WP-01",
        description="Terrace/roof waterproofing",
        category="Waterproofing",
        unit="m2",
        quantity=round(area, 2),
        confidence=ConfidenceLevel.MEDIUM,
        formula="area = roof (top floor) plan area",
        inputs_used={"roof_area_sqm": area},
        assumptions=["Roof area assumed equal to the typical floor plate area; parapet/overhang not added in MVP."],
    )


def compute_painting(net_wall_area: float) -> List[QuantityLineItem]:
    return [
        QuantityLineItem(
            item_code="PAINT-01",
            description="Internal painting (2 coats over primer)",
            category="Painting",
            unit="m2",
            quantity=round(net_wall_area, 2),
            confidence=ConfidenceLevel.MEDIUM,
            formula="area = internal plaster area",
            inputs_used={"internal_plaster_area_sqm": net_wall_area},
            assumptions=["Paint area tied 1:1 to plaster area computed above."],
        ),
        QuantityLineItem(
            item_code="PAINT-02",
            description="External painting/texture (weatherproof, 2 coats)",
            category="Painting",
            unit="m2",
            quantity=round(net_wall_area, 2),
            confidence=ConfidenceLevel.MEDIUM,
            formula="area = external plaster area",
            inputs_used={"external_plaster_area_sqm": net_wall_area},
            assumptions=["Paint area tied 1:1 to plaster area computed above."],
        ),
    ]


def compute_dpc(walls: WallSpec) -> QuantityLineItem:
    volume = walls.total_length_per_floor_m.value * walls.thickness_m.value * rules.DPC_THICKNESS_M
    return QuantityLineItem(
        item_code="DPC-01",
        description="Damp Proof Course (DPC) at plinth level",
        category="DPC",
        unit="m3",
        quantity=round(volume, 3),
        confidence=combine_confidence(walls.total_length_per_floor_m),
        formula="V = ground_floor_wall_length × wall_thickness × DPC_thickness",
        inputs_used={
            "wall_length_m": walls.total_length_per_floor_m.value,
            "wall_thickness_m": walls.thickness_m.value,
            "dpc_thickness_m": rules.DPC_THICKNESS_M,
        },
        assumptions=["DPC applied once at plinth level along ground-floor wall footprint only."],
    )


def compute_anti_termite(plinth_area_per_floor: Estimate) -> QuantityLineItem:
    area = plinth_area_per_floor.value
    return QuantityLineItem(
        item_code="AT-01",
        description="Anti-termite chemical treatment",
        category="Anti-termite",
        unit="m2",
        quantity=round(area, 2),
        confidence=plinth_area_per_floor.confidence,
        formula="area = ground floor plinth area (soil treatment under building footprint + periphery)",
        inputs_used={"plinth_area_sqm": area},
        assumptions=["Applied once to ground-floor footprint; peripheral trench treatment not separately quantified in MVP."],
    )


# --------------------------------------------------------------------------
# Doors & windows (supply + installation)
# --------------------------------------------------------------------------


def compute_doors_windows(openings: OpeningsSpec, num_floors: float) -> List[QuantityLineItem]:
    """Doors/windows are already captured (count + avg area) for the wall-
    opening deduction in compute_masonry() - this prices them as their own
    procurable BOQ items, since a real residential BOQ has to budget for
    them (a door/window schedule is one of the biggest single procurement
    line items on a house). Priced per DOOR (a fixed-size assumption is
    reasonable for cost since door sizes vary little) but per m2 of WINDOW
    area (window cost scales with size, unlike doors)."""
    door_count = openings.door_count_per_floor.value * num_floors
    window_count = openings.window_count_per_floor.value * num_floors
    window_area = window_count * openings.avg_window_area_sqm.value

    return [
        QuantityLineItem(
            item_code="DOOR-01",
            description="Doors - supply & installation (frame/chaukhat + hardware, standard residential size)",
            category="Doors",
            unit="Nos",
            quantity=round(door_count),
            confidence=combine_confidence(openings.door_count_per_floor),
            formula="count = door_count_per_floor × num_floors",
            inputs_used={"door_count_per_floor": openings.door_count_per_floor.value, "num_floors": num_floors},
            assumptions=[
                "Rate assumes a standard-size residential door (~0.9m x 2.1m); unusually large/oversized doors will cost more per unit.",
                "Finish Level (Step 1) scales the door quality/cost tier - see engineering/rules.py FINISH_LEVEL_RATE_MULTIPLIERS.",
            ],
        ),
        QuantityLineItem(
            item_code="WINDOW-01",
            description="Windows - supply & installation (aluminium frame, glazing, hardware)",
            category="Windows",
            unit="m2",
            quantity=round(window_area, 2),
            confidence=combine_confidence(openings.window_count_per_floor, openings.avg_window_area_sqm),
            formula="area = window_count_per_floor × avg_window_area_sqm × num_floors",
            inputs_used={
                "window_count_per_floor": openings.window_count_per_floor.value,
                "avg_window_area_sqm": openings.avg_window_area_sqm.value,
                "num_floors": num_floors,
                "total_window_count": window_count,
            },
            assumptions=[
                "Priced per m2 of window area (standard aluminium sliding/casement) - UPVC or specialty glazing costs more.",
                "Finish Level (Step 1) scales the window quality/cost tier - see engineering/rules.py FINISH_LEVEL_RATE_MULTIPLIERS.",
            ],
        ),
    ]


# --------------------------------------------------------------------------
# Reinforcement sanity cross-check (not a BOQ line, just a diagnostic)
# --------------------------------------------------------------------------


def steel_sanity_check(structural_concrete_m3: float, total_steel_kg: float) -> dict:
    if structural_concrete_m3 <= 0:
        return {"kg_per_m3": 0.0, "status": "n/a", "message": "No structural concrete computed yet."}
    kg_per_m3 = total_steel_kg / structural_concrete_m3
    if 75 <= kg_per_m3 <= 160:
        status = "OK"
        message = f"Overall steel ratio {kg_per_m3:.0f} kg/m3 is within the typical residential RCC range (75-160 kg/m3)."
    else:
        status = "Review"
        message = (
            f"Overall steel ratio {kg_per_m3:.0f} kg/m3 is OUTSIDE the typical residential RCC range "
            f"(75-160 kg/m3). Re-check extracted dimensions/counts and thumb-rule settings."
        )
    return {"kg_per_m3": round(kg_per_m3, 1), "status": status, "message": message}


# --------------------------------------------------------------------------
# Master orchestrator
# --------------------------------------------------------------------------


def generate_all_quantities(params: ExtractedBuildingParams, project_inputs: ProjectInputs) -> List[QuantityLineItem]:
    """Run every calculation function and return the full flat MTO list.

    Every concrete/mortar-producing item is immediately followed by its own
    cement/sand/(aggregate) procurement breakdown (informational=True lines
    - see _concrete_material_items/_mortar_material_items) so the two never
    drift apart, and a project-wide cement/sand/aggregate rollup is added
    at the end (compute_procurement_summary)."""
    num_floors = params.num_floors.value
    items: List[QuantityLineItem] = []

    items.append(compute_excavation(params.footings, project_inputs.soil_type))

    pcc = compute_pcc(params.footings, project_inputs.pcc_grade)
    items.append(pcc)
    items.extend(_concrete_material_items(pcc, project_inputs.pcc_grade))

    ftg_conc = compute_footing_concrete(params.footings, project_inputs.concrete_grade_footing)
    items.append(ftg_conc)
    items.extend(_concrete_material_items(ftg_conc, project_inputs.concrete_grade_footing))
    items.append(compute_footing_steel(ftg_conc, params.footings))

    col_conc = compute_column_concrete(params.columns, num_floors, project_inputs.concrete_grade_column)
    items.append(col_conc)
    items.extend(_concrete_material_items(col_conc, project_inputs.concrete_grade_column))
    items.append(compute_column_steel(col_conc))

    beam_conc = compute_beam_concrete(params.beams, num_floors, project_inputs.concrete_grade_beam)
    items.append(beam_conc)
    items.extend(_concrete_material_items(beam_conc, project_inputs.concrete_grade_beam))
    items.append(compute_beam_steel(beam_conc))

    slab_conc = compute_slab_concrete(params.slabs, num_floors, project_inputs.concrete_grade_slab)
    items.append(slab_conc)
    items.extend(_concrete_material_items(slab_conc, project_inputs.concrete_grade_slab))
    items.append(compute_slab_steel(slab_conc))

    items.extend(compute_formwork(params.footings, params.columns, params.beams, params.slabs, num_floors))

    masonry_items, net_wall_area = compute_masonry(params.walls, params.openings, num_floors)
    items.extend(masonry_items)
    mortar_item = next((i for i in masonry_items if i.item_code == "MAS-02"), None)
    if mortar_item is not None:
        # MAS-02's quantity IS already a volume (m3) - use it directly.
        items.extend(
            _mortar_material_items(mortar_item, mortar_item.quantity, rules.MASONRY_MORTAR_MIX_RATIO, "masonry mortar (bedding/jointing)")
        )

    plaster_items = compute_plaster(net_wall_area, params.walls, project_inputs)
    items.extend(plaster_items)
    for p_item in plaster_items:
        # PLAS-01/02's quantity is an AREA (m2), not a volume - convert
        # area x thickness to get the actual mortar volume cast.
        if p_item.item_code == "PLAS-01":
            purpose = "internal plaster"
            thickness_m = project_inputs.plaster_thickness_internal_mm / 1000.0
        else:
            purpose = "external plaster"
            thickness_m = project_inputs.plaster_thickness_external_mm / 1000.0
        plaster_volume_m3 = p_item.quantity * thickness_m
        items.extend(_mortar_material_items(p_item, plaster_volume_m3, rules.PLASTER_MORTAR_MIX_RATIO, purpose))

    items.extend(compute_doors_windows(params.openings, num_floors))

    if project_inputs.include_flooring:
        items.append(compute_flooring(params.slabs, num_floors))
    if project_inputs.include_waterproofing:
        items.append(compute_waterproofing(params.slabs))
    if project_inputs.include_painting:
        items.extend(compute_painting(net_wall_area))
    if project_inputs.include_dpc:
        dpc = compute_dpc(params.walls)
        items.append(dpc)
        items.extend(_concrete_material_items(dpc, rules.DPC_ASSUMED_GRADE))
    if project_inputs.include_anti_termite:
        items.append(compute_anti_termite(params.plinth_area_per_floor_sqm))

    items.extend(compute_procurement_summary(items))

    return items
