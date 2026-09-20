"""
Orchestrates the AI extraction step:
  images + OCR hints + project context --[Groq vision LLM]--> raw JSON
  raw JSON --[validate/map]--> ExtractedBuildingParams (Pydantic)

If the Groq call fails, times out, or returns malformed JSON, this module
NEVER lets the app crash - it falls back to a fully-defaulted
ExtractedBuildingParams (all fields Low confidence, sourced as
"Default assumption") so the user can still proceed and fill everything in
manually on the verification screen. This fallback path is exercised
whenever `extract_building_params` catches an exception.
"""
from __future__ import annotations

import json
import logging
from typing import List, Tuple

from PIL import Image
from pydantic import ValidationError

from ai.groq_client import GroqClientError, call_vision_model
from ai.prompts import SYSTEM_PROMPT, build_user_prompt
from models.schemas import (
    BeamSpec,
    ColumnSpec,
    ConfidenceLevel,
    Estimate,
    ExtractedBuildingParams,
    FootingSpec,
    OpeningsSpec,
    Source,
    SlabSpec,
    WallSpec,
)

logger = logging.getLogger(__name__)


def _to_estimate(d, source: Source = Source.AI_EXTRACTED) -> Estimate:
    """Parses the compact [value, "H|M|L"] array format. Also accepts the
    older {value, confidence, note} object format for backward compatibility.
    """
    letter_map = {"H": "High", "M": "Medium", "L": "Low", "HIGH": "High", "MEDIUM": "Medium", "LOW": "Low"}

    if isinstance(d, (list, tuple)) and len(d) >= 1:
        value = d[0]
        conf_raw = str(d[1]).strip().upper() if len(d) > 1 else "M"
        note = ""
    elif isinstance(d, dict) and "value" in d:
        value = d["value"]
        conf_raw = str(d.get("confidence", "M")).strip().upper()
        note = str(d.get("note", ""))[:300]
    else:
        raise ValueError(f"Malformed estimate field: {d!r}")

    confidence = ConfidenceLevel(letter_map.get(conf_raw, "Medium"))
    return Estimate(value=float(value), confidence=confidence, source=source, note=note)


def _map_json_to_params(raw: dict) -> ExtractedBuildingParams:
    footings_raw = raw["footings"]
    columns_raw = raw["columns"]
    beams_raw = raw["beams"]
    slabs_raw = raw["slabs"]
    walls_raw = raw["walls"]
    openings_raw = raw["openings"]

    return ExtractedBuildingParams(
        num_floors=_to_estimate(raw["num_floors"]),
        plinth_area_per_floor_sqm=_to_estimate(raw["plinth_area_per_floor_sqm"]),
        footings=FootingSpec(
            footing_type=footings_raw.get("footing_type", "isolated"),
            count=_to_estimate(footings_raw["count"]),
            length_m=_to_estimate(footings_raw["length_m"]),
            width_m=_to_estimate(footings_raw["width_m"]),
            depth_m=_to_estimate(footings_raw["depth_m"]),
        ),
        columns=ColumnSpec(
            count=_to_estimate(columns_raw["count"]),
            width_m=_to_estimate(columns_raw["width_m"]),
            depth_m=_to_estimate(columns_raw["depth_m"]),
            height_per_floor_m=_to_estimate(columns_raw["height_per_floor_m"]),
        ),
        beams=BeamSpec(
            count=_to_estimate(beams_raw["count"]),
            avg_length_m=_to_estimate(beams_raw["avg_length_m"]),
            width_m=_to_estimate(beams_raw["width_m"]),
            depth_m=_to_estimate(beams_raw["depth_m"]),
        ),
        slabs=SlabSpec(
            area_per_floor_sqm=_to_estimate(slabs_raw["area_per_floor_sqm"]),
            thickness_m=_to_estimate(slabs_raw["thickness_m"]),
        ),
        walls=WallSpec(
            total_length_per_floor_m=_to_estimate(walls_raw["total_length_per_floor_m"]),
            height_m=_to_estimate(walls_raw["height_m"]),
            thickness_m=_to_estimate(walls_raw["thickness_m"]),
            wall_material=walls_raw.get("wall_material", "Burnt clay brick (modular 190x90x90mm)"),
        ),
        openings=OpeningsSpec(
            door_count_per_floor=_to_estimate(openings_raw["door_count_per_floor"]),
            avg_door_area_sqm=_to_estimate(openings_raw["avg_door_area_sqm"]),
            window_count_per_floor=_to_estimate(openings_raw["window_count_per_floor"]),
            avg_window_area_sqm=_to_estimate(openings_raw["avg_window_area_sqm"]),
        ),
        overall_notes=str(raw.get("overall_notes", ""))[:1000],
        extraction_warnings=[str(w)[:300] for w in raw.get("extraction_warnings", [])],
    )


def default_building_params(
    wall_thickness_mm: float = 230.0,
    wall_material: str = "Burnt clay brick (modular 190x90x90mm)",
) -> ExtractedBuildingParams:
    """Fully-defaulted fallback used when AI extraction is unavailable or
    fails, and as the starting point for the 'skip AI, enter manually'
    path. All values are standard small-residential defaults, all Low
    confidence, so the UI visibly nudges the user to review every field.

    `wall_thickness_mm`/`wall_material` seed the wall estimate from the
    Step 1 "Wall Thickness"/"Wall Material" selectors: with no drawing to
    read the real wall construction off of, the user's own explicit Step 1
    choice is the best information available. Without this, these fields
    silently defaulted to a fixed 230mm burnt-clay-brick wall regardless of
    what was picked in Step 1 - and since the masonry unit-count/mortar
    calculation in engineering/calculations.py keys off THIS wall_material
    (not project_inputs.wall_material, which is display-only in the
    exports), that mismatch could make the exported BOQ describe and price
    a completely different wall material than the one shown in the
    project's own cover/info table.
    """
    def est(v: float, note: str = "Standard default - please verify") -> Estimate:
        return Estimate(value=v, confidence=ConfidenceLevel.LOW, source=Source.DEFAULT_ASSUMPTION, note=note)

    return ExtractedBuildingParams(
        num_floors=est(1, "Default: single storey"),
        plinth_area_per_floor_sqm=est(100.0, "Default: 100 sqm built-up area"),
        footings=FootingSpec(
            footing_type="isolated",
            count=est(9, "Default: 3x3 column grid"),
            length_m=est(1.2),
            width_m=est(1.2),
            depth_m=est(0.9),
        ),
        columns=ColumnSpec(
            count=est(9, "Default: 3x3 column grid"),
            width_m=est(0.23),
            depth_m=est(0.45),
            height_per_floor_m=est(3.0),
        ),
        beams=BeamSpec(
            count=est(12, "Default: perimeter + a few internal beams"),
            avg_length_m=est(4.0),
            width_m=est(0.23),
            depth_m=est(0.45),
        ),
        slabs=SlabSpec(area_per_floor_sqm=est(100.0), thickness_m=est(0.125)),
        walls=WallSpec(
            total_length_per_floor_m=est(45.0, "Default: perimeter + a few partitions for ~100 sqm plan"),
            height_m=est(3.0),
            thickness_m=est(wall_thickness_mm / 1000.0, "From Step 1 'Wall Thickness' selection"),
            wall_material=wall_material,
        ),
        openings=OpeningsSpec(
            door_count_per_floor=est(4),
            avg_door_area_sqm=est(1.89, "0.9m x 2.1m standard door"),
            window_count_per_floor=est(5),
            avg_window_area_sqm=est(1.44, "1.2m x 1.2m standard window"),
        ),
        overall_notes="Default assumptions used (no AI extraction performed or extraction failed).",
        extraction_warnings=["All values are generic defaults - please review and edit every field before proceeding."],
    )


def extract_building_params(
    api_key: str,
    images: List[Image.Image],
    project_context: str = "",
    ocr_hint: str = "",
    image_labels: List[str] | None = None,
    wall_thickness_mm: float = 230.0,
    wall_material: str = "Burnt clay brick (modular 190x90x90mm)",
) -> Tuple[ExtractedBuildingParams, str, List[str]]:
    """Returns (params, raw_model_output_text, error_messages).

    `image_labels`, if given, must be the same length/order as `images`
    (e.g. ["Plan", "Section", "Elevation"]) - it's threaded into the
    prompt so the model knows which view to read each kind of dimension
    from (see ai/prompts.py rule 6).

    error_messages is empty on success. On any failure, params falls back
    to `default_building_params()` and error_messages explains why, so the
    UI can show a clear (non-crashing) warning banner.
    """
    errors: List[str] = []
    user_prompt = build_user_prompt(project_context, ocr_hint, image_labels)

    try:
        raw_text = call_vision_model(
            api_key=api_key,
            system_prompt=SYSTEM_PROMPT,
            user_prompt=user_prompt,
            images=images,
        )
    except GroqClientError as exc:
        logger.warning("Groq call failed, using defaults: %s", exc)
        return default_building_params(wall_thickness_mm, wall_material), "", [str(exc)]

    try:
        raw_json = json.loads(raw_text)
        params = _map_json_to_params(raw_json)
        return params, raw_text, errors
    except (json.JSONDecodeError, KeyError, ValueError, ValidationError) as exc:
        logger.warning("Failed to parse/validate Groq JSON output, using defaults: %s", exc)
        errors.append(
            "The AI's response could not be parsed into valid building parameters "
            f"({type(exc).__name__}: {exc}). Falling back to standard defaults - "
            "please review and edit every field below."
        )
        return default_building_params(wall_thickness_mm, wall_material), raw_text, errors
