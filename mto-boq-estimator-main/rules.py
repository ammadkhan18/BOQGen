"""
Thumb-rule constants and default engineering assumptions used by
engineering/calculations.py.

These are typical values used in preliminary/conceptual estimation for
small residential RCC buildings (Indian practice, commonly cited in
estimation textbooks and CPWD/state DSR-style guidance). They are DEFAULTS
ONLY — every one of them is editable from the Streamlit UI before the BOQ
is finalized, and none of them should be treated as a structural design
input.

Where a rule is a range in common practice, we pick the mid-point as the
default and note the range in the `note`/help text shown in the UI.
"""
from __future__ import annotations

# Dry volume factor: converts wet (compacted) concrete volume to the dry
# volume of loose materials (cement+sand+aggregate) needed - standard
# factor used in Indian estimation practice.
DRY_VOLUME_FACTOR = 1.54

# Excavation: extra working space added on each side of a footing/trench
# for shuttering & working room.
EXCAVATION_WORKING_SPACE_M = 0.15

# Excavation depth safety/side-slope allowance multiplier for soils that
# require battering (very approximate, MVP-level only).
SOIL_SIDE_SLOPE_FACTOR = {
    "Soft soil": 1.15,
    "Ordinary soil": 1.05,
    "Hard soil": 1.0,
    "Murrum/Gravel": 1.0,
    "Rock": 1.0,
}

# PCC (lean concrete / mud mat) below footings
DEFAULT_PCC_THICKNESS_M = 0.075  # 75 mm
PCC_PROJECTION_BEYOND_FOOTING_M = 0.075  # 75 mm each side beyond footing edge

# Reinforcement thumb rules: kg of steel per m3 of concrete, by member type.
# (min, default/mid, max) - source: common preliminary-estimation ranges.
STEEL_THUMB_RULE_KG_PER_M3 = {
    "footing": (60.0, 80.0, 100.0),
    "column": (140.0, 170.0, 200.0),
    "beam": (110.0, 135.0, 160.0),
    "slab": (70.0, 85.0, 100.0),
    "plinth_beam": (100.0, 120.0, 140.0),
}

# Concrete grade -> approximate nominal mix ratio (cement:sand:aggregate)
# used both for the cement/sand/aggregate procurement breakdown
# (compute_concrete_material_breakdown in calculations.py) and for
# indicative material-split notes - NOT for structural design.
# M7.5 is included because it's a selectable PCC grade (PCC_GRADE_OPTIONS
# below) even though no structural member ever uses it.
CONCRETE_GRADE_NOMINAL_MIX = {
    "M7.5": (1, 4, 8),
    "M10": (1, 3, 6),
    "M15": (1, 2, 4),
    "M20": (1, 1.5, 3),
    "M25": (1, 1, 2),
}


def resolve_nominal_mix(grade_label: str) -> tuple[float, float, float]:
    """Resolves a grade label to its (cement, sand, aggregate) nominal mix
    ratio - works whether `grade_label` is an SI label ("M20", already a
    CONCRETE_GRADE_NOMINAL_MIX key) or an FPS label ("3000 psi", which
    isn't a key on its own). FPS labels are resolved via their position in
    CONCRETE_GRADE_OPTIONS/PCC_GRADE_OPTIONS's "FPS" list, which is aligned
    1:1 by index with the matching "SI" list (see the comment on those
    constants below) - so "3000 psi" (index 2) maps to "M20" (index 2),
    whichever grade selector/unit system the project was set up with.
    Falls back to the M20 mix if the label is unrecognized, so a bad/custom
    grade string never crashes the material breakdown."""
    if grade_label in CONCRETE_GRADE_NOMINAL_MIX:
        return CONCRETE_GRADE_NOMINAL_MIX[grade_label]
    for options in (CONCRETE_GRADE_OPTIONS, PCC_GRADE_OPTIONS):
        fps_list = options.get("FPS", [])
        si_list = options.get("SI", [])
        if grade_label in fps_list:
            idx = fps_list.index(grade_label)
            if idx < len(si_list) and si_list[idx] in CONCRETE_GRADE_NOMINAL_MIX:
                return CONCRETE_GRADE_NOMINAL_MIX[si_list[idx]]
    return CONCRETE_GRADE_NOMINAL_MIX["M20"]

# Grade/strength-designation option lists shown in the UI, per unit system.
# These ARE now also used in a calculation: resolve_nominal_mix() (above)
# uses each list's index alignment to map an FPS grade label back to its
# SI-equivalent nominal mix. Equivalent strength pairs (1 MPa ~= 145 psi)
# line up at the same list index in both "SI" and "FPS" below, so the
# default selectbox index AND resolve_nominal_mix() both work unchanged for
# either unit system.
# NOTE: "SI" is listed explicitly (NOT derived from
# CONCRETE_GRADE_NOMINAL_MIX.keys()) because that dict also carries "M7.5"
# for PCC's grade list below - concrete structural members never use M7.5,
# so it must stay out of this 4-item list to keep the SI/FPS index
# alignment correct.
CONCRETE_GRADE_OPTIONS = {
    "SI": ["M10", "M15", "M20", "M25"],
    "FPS": ["1500 psi", "2200 psi", "3000 psi", "3600 psi"],
}
CONCRETE_GRADE_DEFAULT_INDEX = 2  # M20 / 3000 psi - standard residential grade

PCC_GRADE_OPTIONS = {
    "SI": ["M7.5", "M10", "M15"],
    "FPS": ["1100 psi", "1500 psi", "2200 psi"],
}
PCC_GRADE_DEFAULT_INDEX = 1  # M10 / 1500 psi

STEEL_GRADE_OPTIONS = {
    "SI": ["Fe415", "Fe500", "Fe550"],
    "FPS": ["Grade 40 (40,000 psi)", "Grade 60 (60,000 psi)", "Grade 75 (75,000 psi)"],
}
STEEL_GRADE_DEFAULT_INDEX = 1  # Fe500 / Grade 60 - Grade 60 is Pakistan's standard residential rebar

# Unit weight of steel reinforcement (kg/m3) - standard constant, used only
# for cross-checks / sanity notes, not for the primary steel-quantity calc
# (which uses the thumb-rule kg/m3-of-concrete method above).
STEEL_DENSITY_KG_PER_M3 = 7850.0

# Masonry unit sizes (m) - length x height x width, modular with 10mm mortar
MASONRY_UNIT_SIZES_M = {
    "Burnt clay brick (modular 190x90x90mm)": (0.20, 0.10, 0.10),
    "Burnt clay brick (traditional 230x110x75mm)": (0.24, 0.12, 0.085),
    "AAC block (600x200x200mm)": (0.61, 0.21, 0.20),
    "Concrete solid block (400x200x200mm)": (0.41, 0.21, 0.20),
    "CSEB / stabilized mud block (300x150x100mm)": (0.31, 0.16, 0.10),
}

# Mortar volume as a fraction of gross wall volume (rest is masonry units)
MORTAR_VOLUME_FRACTION = {
    "Burnt clay brick (modular 190x90x90mm)": 0.30,
    "Burnt clay brick (traditional 230x110x75mm)": 0.30,
    "AAC block (600x200x200mm)": 0.03,  # thin-bed adhesive joints
    "Concrete solid block (400x200x200mm)": 0.12,
    "CSEB / stabilized mud block (300x150x100mm)": 0.05,
}

# Formwork contact-area multipliers relative to concrete surfaces (MVP
# simplification): we compute actual contact faces per member type in
# calculations.py rather than a single blanket multiplier.

# Flooring / waterproofing / paint coverage defaults
FLOORING_COVERAGE_FACTOR = 1.0  # 1 m2 built-up ~ 1 m2 flooring (simplified)
WATERPROOFING_LAYERS_DEFAULT = 1

# DPC (damp proof course) thickness at plinth level
DPC_THICKNESS_M = 0.025  # 25 mm

# Anti-termite treatment is priced per sqm of plinth area (chemical barrier)

DEFAULT_FLOOR_TO_FLOOR_HEIGHT_M = 3.0
DEFAULT_FOOTING_DEPTH_M = 1.2
DEFAULT_PLINTH_HEIGHT_M = 0.6

# --------------------------------------------------------------------------
# Cement / sand / aggregate procurement breakdown
# --------------------------------------------------------------------------
# Standard "nominal mix, dry-volume-factor" method for splitting a cast
# concrete/mortar volume into the raw materials someone actually has to buy
# - see engineering/calculations.py:concrete_material_breakdown() and
# mortar_material_breakdown(). This is indicative/preliminary-estimation
# practice (same status as every other thumb rule in this file), not a lab
# mix design - always cross-check against your supplier's own guidance.

CEMENT_BAG_WEIGHT_KG = 50.0
CEMENT_DENSITY_KG_PER_M3 = 1440.0  # loose/bulk density of OPC cement powder
SAND_DENSITY_KG_PER_M3 = 1600.0  # loose bulk density (typical range 1450-1750)
AGGREGATE_DENSITY_KG_PER_M3 = 1550.0  # loose bulk density of crushed stone/"crush" (typical range 1450-1600)

# Mortar (cement:sand only - no coarse aggregate) uses a lower dry-volume
# factor than concrete (1.33 vs 1.54) since there's no coarse aggregate to
# bulk the loose mix up as much - standard value in Indian/Pakistani
# estimation references.
MORTAR_DRY_VOLUME_FACTOR = 1.33
MASONRY_MORTAR_MIX_RATIO = (1, 6)  # cement:sand - standard brick/block bedding & jointing mortar
PLASTER_MORTAR_MIX_RATIO = (1, 4)  # cement:sand - standard smooth cement plaster (residential)

# DPC (damp-proof course) has no dedicated grade selector in Step 1 - assume
# a typical DPC-grade mix (M15-equivalent) purely for its own cement/sand/
# aggregate breakdown.
DPC_ASSUMED_GRADE = "M15"

# --------------------------------------------------------------------------
# Finish Level -> BOQ rate multipliers
# --------------------------------------------------------------------------
# "Finish Level" (Basic / Standard / Premium, set in Step 1) never changes a
# quantity - the same floor area still gets floored, the same wall area
# still gets plastered/painted. What it changes is the MATERIAL GRADE used
# to cover that area, which the BOQ generator applies as a rate multiplier
# on top of the rate-book's Flooring/Painting/Plaster rates (see
# mto_boq/boq_generator.py:generate_boq). The rate book's own default rates
# (data/material_rates.json) represent the "Standard" tier, so Standard is
# always a 1.00x no-op.
#
# Multipliers are derived from researched September-2026 Pakistani market
# price spreads (material + labour, PKR/sqft, converted to the ratio
# between tiers so they're independent of any single rate-book edit):
#   - Flooring: economy ceramic tile (~PKR 120-450/sqft) vs mid-range
#     vitrified/porcelain (~PKR 350-1,000+/sqft) vs premium imported
#     porcelain/marble (~PKR 800-2,500+/sqft installed).
#   - Painting: budget distemper (~PKR 40-90/sqft applied) vs mid-range
#     plastic emulsion (~PKR 90-160/sqft applied) vs premium weathershield/
#     texture finishes (~PKR 160-250+/sqft applied).
#   - Plaster: single-coat rendering (~PKR 64-92/sqft) vs smooth
#     double-coat finish-ready plaster (~PKR 86-125/sqft, the rate book's
#     "Standard") vs a premium/waterproof + wall-putty finish (~PKR
#     100-145+/sqft, plus an allowance for putty/corner-beading work not
#     separately broken out in these sources).
#   - Doors: economy flush/PVC door with basic frame (~PKR 8,000-12,000/
#     door + hardware) vs mid-range semi-solid/veneer door (~PKR 25,000-
#     30,000/door + frame, the rate book's "Standard") vs solid
#     Deodar/Sheesham/Mahogany (~PKR 35,000-130,000+/door) - door prices
#     vary hugely by wood species, so this spread is wide by nature.
#   - Windows: economy fixed aluminium (~PKR 1,200-1,800/sqft) vs
#     standard sliding/casement aluminium (~PKR 1,500-2,500+/sqft, the
#     rate book's "Standard") vs thermal-break/UPVC premium glazing
#     (~PKR 3,500-5,500/sqft).
# These are indicative MVP-level multipliers, not a substitute for actual
# material-brand quotations - like every other default in this app, they
# are meant to get a preliminary estimate "in the right ballpark," and the
# rate book itself remains fully editable in Step 5.
FINISH_LEVEL_RATE_MULTIPLIERS = {
    "Basic": {"Flooring": 0.65, "Painting": 0.55, "Plaster": 0.85, "Doors": 0.45, "Windows": 0.70},
    "Standard": {"Flooring": 1.00, "Painting": 1.00, "Plaster": 1.00, "Doors": 1.00, "Windows": 1.00},
    "Premium": {"Flooring": 1.85, "Painting": 1.65, "Plaster": 1.20, "Doors": 2.55, "Windows": 2.05},
}
