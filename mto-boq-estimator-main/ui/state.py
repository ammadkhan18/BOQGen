"""
Centralizes Streamlit `st.session_state` initialization so app.py and the
UI components don't scatter `if "x" not in st.session_state` checks
everywhere.
"""
from __future__ import annotations

import streamlit as st

from ai.extraction import default_building_params
from models.schemas import ProjectInputs, WastageFactors
from mto_boq.rates import load_default_rates


def init_session_state():
    defaults = {
        "step": 1,
        "groq_api_key": "",
        "uploaded_files": [],  # list of {"name": str, "bytes": bytes, "view_tag": str}
        "uploaded_images": [],
        "uploaded_image_labels": [],
        "ocr_hint_text": "",
        "project_inputs": ProjectInputs(),
        "extracted_params": None,
        "raw_ai_response": "",
        "ai_errors": [],
        "wastage_factors": WastageFactors(),
        "rate_book": {r.item_code: r for r in load_default_rates()},
        "mto_items": None,
        "boq_items": None,
        "cost_summary": None,
        "used_ai": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def reset_project():
    """Wipes everything tied to the CURRENT project - drawing/AI results
    AND the project inputs/rate-book/wastage edits a user made in Steps
    1/5 - so "Start New Project" actually starts from a clean slate rather
    than silently carrying the previous project's name/client/grades/
    custom rates into the next one."""
    keys_to_clear = [
        "uploaded_files",
        "uploaded_images",
        "uploaded_image_labels",
        "ocr_hint_text",
        "extracted_params",
        "raw_ai_response",
        "ai_errors",
        "mto_items",
        "boq_items",
        "cost_summary",
        "used_ai",
        "drawing_uploader",  # clears the file_uploader widget itself
    ]
    for k in keys_to_clear:
        if k in st.session_state:
            del st.session_state[k]
    st.session_state["project_inputs"] = ProjectInputs()
    st.session_state["wastage_factors"] = WastageFactors()
    st.session_state["rate_book"] = {r.item_code: r for r in load_default_rates()}
    st.session_state["step"] = 1


def go_to_step(n: int):
    st.session_state["step"] = n
