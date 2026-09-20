"""
CostLens visual theme: CSS injection + small branded UI helpers layered on
top of the native Streamlit theme (.streamlit/config.toml). Kept in its own
module so app.py stays focused on app flow, not styling.

Everything here is additive and defensive:
- Selectors target stable `data-testid` attributes, not Streamlit's
  auto-generated/versioned class names, so a Streamlit upgrade that
  changes internal class names won't break this.
- If a selector ever stops matching in some version, the app just falls
  back to plain Streamlit styling - nothing here is load-bearing for
  functionality, only for visual polish.
- No JS, no external component libraries - pure CSS injected via
  st.markdown(unsafe_allow_html=True), which is the one supported
  "custom styling" escape hatch within Streamlit's platform limits.
"""
from __future__ import annotations

import base64

import streamlit as st

import config

_CSS = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Outfit:wght@400;500;600;700;800&display=swap');

html, body, [class*="css"] {{
    font-family: 'Outfit', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}}

/* ---------------------------------------------------------------- *
 * App background
 * ---------------------------------------------------------------- */
[data-testid="stAppViewContainer"] > .main {{
    background: linear-gradient(180deg, {config.BRAND_BG} 0%, #FFFFFF 360px);
}}

/* ---------------------------------------------------------------- *
 * Hero header banner (top of every step)
 * ---------------------------------------------------------------- */
.cl-hero {{
    display: flex;
    align-items: center;
    gap: 18px;
    padding: 18px 26px;
    margin: -1rem -1rem 1.5rem -1rem;
    background: linear-gradient(120deg, {config.BRAND_NAVY} 0%, {config.BRAND_NAVY_LIGHT} 100%);
    border-radius: 0 0 18px 18px;
    box-shadow: 0 6px 24px rgba(11, 30, 61, 0.18);
}}
.cl-hero img {{ height: 46px; display: block; }}
.cl-hero-text h1 {{
    color: #FFFFFF !important;
    font-size: 1.5rem !important;
    font-weight: 800 !important;
    margin: 0 !important;
    letter-spacing: -0.01em;
}}
.cl-hero-text p {{
    color: {config.BRAND_TEAL_BRIGHT} !important;
    font-size: 0.8rem !important;
    letter-spacing: 0.13em;
    text-transform: uppercase;
    margin: 2px 0 0 0 !important;
    font-weight: 600;
}}

/* ---------------------------------------------------------------- *
 * Headings
 * ---------------------------------------------------------------- */
h1, h2, h3 {{ color: {config.BRAND_NAVY}; font-weight: 700; }}

/* ---------------------------------------------------------------- *
 * Buttons
 * ---------------------------------------------------------------- */
.stButton > button,
.stDownloadButton > button,
[data-testid="stFormSubmitButton"] button {{
    border-radius: 10px;
    font-weight: 600;
    border: 1px solid rgba(11, 30, 61, 0.12);
    transition: transform 0.06s ease-in-out, box-shadow 0.15s ease-in-out;
}}
.stButton > button:hover,
.stDownloadButton > button:hover,
[data-testid="stFormSubmitButton"] button:hover {{
    transform: translateY(-1px);
    box-shadow: 0 4px 14px rgba(13, 148, 136, 0.25);
    border-color: {config.BRAND_TEAL};
}}
.stButton > button[kind="primary"],
[data-testid="stFormSubmitButton"] button[kind="primary"] {{
    background: linear-gradient(120deg, {config.BRAND_TEAL} 0%, #0F766E 100%);
    border: none;
}}

/* ---------------------------------------------------------------- *
 * Metric cards (Step 5: Subtotal / Contingency / Grand Total)
 * ---------------------------------------------------------------- */
[data-testid="stMetric"] {{
    background: #FFFFFF;
    border: 1px solid rgba(11, 30, 61, 0.08);
    border-left: 4px solid {config.BRAND_TEAL};
    border-radius: 12px;
    padding: 14px 18px;
    box-shadow: 0 2px 10px rgba(11, 30, 61, 0.05);
}}
[data-testid="stMetricLabel"] {{ color: {config.BRAND_NAVY}; font-weight: 600; }}
[data-testid="stMetricValue"] {{ color: {config.BRAND_NAVY}; }}

/* ---------------------------------------------------------------- *
 * Expanders (Steps 3 / 4 / 5 rely on these heavily)
 * ---------------------------------------------------------------- */
[data-testid="stExpander"] {{
    border: 1px solid rgba(11, 30, 61, 0.08);
    border-radius: 12px;
    box-shadow: 0 1px 6px rgba(11, 30, 61, 0.04);
}}

/* ---------------------------------------------------------------- *
 * Sidebar logo (st.logo) - Streamlit renders this quite small by
 * default (~24-32px tall) regardless of the source image's actual
 * resolution. Force it larger here so it reads clearly; `size="large"`
 * is passed in app.py too for versions that support that parameter,
 * but this CSS is what actually guarantees the size across versions.
 * ---------------------------------------------------------------- */
[data-testid="stSidebarHeader"] {{
    padding-top: 1rem !important;
    padding-bottom: 0.75rem !important;
    align-items: center !important;
}}
[data-testid="stSidebarHeader"] img,
[data-testid="stLogo"],
[data-testid="stLogo"] img,
.stLogo,
.stLogo img {{
    height: 3.2rem !important;
    max-height: none !important;
    width: auto !important;
}}

/* ---------------------------------------------------------------- *
 * Sidebar
 * ---------------------------------------------------------------- */
[data-testid="stSidebar"] {{
    background: linear-gradient(180deg, {config.BRAND_NAVY} 0%, {config.BRAND_NAVY_LIGHT} 100%);
}}
[data-testid="stSidebar"] * {{ color: #E8EEF5 !important; }}
[data-testid="stSidebar"] hr {{ border-color: rgba(255, 255, 255, 0.15); }}
[data-testid="stSidebar"] .stButton > button {{
    background: rgba(255, 255, 255, 0.06);
    border: 1px solid rgba(255, 255, 255, 0.18);
    color: #FFFFFF !important;
}}
[data-testid="stSidebar"] .stButton > button:hover {{
    background: {config.BRAND_TEAL};
    border-color: {config.BRAND_TEAL};
}}

/* ---------------------------------------------------------------- *
 * Sidebar step tracker (replaces the plain emoji checklist)
 * ---------------------------------------------------------------- */
.cl-step {{
    display: flex;
    align-items: center;
    gap: 10px;
    padding: 7px 10px;
    border-radius: 8px;
    margin-bottom: 4px;
    font-size: 0.88rem;
}}
.cl-step-done {{ opacity: 0.6; }}
.cl-step-current {{
    background: rgba(45, 212, 191, 0.16);
    border: 1px solid rgba(45, 212, 191, 0.4);
    font-weight: 700 !important;
}}
.cl-step-upcoming {{ opacity: 0.4; }}
.cl-step-dot {{
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 20px;
    height: 20px;
    border-radius: 50%;
    font-size: 0.72rem;
    font-weight: 700;
    flex-shrink: 0;
}}
.cl-step-done .cl-step-dot {{ background: {config.BRAND_TEAL}; color: #FFFFFF; }}
.cl-step-current .cl-step-dot {{ background: {config.BRAND_GOLD}; color: {config.BRAND_NAVY}; }}
.cl-step-upcoming .cl-step-dot {{ background: rgba(255, 255, 255, 0.15); color: #E8EEF5; }}
</style>
"""


def inject_theme() -> None:
    """Injects the CostLens CSS. Safe to call on every rerun - it's purely
    additive and idempotent (re-injecting the same <style> block has no
    side effects)."""
    st.markdown(_CSS, unsafe_allow_html=True)


def render_hero() -> None:
    """Branded header banner (logo + wordmark + tagline) shown above every
    step's content. Degrades to a text-only banner if the logo PNG is
    missing (e.g. assets/generate_logo.py hasn't been run in a fork)."""
    logo_html = ""
    try:
        with open(config.LOGO_ICON_PATH, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode("ascii")
        logo_html = f'<img src="data:image/png;base64,{b64}" alt="{config.APP_NAME} logo" />'
    except OSError:
        pass

    st.markdown(
        f"""
        <div class="cl-hero">
            {logo_html}
            <div class="cl-hero-text">
                <h1>{config.APP_NAME}</h1>
                <p>{config.APP_TAGLINE}</p>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_sidebar_steps(step_labels: list[str], current_step: int) -> None:
    """Branded HTML/CSS step tracker for the sidebar. Read-only by design -
    the wizard advances via its own Continue/Back buttons, not by clicking
    a step here."""
    rows = []
    for i, label in enumerate(step_labels, start=1):
        if current_step > i:
            state, dot = "cl-step-done", "✓"
        elif current_step == i:
            state, dot = "cl-step-current", str(i)
        else:
            state, dot = "cl-step-upcoming", str(i)
        rows.append(f'<div class="cl-step {state}"><span class="cl-step-dot">{dot}</span><span>{label}</span></div>')
    st.markdown("\n".join(rows), unsafe_allow_html=True)
