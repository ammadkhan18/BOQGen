"""
Loads and manages the editable material/labour rate book.

Rates start from `data/material_rates.json` but are fully editable in the
Streamlit session (see ui/components.py) before BOQ costing runs. Nothing
here calls the AI - rates are either the shipped defaults or user-entered.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List

from models.schemas import MaterialRate

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
RATE_FILE = DATA_DIR / "material_rates.json"


def load_default_rates() -> List[MaterialRate]:
    with open(RATE_FILE, "r", encoding="utf-8") as f:
        payload = json.load(f)
    return [MaterialRate(**row) for row in payload["rates"]]


def rates_to_dict(rates: List[MaterialRate]) -> Dict[str, MaterialRate]:
    return {r.item_code: r for r in rates}


def load_default_assumptions() -> dict:
    with open(DATA_DIR / "default_assumptions.json", "r", encoding="utf-8") as f:
        return json.load(f)
