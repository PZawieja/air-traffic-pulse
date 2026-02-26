"""Generate placeholder screenshot images for the README.

Run from the repo root:
    python tools/generate_placeholders.py

Requires Pillow (installed as a dev dependency):
    pip install pillow
"""

from __future__ import annotations

import pathlib

from PIL import Image, ImageDraw, ImageFont

DOCS_DIR = pathlib.Path(__file__).parent.parent / "docs"
DOCS_DIR.mkdir(exist_ok=True)

# ── Colour palette ────────────────────────────────────────────────────────────
BG_DARK = (15, 17, 22)
BG_CARD = (30, 33, 40)
ACCENT = (255, 75, 75)
ACCENT2 = (0, 180, 216)
TEXT_PRIMARY = (255, 255, 255)
TEXT_SECONDARY = (160, 165, 175)
GRID = (45, 50, 60)

W, H = 1200, 720


def _base_canvas(title: str) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), BG_DARK)
    draw = ImageDraw.Draw(img)

    # Top bar
    draw.rectangle([(0, 0), (W, 52)], fill=BG_CARD)
    draw.line([(0, 52), (W, 52)], fill=GRID, width=1)

    # Page icon + title in header
    try:
        font_lg = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 22)
        font_sm = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 12)
    except OSError:
        font_lg = font_sm = ImageFont.load_default()

    draw.text((20, 14), "✈  Air Traffic Pulse", fill=TEXT_PRIMARY, font=font_lg)
    draw.text(
        (W - 260, 17), "OpenSky → DuckDB → dbt → Streamlit", fill=TEXT_SECONDARY, font=font_sm
    )

    # Section title
    draw.text((20, 72), title, fill=TEXT_PRIMARY, font=font_lg)
    draw.line([(20, 98), (W - 20, 98)], fill=GRID, width=1)

    return img, draw


def _draw_metric_card(
    draw: ImageDraw.ImageDraw, x: int, y: int, label: str, value: str, delta: str = ""
) -> None:
    cw, ch = 260, 100
    draw.rounded_rectangle([(x, y), (x + cw, y + ch)], radius=8, fill=BG_CARD)
    try:
        font_val = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 28)
        font_lbl = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 12)
    except OSError:
        font_val = font_lbl = ImageFont.load_default()
    draw.text((x + 14, y + 12), label, fill=TEXT_SECONDARY, font=font_lbl)
    draw.text((x + 14, y + 36), value, fill=TEXT_PRIMARY, font=font_val)
    if delta:
        draw.text((x + 14, y + 74), delta, fill=ACCENT2, font=font_lbl)


def generate_overview() -> None:
    img, draw = _base_canvas("Latest snapshot by bounding box")

    try:
        font_sm = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 12)
    except OSError:
        font_sm = ImageFont.load_default()

    # ── Metric cards ──────────────────────────────────────────────────────
    _draw_metric_card(draw, 20, 110, "Last run status", "✅  SUCCESS", "2.8s · 55 rows")
    _draw_metric_card(draw, 300, 110, "Records loaded", "55", "+55 this run")
    _draw_metric_card(draw, 580, 110, "Ingestion runs", "3", "")
    _draw_metric_card(draw, 860, 110, "Bboxes active", "3", "berlin · frankfurt · london")

    # ── Snapshot table ────────────────────────────────────────────────────
    draw.text((20, 230), "Latest snapshot per bbox", fill=TEXT_SECONDARY, font=font_sm)

    headers = [
        "Bbox",
        "Snapshot time (UTC)",
        "Aircraft",
        "With position",
        "On ground",
        "Avg speed (m/s)",
    ]
    col_x = [20, 120, 360, 470, 590, 700]
    row_h = 36
    table_top = 255

    # Header row
    draw.rectangle([(18, table_top), (W - 20, table_top + row_h)], fill=BG_CARD)
    for hx, hdr in zip(col_x, headers, strict=False):
        draw.text((hx + 6, table_top + 10), hdr, fill=TEXT_SECONDARY, font=font_sm)

    # Data rows
    rows = [
        ("berlin", "2026-02-26 15:48 UTC", "7", "6", "1", "218.4"),
        ("frankfurt", "2026-02-26 15:48 UTC", "17", "15", "2", "231.7"),
        ("london", "2026-02-26 15:48 UTC", "31", "28", "4", "244.1"),
    ]
    for ri, row in enumerate(rows):
        y = table_top + row_h * (ri + 1)
        fill = BG_DARK if ri % 2 == 0 else BG_CARD
        draw.rectangle([(18, y), (W - 20, y + row_h)], fill=fill)
        color = ACCENT2 if ri == 0 else TEXT_PRIMARY
        for cx, val in zip(col_x, row, strict=False):
            draw.text((cx + 6, y + 10), val, fill=color, font=font_sm)

    # ── Footer note ───────────────────────────────────────────────────────
    draw.text(
        (20, H - 30),
        "Run  make ingest  to refresh  ·  make dbt  to rebuild models",
        fill=TEXT_SECONDARY,
        font=font_sm,
    )

    out = DOCS_DIR / "screenshot_overview.png"
    img.save(out, "PNG")
    print(f"Saved {out}")


def generate_timeseries() -> None:
    img, draw = _base_canvas("Traffic timeseries — 5-minute buckets")

    try:
        font_sm = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 12)
    except OSError:
        font_sm = ImageFont.load_default()

    # ── Bbox selector ─────────────────────────────────────────────────────
    draw.text((20, 112), "Select bounding box", fill=TEXT_SECONDARY, font=font_sm)
    draw.rounded_rectangle([(20, 130), (200, 158)], radius=6, fill=BG_CARD)
    draw.text((30, 138), "london  ▾", fill=TEXT_PRIMARY, font=font_sm)

    # ── Chart area ────────────────────────────────────────────────────────
    cx0, cy0, cx1, cy1 = 20, 175, W - 20, H - 60

    # Grid lines
    for i in range(5):
        gy = cy0 + (cy1 - cy0) * i // 4
        draw.line([(cx0, gy), (cx1, gy)], fill=GRID, width=1)

    # Simulated time-series data points (aircraft_count and positioned_count)
    import math

    n_points = 24
    points_total: list[tuple[int, int]] = []
    points_pos: list[tuple[int, int]] = []
    for i in range(n_points):
        px = cx0 + (cx1 - cx0) * i // (n_points - 1)
        # Simulated realistic values
        val_total = 28 + int(8 * math.sin(i * 0.5)) + (i % 3)
        val_pos = val_total - 2 - (i % 2)
        py_total = cy1 - int((val_total / 42) * (cy1 - cy0))
        py_pos = cy1 - int((val_pos / 42) * (cy1 - cy0))
        points_total.append((px, py_total))
        points_pos.append((px, py_pos))

    # Fill area under total line
    poly = [(cx0, cy1), *points_total, (cx1, cy1)]
    draw.polygon(poly, fill=(255, 75, 75, 40))

    # Draw lines
    for i in range(len(points_total) - 1):
        draw.line([points_total[i], points_total[i + 1]], fill=ACCENT, width=2)
        draw.line([points_pos[i], points_pos[i + 1]], fill=ACCENT2, width=2)

    # X-axis labels (every 4 buckets = 20 min)
    times = ["15:00", "15:20", "15:40", "16:00", "16:20", "16:40"]
    for j, label in enumerate(times):
        lx = cx0 + (cx1 - cx0) * j * 4 // (n_points - 1)
        draw.text((lx - 14, cy1 + 8), label, fill=TEXT_SECONDARY, font=font_sm)

    # Y-axis labels
    for k in range(5):
        lv = int(42 * (4 - k) / 4)
        ly = cy0 + (cy1 - cy0) * k // 4
        draw.text((cx0 - 8, ly - 6), str(lv), fill=TEXT_SECONDARY, font=font_sm)

    # Legend
    draw.line([(W - 300, 140), (W - 270, 140)], fill=ACCENT, width=2)
    draw.text((W - 265, 133), "Total aircraft", fill=TEXT_PRIMARY, font=font_sm)
    draw.line([(W - 300, 158), (W - 270, 158)], fill=ACCENT2, width=2)
    draw.text((W - 265, 151), "With position fix", fill=TEXT_PRIMARY, font=font_sm)

    # Caption
    draw.text(
        (cx0, H - 30),
        "Each point = distinct aircraft in a 5-minute window over london",
        fill=TEXT_SECONDARY,
        font=font_sm,
    )

    out = DOCS_DIR / "screenshot_timeseries.png"
    img.save(out, "PNG")
    print(f"Saved {out}")


if __name__ == "__main__":
    generate_overview()
    generate_timeseries()
    print("Done.")
