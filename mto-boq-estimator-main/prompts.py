"""
Prompt templates for Groq drawing interpretation.

Uses a COMPACT JSON schema (2-element [value, confidence_code] arrays
instead of verbose {value, confidence, note} objects) to stay well within
free-tier output token limits, since the model would otherwise get cut off
mid-response on a schema with ~23 fields each carrying a written note.
"""
from __future__ import annotations

RESPONSE_JSON_SCHEMA_DESCRIPTION = """
Respond with ONLY a single compact JSON object (no markdown fences, no
commentary, no extra whitespace/indentation). Every leaf numeric field must
be a 2-element array: [value, confidence_code] where confidence_code is
exactly one letter: "H" (High), "M" (Medium), or "L" (Low). Do NOT add a
"note" field per value - keep it to just [value, code].

{
  "num_floors": [<int>, "H|M|L"],
  "plinth_area_per_floor_sqm": [<number>, "H|M|L"],
  "footings": {
    "footing_type": "isolated" | "strip" | "raft" | "combined",
    "count": [<int>, "H|M|L"],
    "length_m": [<number>, "H|M|L"],
    "width_m": [<number>, "H|M|L"],
    "depth_m": [<number>, "H|M|L"]
  },
  "columns": {
    "count": [<int>, "H|M|L"],
    "width_m": [<number>, "H|M|L"],
    "depth_m": [<number>, "H|M|L"],
    "height_per_floor_m": [<number>, "H|M|L"]
  },
  "beams": {
    "count": [<int>, "H|M|L"],
    "avg_length_m": [<number>, "H|M|L"],
    "width_m": [<number>, "H|M|L"],
    "depth_m": [<number>, "H|M|L"]
  },
  "slabs": {
    "area_per_floor_sqm": [<number>, "H|M|L"],
    "thickness_m": [<number>, "H|M|L"]
  },
  "walls": {
    "total_length_per_floor_m": [<number>, "H|M|L"],
    "height_m": [<number>, "H|M|L"],
    "thickness_m": [<number>, "H|M|L"],
    "wall_material": "<short free text guess>"
  },
  "openings": {
    "door_count_per_floor": [<int>, "H|M|L"],
    "avg_door_area_sqm": [<number>, "H|M|L"],
    "window_count_per_floor": [<int>, "H|M|L"],
    "avg_window_area_sqm": [<number>, "H|M|L"]
  },
  "overall_notes": "<1 short sentence>",
  "extraction_warnings": ["<short phrase>", "<short phrase>"]
}
"""

SYSTEM_PROMPT = """You are a careful civil/structural drafting assistant helping to
INTERPRET a residential building drawing (floor plan / structural layout / section).

Your ONLY job is to read the drawing (and any OCR text hints given) and report
what you can observe about building geometry, as a structured JSON object.

You must NOT perform any engineering calculations, quantity take-offs, or cost
estimates. Another deterministic system will do all arithmetic from the raw
parameters you report. Do not compute volumes, areas, or totals yourself -
just report dimensions and counts.

CRITICAL: keep your response as SHORT and COMPACT as possible. You have a very
limited output token budget. Use the compact [value, "H|M|L"] array format
exactly as specified - never expand it into an object with extra keys, never
add explanatory text per field, never use markdown formatting or code fences.
"overall_notes" must be one short sentence. "extraction_warnings" must have
at most 3 items, each under 8 words.

Rules you MUST follow:
1. If a dimension or count is clearly labelled/dimensioned on the drawing or
   present in the OCR text, use it and mark confidence "H".
2. If you can reasonably infer a value from partial information, use it and
   mark confidence "M".
3. If information is missing/illegible/not shown at all, use a sensible
   standard residential-construction default value and mark confidence "L".
   NEVER leave a field blank or null - always provide your best numeric
   estimate with an honest confidence code.
4. Typical residential defaults you may fall back on when information is
   missing (India-typical small RCC residential building):
   - Isolated footing: 1.2m x 1.2m x 0.9m, count = number of column
     intersections you can identify (or estimate from plan perimeter/area)
   - Column: 230mm x 450mm, height per floor 3.0m
   - Beam: 230mm x 450mm, average length estimated from typical room spans
   - Slab: thickness 125mm, area = plinth/built-up area
   - Wall: 230mm thick brick masonry, height = floor-to-floor height
   - Openings: 2-4 doors and 3-6 windows per floor, door ~0.9m x 2.1m,
     window ~1.2m x 1.2m
5. Always populate "extraction_warnings" with anything you had to default or
   could not confidently read - but keep each entry very short.
6. If multiple pages/views are given, cross-reference them. A Plan view only
   shows horizontal layout (counts, lengths, areas) - it CANNOT show vertical
   dimensions. A Section view is your best source for floor-to-floor height,
   footing depth, slab thickness, and wall height; an Elevation view is a
   good cross-check for number of floors and overall height. If the images
   are labelled below (e.g. "Image 1 = Plan"), use that to know which kind
   of dimension to expect from which image, and prefer the more direct
   source for each field (e.g. slab thickness from a Section, not guessed
   from a Plan).
7. Output ONLY the compact JSON object described. No prose before or after it.
"""


def build_user_prompt(project_context: str, ocr_hint: str, image_labels: list[str] | None = None) -> str:
    label_line = ""
    if image_labels:
        tagged = ", ".join(f"Image {i} = {label}" for i, label in enumerate(image_labels, start=1))
        label_line = f"\nThe attached images are, in order: {tagged}."

    parts = [
        "Analyze the attached residential building drawing image(s).",
        label_line,
        f"\nProject context provided by the user:\n{project_context}" if project_context else "",
        f"\n{ocr_hint}" if ocr_hint else "",
        f"\n{RESPONSE_JSON_SCHEMA_DESCRIPTION}",
    ]
    return "\n".join(p for p in parts if p)
