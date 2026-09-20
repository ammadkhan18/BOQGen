"""
Reusable Streamlit widgets shared across app.py steps.
"""
from __future__ import annotations

import math
from typing import Dict, Optional

import pandas as pd
import streamlit as st

from models.schemas import ConfidenceLevel, Estimate, MaterialRate, Source, WastageFactors
from utils import units

CONFIDENCE_COLORS = {
    ConfidenceLevel.HIGH: "#1a7f37",
    ConfidenceLevel.MEDIUM: "#9a6700",
    ConfidenceLevel.LOW: "#c0392b",
}
CONFIDENCE_BG = {
    ConfidenceLevel.HIGH: "#dafbe1",
    ConfidenceLevel.MEDIUM: "#fff8c5",
    ConfidenceLevel.LOW: "#ffebe9",
}


def confidence_badge(confidence: ConfidenceLevel) -> str:
    color = CONFIDENCE_COLORS.get(confidence, "#555")
    bg = CONFIDENCE_BG.get(confidence, "#eee")
    return (
        f'<span style="background-color:{bg};color:{color};padding:2px 8px;'
        f'border-radius:10px;font-size:0.75rem;font-weight:600;">{confidence.value}</span>'
    )


def render_estimate_input(
    label: str,
    estimate: Estimate,
    key: str,
    unit: str = "",
    step: float = 0.01,
    min_value: float = 0.0,
    help_text: str | None = None,
    unit_system: str = units.SI,
    quantity_kind: Optional[str] = None,
) -> Estimate:
    """Render one editable numeric field with its confidence badge + note,
    and return a (possibly updated) Estimate reflecting the user's edit.

    `estimate.value` is ALWAYS canonical SI (metres / sqm) - this is the
    single source of truth consumed by engineering/calculations.py.
    `quantity_kind` ("length" | "thickness" | "area" | None) tells this
    widget how to convert that SI value to/from the user's chosen
    `unit_system` for display only; pass None (the default) for
    unit-less fields such as counts, where `unit` is shown verbatim
    (e.g. "nos", "floors").
    """
    if quantity_kind is not None:
        display_value = units.to_display(estimate.value, quantity_kind, unit_system)
        display_step = units.to_display(step, quantity_kind, unit_system) or step
        display_min = units.to_display(min_value, quantity_kind, unit_system)
        display_unit = units.dimension_unit_label(quantity_kind, unit_system)
    else:
        display_value = estimate.value
        display_step = step
        display_min = min_value
        display_unit = unit

    col1, col2 = st.columns([3, 1])
    with col1:
        new_display_value = st.number_input(
            f"{label} ({display_unit})" if display_unit else label,
            value=float(display_value),
            step=float(display_step),
            min_value=float(display_min),
            key=key,
            help=help_text or estimate.note,
        )
    with col2:
        st.markdown("<div style='margin-top:1.8rem'></div>" + confidence_badge(estimate.confidence), unsafe_allow_html=True)

    if estimate.note:
        st.caption(f"\u2139\ufe0f {estimate.note}")

    new_value = units.to_si(new_display_value, quantity_kind, unit_system) if quantity_kind is not None else new_display_value

    # Use a tolerant comparison (not `!=`) because round-tripping through a
    # display unit conversion (e.g. metres -> feet -> metres) can leave a
    # sub-nanometre floating-point residue on an otherwise-unchanged field;
    # an exact-equality check would wrongly flag every FPS field as
    # "user-edited" on every rerun.
    if not math.isclose(new_value, estimate.value, rel_tol=1e-9, abs_tol=1e-9):
        return estimate.with_value(new_value)
    return estimate


def render_wastage_editor(wastage: WastageFactors) -> WastageFactors:
    st.caption("Adjust wastage/allowance percentages applied when converting MTO quantities into BOQ order quantities.")
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        concrete_pct = st.slider("Concrete wastage %", 0.0, 15.0, wastage.concrete_pct, 0.5)
        steel_pct = st.slider("Steel wastage %", 0.0, 15.0, wastage.steel_pct, 0.5)
    with c2:
        brick_block_pct = st.slider("Brick/block wastage %", 0.0, 15.0, wastage.brick_block_pct, 0.5)
        plaster_pct = st.slider("Plaster wastage %", 0.0, 20.0, wastage.plaster_pct, 0.5)
    with c3:
        formwork_pct = st.slider("Formwork wastage %", 0.0, 15.0, wastage.formwork_pct, 0.5)
        flooring_pct = st.slider("Flooring wastage %", 0.0, 15.0, wastage.flooring_pct, 0.5)
    with c4:
        paint_pct = st.slider("Paint wastage %", 0.0, 15.0, wastage.paint_pct, 0.5)
        misc_pct = st.slider("Misc/other wastage %", 0.0, 15.0, wastage.misc_pct, 0.5)

    return WastageFactors(
        concrete_pct=concrete_pct,
        steel_pct=steel_pct,
        brick_block_pct=brick_block_pct,
        plaster_pct=plaster_pct,
        formwork_pct=formwork_pct,
        flooring_pct=flooring_pct,
        paint_pct=paint_pct,
        misc_pct=misc_pct,
    )


def render_rate_editor(
    rate_book: Dict[str, MaterialRate],
    unit_system: str = units.SI,
    currency_symbol: str = "",
) -> Dict[str, MaterialRate]:
    """Rates are always stored canonically per SI unit (PKR/m3, PKR/m2,
    PKR/kg, ...) - exactly what generate_boq() expects. When FPS is
    selected, this editor only *displays* and *accepts* the equivalent
    rate per cft/sqft, converting silently in both directions, so the
    stored MaterialRate never changes meaning regardless of which unit
    system the user is looking at.
    """
    if units.is_fps(unit_system):
        st.caption(
            "Edit unit rates below (shown per cft / sqft - Pakistani FPS practice) to match your local market "
            "before generating the final BOQ cost. Rates are still stored/calculated per metric unit internally, "
            "so switching unit systems never changes the total cost."
        )
    else:
        st.caption("Edit unit rates below to match your local market before generating the final BOQ cost.")

    rate_col_label = f"Rate ({currency_symbol.strip()})" if currency_symbol else "Rate"
    df = pd.DataFrame(
        [
            {
                "Item Code": r.item_code,
                "Description": r.description,
                "Unit": units.display_unit(r.unit, unit_system),
                "Category": r.category,
                rate_col_label: round(units.display_rate(r.rate, r.unit, unit_system), 4),
            }
            for r in rate_book.values()
        ]
    )
    edited = st.data_editor(
        df,
        key="rate_editor",
        num_rows="fixed",
        use_container_width=True,
        hide_index=True,
        column_config={
            "Item Code": st.column_config.TextColumn(disabled=True),
            "Description": st.column_config.TextColumn(disabled=True),
            "Unit": st.column_config.TextColumn(disabled=True),
            "Category": st.column_config.TextColumn(disabled=True),
            rate_col_label: st.column_config.NumberColumn(min_value=0.0, step=0.01, format="%.2f"),
        },
    )
    updated: Dict[str, MaterialRate] = {}
    for _, row in edited.iterrows():
        code = row["Item Code"]
        original = rate_book[code]
        si_rate = units.rate_to_si(float(row[rate_col_label]), original.unit, unit_system)
        updated[code] = MaterialRate(
            item_code=code,
            description=original.description,
            unit=original.unit,
            category=original.category,
            rate=si_rate,
        )
    return updated
