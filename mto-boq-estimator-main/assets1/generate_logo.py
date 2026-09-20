"""
Generates the CostLens brand assets (icon + horizontal lockup) as PNGs.

Not imported by the running app - app.py just loads the resulting PNG
files from this folder. Kept here so the logo can be regenerated/tweaked
later without needing an external design tool. Everything is drawn with
Pillow at a supersampled resolution and downsampled with LANCZOS for
smooth, anti-aliased edges - no external rasterizer/SVG library needed.

Fonts: Outfit (Bold/Regular), OFL-licensed, bundled with this repo's
canvas-design assets - see assets/fonts/OFL.txt.

Run:  python assets/generate_logo.py
"""
from __future__ import annotations

import math
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONT_DIR = os.path.join(HERE, "fonts")

# Brand palette
NAVY_DARK = (11, 30, 61)        # #0B1E3D
NAVY_LIGHT = (18, 58, 90)       # #123A5A
TEAL = (45, 212, 191)           # #2DD4BF
TEAL_LIGHT = (153, 246, 228)    # #99F6E4 (glass highlight)
GOLD = (251, 191, 36)           # #FBBF24
GOLD_DARK = (180, 120, 8)       # shadow under coin
WHITE = (255, 255, 255)
INK = NAVY_DARK


def _font(name: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(os.path.join(FONT_DIR, name), size)


def _rounded_gradient_bg(size: int, c1, c2) -> Image.Image:
    """Diagonal (top-left -> bottom-right) gradient, then masked into a
    rounded-rect / squircle-ish shape."""
    base = Image.new("RGB", (size, size), c1)
    top = Image.new("RGB", (size, size), c2)
    mask = Image.new("L", (size, size))
    mpix = mask.load()
    for y in range(size):
        for x in range(size):
            mpix[x, y] = int(255 * ((x + y) / (2 * size)))
    grad = Image.composite(top, base, mask)

    rounded_mask = Image.new("L", (size, size), 0)
    d = ImageDraw.Draw(rounded_mask)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=int(size * 0.22), fill=255)

    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(grad, (0, 0), rounded_mask)
    return out


def draw_icon(final_size: int = 512, supersample: int = 3) -> Image.Image:
    S = final_size * supersample
    canvas = _rounded_gradient_bg(S, NAVY_DARK, NAVY_LIGHT)
    d = ImageDraw.Draw(canvas)

    cx, cy = S * 0.42, S * 0.42
    lens_r = S * 0.24
    stroke = max(2, int(S * 0.035))

    # --- magnifying-glass handle (drawn first, so the lens sits on top) ---
    hx1 = cx + lens_r * math.cos(math.radians(45))
    hy1 = cy + lens_r * math.sin(math.radians(45))
    hx2, hy2 = S * 0.86, S * 0.86
    d.line([hx1, hy1, hx2, hy2], fill=TEAL, width=int(stroke * 1.3))
    d.ellipse([hx2 - stroke * 0.65, hy2 - stroke * 0.65, hx2 + stroke * 0.65, hy2 + stroke * 0.65], fill=TEAL)

    # --- lens glass (soft navy fill so the house icon reads clearly) ---
    d.ellipse([cx - lens_r, cy - lens_r, cx + lens_r, cy + lens_r], fill=NAVY_LIGHT, outline=TEAL, width=stroke)

    # subtle glass highlight arc (top-left)
    hl_bbox = [cx - lens_r * 0.72, cy - lens_r * 0.72, cx + lens_r * 0.15, cy + lens_r * 0.15]
    d.arc(hl_bbox, start=200, end=300, fill=TEAL_LIGHT, width=max(1, int(stroke * 0.4)))

    # --- simple bold house glyph inside the lens (reads well even tiny) ---
    house_w = lens_r * 0.95
    house_h = lens_r * 0.62
    bx0, by0 = cx - house_w / 2, cy - house_h * 0.15
    bx1, by1 = cx + house_w / 2, cy + house_h * 0.62
    d.rectangle([bx0, by0, bx1, by1], fill=WHITE)
    roof = [(cx - house_w * 0.62, by0), (cx, cy - house_h * 0.85), (cx + house_w * 0.62, by0)]
    d.polygon(roof, fill=WHITE)
    door_w, door_h = house_w * 0.22, house_h * 0.42
    d.rectangle([cx - door_w / 2, by1 - door_h, cx + door_w / 2, by1], fill=NAVY_LIGHT)

    # --- gold "value" coin badge, bottom-right of the lens ---
    coin_r = lens_r * 0.52
    coin_cx, coin_cy = cx + lens_r * 0.78, cy + lens_r * 0.78
    d.ellipse(
        [coin_cx - coin_r - stroke * 0.5, coin_cy - coin_r - stroke * 0.5, coin_cx + coin_r + stroke * 0.5, coin_cy + coin_r + stroke * 0.5],
        fill=NAVY_DARK,
    )
    d.ellipse([coin_cx - coin_r, coin_cy - coin_r, coin_cx + coin_r, coin_cy + coin_r], fill=GOLD, outline=GOLD_DARK, width=max(1, int(stroke * 0.35)))

    # three ascending bars = "value/growth"
    bar_w = coin_r * 0.34
    gap = coin_r * 0.18
    heights = [coin_r * 0.55, coin_r * 0.9, coin_r * 1.25]
    total_w = bar_w * 3 + gap * 2
    start_x = coin_cx - total_w / 2
    base_y = coin_cy + coin_r * 0.62
    for i, h in enumerate(heights):
        x0 = start_x + i * (bar_w + gap)
        d.rectangle([x0, base_y - h, x0 + bar_w, base_y], fill=NAVY_DARK)

    return canvas.resize((final_size, final_size), Image.LANCZOS)


def draw_horizontal_lockup(
    icon: Image.Image,
    final_w: int = 1200,
    final_h: int = 320,
    supersample: int = 2,
    wordmark_color=INK,
    tagline_color=(45, 90, 110),
) -> Image.Image:
    """Icon + "CostLens" wordmark + tagline, on a transparent background.

    `wordmark_color`/`tagline_color` default to dark navy/muted teal, which
    reads well on a LIGHT background. Pass light colors (see
    `draw_horizontal_lockup_on_dark`) for use on a dark background (e.g.
    the app's navy sidebar) - a transparent PNG only controls its own
    pixels, not what's behind it, so the same file can't work on both."""
    W, H = final_w * supersample, final_h * supersample
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 0))

    icon_big = icon.resize((H, H), Image.LANCZOS)
    canvas.paste(icon_big, (0, 0), icon_big)

    d = ImageDraw.Draw(canvas)
    text_x = int(H * 1.18)

    wordmark_font = _font("Outfit-Bold.ttf", int(H * 0.46))
    tagline_font = _font("Outfit-Regular.ttf", int(H * 0.145))

    wm_y = int(H * 0.14)
    d.text((text_x, wm_y), "CostLens", font=wordmark_font, fill=wordmark_color)

    tagline = "FROM  PLANS  TO  PRICE"
    tag_y = int(H * 0.70)
    d.text((text_x, tag_y), tagline, font=tagline_font, fill=tagline_color)

    # trim transparent right margin (alpha-based, so text color doesn't
    # affect this - the whole point is to see through in either theme)
    bbox = canvas.getbbox()
    if bbox:
        canvas = canvas.crop((0, 0, min(W, bbox[2] + int(H * 0.12)), H))

    out_w = int(canvas.width / supersample)
    out_h = int(canvas.height / supersample)
    return canvas.resize((out_w, out_h), Image.LANCZOS)


def draw_horizontal_lockup_on_dark(icon: Image.Image, **kwargs) -> Image.Image:
    """Same lockup, recolored for use on a dark/navy background (e.g.
    st.logo() in the app's navy sidebar) - white wordmark, bright-teal
    tagline instead of navy-on-navy (which would be invisible)."""
    return draw_horizontal_lockup(icon, wordmark_color=WHITE, tagline_color=TEAL_LIGHT, **kwargs)


if __name__ == "__main__":
    icon = draw_icon()
    icon.save(os.path.join(HERE, "costlens_icon.png"))

    lockup = draw_horizontal_lockup(icon)
    lockup.save(os.path.join(HERE, "costlens_logo.png"))

    lockup_dark = draw_horizontal_lockup_on_dark(icon)
    lockup_dark.save(os.path.join(HERE, "costlens_logo_on_dark.png"))

    print("Wrote costlens_icon.png", icon.size)
    print("Wrote costlens_logo.png", lockup.size)
    print("Wrote costlens_logo_on_dark.png", lockup_dark.size)
