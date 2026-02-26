"""Generate representative screenshot images for the README.

Produces two PNG files in docs/ that closely mirror the current Streamlit
dashboard — pipeline status, the insights table with z-scores and anomaly
badges, and a timeseries chart with an injected spike event.

Run from the repo root:
    python tools/generate_placeholders.py

Requires Pillow (installed as a dev dependency).
"""

from __future__ import annotations

import math
import pathlib

from PIL import Image, ImageDraw, ImageFont

DOCS_DIR = pathlib.Path(__file__).parent.parent / "docs"
DOCS_DIR.mkdir(exist_ok=True)

# ── Colour palette (matches Streamlit dark theme) ─────────────────────────────
BG_DARK = (15, 17, 22)
BG_CARD = (30, 33, 40)
BG_CARD2 = (38, 42, 52)
ACCENT_RED = (255, 75, 75)
ACCENT_BLUE = (41, 182, 246)
ACCENT_YELL = (251, 191, 36)
GREEN = (74, 222, 128)
TEXT_PRI = (255, 255, 255)
TEXT_SEC = (148, 163, 184)
GRID = (45, 50, 60)
BORDER = (55, 60, 72)

W, H = 1280, 760


# ── Font helpers ──────────────────────────────────────────────────────────────


def _fonts() -> dict[str, ImageFont.FreeTypeFont | ImageFont.ImageFont]:
    candidates = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/System/Library/Fonts/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        try:
            return {
                "xl": ImageFont.truetype(path, 24),
                "lg": ImageFont.truetype(path, 18),
                "md": ImageFont.truetype(path, 14),
                "sm": ImageFont.truetype(path, 12),
                "xs": ImageFont.truetype(path, 10),
            }
        except OSError:
            continue
    default = ImageFont.load_default()
    return {"xl": default, "lg": default, "md": default, "sm": default, "xs": default}


F = _fonts()


# ── Shared canvas ─────────────────────────────────────────────────────────────


def _base_canvas() -> tuple[Image.Image, ImageDraw.ImageDraw]:
    img = Image.new("RGB", (W, H), BG_DARK)
    draw = ImageDraw.Draw(img)

    # Top bar
    draw.rectangle([(0, 0), (W, 56)], fill=BG_CARD)
    draw.line([(0, 56), (W, 56)], fill=BORDER, width=1)
    draw.text((18, 16), "✈  Air Traffic Pulse", fill=TEXT_PRI, font=F["xl"])
    draw.text(
        (W - 440, 19),
        "OpenSky → DuckDB → dbt → Streamlit  ·  🧪 Demo mode",
        fill=TEXT_SEC,
        font=F["sm"],
    )
    return img, draw


def _divider(draw: ImageDraw.ImageDraw, y: int) -> None:
    draw.line([(16, y), (W - 16, y)], fill=BORDER, width=1)


def _section_header(draw: ImageDraw.ImageDraw, y: int, title: str) -> None:
    draw.text((16, y), title, fill=TEXT_PRI, font=F["lg"])


def _metric_card(
    draw: ImageDraw.ImageDraw, x: int, y: int, label: str, value: str, sub: str = ""
) -> None:
    draw.rounded_rectangle([(x, y), (x + 278, y + 90)], radius=6, fill=BG_CARD)
    draw.text((x + 12, y + 10), label, fill=TEXT_SEC, font=F["xs"])
    draw.text((x + 12, y + 30), value, fill=TEXT_PRI, font=F["lg"])
    if sub:
        draw.text((x + 12, y + 64), sub, fill=ACCENT_BLUE, font=F["xs"])


def _table_row(
    draw: ImageDraw.ImageDraw,
    y: int,
    cells: list[str],
    col_x: list[int],
    fill: tuple,
    text_color: tuple = TEXT_PRI,
) -> None:
    draw.rectangle([(16, y), (W - 16, y + 28)], fill=fill)
    for cx, val in zip(col_x, cells, strict=False):
        draw.text((cx + 6, y + 8), val, fill=text_color, font=F["sm"])


# ── Screenshot 1: Overview + Insights ────────────────────────────────────────


def generate_overview() -> None:
    img, draw = _base_canvas()

    y = 68

    # ── Pipeline status ───────────────────────────────────────────────────────
    _section_header(draw, y, "🔄  Pipeline status")
    y += 30
    _metric_card(draw, 16, y, "Last run result", "✅  Success")
    _metric_card(draw, 306, y, "Aircraft states collected", "36,145", "+576 latest run")
    _metric_card(draw, 596, y, "Run duration", "1.4 s")
    _metric_card(draw, 886, y, "Started at (UTC)", "2026-02-26 20:00")

    y += 108
    _divider(draw, y)
    y += 14

    # ── Latest snapshot ───────────────────────────────────────────────────────
    _section_header(draw, y, "📍  Latest snapshot by region")
    y += 30

    snap_hdrs = [
        "Region",
        "Captured at (UTC)",
        "Aircraft detected",
        "GPS-positioned",
        "On ground",
        "Avg ground speed (m/s)",
    ]
    snap_col_x = [16, 186, 406, 566, 716, 866]

    _table_row(draw, y, snap_hdrs, snap_col_x, BG_CARD2, TEXT_SEC)
    y += 28

    snap_rows = [
        ("🇩🇪 Berlin", "2026-02-26 20:00 UTC", "14", "12", "1", "224.3"),
        ("🇩🇪 Frankfurt", "2026-02-26 20:00 UTC", "15", "13", "2", "238.7"),
        ("🇬🇧 London", "2026-02-26 20:00 UTC", "22", "20", "3", "241.9"),
        ("🇵🇱 Warsaw", "2026-02-26 20:00 UTC", "14", "12", "1", "219.6"),
    ]
    for i, row in enumerate(snap_rows):
        _table_row(draw, y, list(row), snap_col_x, BG_DARK if i % 2 == 0 else BG_CARD)
        y += 28

    y += 10
    _divider(draw, y)
    y += 14

    # ── Traffic insights ──────────────────────────────────────────────────────
    _section_header(draw, y, "🧠  Traffic insights  (28-day z-score baseline)")
    y += 30

    ins_hdrs = ["Region", "Status", "Aircraft now", "Baseline avg", "σ", "Z-score", "1h trend"]
    ins_col_x = [16, 196, 346, 476, 586, 676, 806]

    _table_row(draw, y, ins_hdrs, ins_col_x, BG_CARD2, TEXT_SEC)
    y += 28

    ins_rows: list[tuple[str, str, tuple, ...]] = [
        ("🇩🇪 Berlin", "✅ Normal", TEXT_PRI, "14", "14.0", "9.4", "+0.0", "+12.5%"),
        ("🇩🇪 Frankfurt", "✅ Normal", TEXT_PRI, "15", "17.5", "10.8", "-0.2", "-27.7%"),
        ("🇬🇧 London", "⚠️ Spike", ACCENT_RED, "60", "20.1", "12.1", "+3.3", "+198.0%"),
        ("🇵🇱 Warsaw", "✅ Normal", TEXT_PRI, "14", "11.7", "8.4", "+0.3", "+2.4%"),
    ]
    for i, (region, status, status_col, aircraft, mean, std, zscore, trend) in enumerate(ins_rows):
        row_fill = BG_DARK if i % 2 == 0 else BG_CARD
        draw.rectangle([(16, y), (W - 16, y + 28)], fill=row_fill)
        draw.text((ins_col_x[0] + 6, y + 8), region, fill=TEXT_PRI, font=F["sm"])
        draw.text((ins_col_x[1] + 6, y + 8), status, fill=status_col, font=F["sm"])
        draw.text((ins_col_x[2] + 6, y + 8), aircraft, fill=TEXT_PRI, font=F["sm"])
        draw.text((ins_col_x[3] + 6, y + 8), mean, fill=TEXT_SEC, font=F["sm"])
        draw.text((ins_col_x[4] + 6, y + 8), std, fill=TEXT_SEC, font=F["sm"])
        trend_color = ACCENT_RED if zscore.startswith("+3") else TEXT_PRI
        draw.text((ins_col_x[5] + 6, y + 8), zscore, fill=trend_color, font=F["sm"])
        pct_color = ACCENT_RED if trend.startswith("+1") else TEXT_PRI
        draw.text((ins_col_x[6] + 6, y + 8), trend, fill=pct_color, font=F["sm"])
        y += 28

    # Anomaly expander hint
    y += 10
    draw.rounded_rectangle([(16, y), (W - 16, y + 32)], radius=4, fill=BG_CARD)
    draw.text(
        (28, y + 9), "🚨  Recent anomaly events  (40 detected)  ▸", fill=ACCENT_RED, font=F["sm"]
    )

    # Footer
    draw.text(
        (16, H - 22),
        "Air Traffic Pulse  ·  Analytics Engineering Portfolio Project  ·  v0.1.0",
        fill=TEXT_SEC,
        font=F["xs"],
    )

    out = DOCS_DIR / "screenshot_overview.png"
    img.save(out, "PNG")
    print(f"Saved {out}")


# ── Screenshot 2: Timeseries + anomaly table ──────────────────────────────────


def generate_timeseries() -> None:
    img, draw = _base_canvas()

    y = 68
    _section_header(draw, y, "📈  Aircraft count over time  (5-minute buckets)")
    y += 28

    # Controls row
    draw.text((16, y + 6), "Region", fill=TEXT_SEC, font=F["xs"])
    draw.rounded_rectangle([(16, y + 20), (220, y + 46)], radius=5, fill=BG_CARD)
    draw.text((26, y + 28), "🇬🇧 London  ▾", fill=TEXT_PRI, font=F["sm"])

    draw.text((240, y + 6), "Time window", fill=TEXT_SEC, font=F["xs"])
    draw.rounded_rectangle([(240, y + 20), (420, y + 46)], radius=5, fill=BG_CARD)
    draw.text((250, y + 28), "Last 48h  ▾", fill=TEXT_PRI, font=F["sm"])

    y += 60

    # ── Chart area ────────────────────────────────────────────────────────────
    cx0, cy0, cx1, cy1 = 48, y, W - 20, y + 330
    cw = cx1 - cx0
    ch = cy1 - cy0

    # Y-axis grid lines
    for k in range(6):
        gy = cy0 + ch * k // 5
        draw.line([(cx0, gy), (cx1, gy)], fill=GRID, width=1)
        lv = int(70 * (5 - k) / 5)
        draw.text((16, gy - 6), str(lv), fill=TEXT_SEC, font=F["xs"])

    # Generate synthetic 48h timeseries with two spike events
    n_points = 120  # every 24 min across 48h for display (we subsample)
    max_val = 70.0
    pts_total: list[tuple[int, int]] = []
    pts_pos: list[tuple[int, int]] = []
    anomaly_pts: list[tuple[int, int]] = []

    for i in range(n_points):
        frac = i / (n_points - 1)
        hour = frac * 48.0

        # Day/night cycle (two full days)
        h_in_day = hour % 24
        if 6 <= h_in_day <= 22:
            base = 20 + 12 * math.sin((h_in_day - 6) * math.pi / 16)
        else:
            base = 6 + 3 * math.sin(h_in_day * math.pi / 6)
        base += 2 * math.sin(i * 0.4)

        # Inject spikes
        is_anomaly = False
        hours_ago = 48 - hour
        if 3.0 <= hours_ago <= 3.5 or 10.5 <= hours_ago <= 10.75:
            base *= 3.5
            is_anomaly = True

        base = max(0.0, min(base, max_val))
        positioned = base * 0.88

        px = cx0 + int(cw * frac)
        py_t = cy1 - int((base / max_val) * ch)
        py_p = cy1 - int((positioned / max_val) * ch)
        pts_total.append((px, py_t))
        pts_pos.append((px, py_p))
        if is_anomaly:
            anomaly_pts.append((px, py_t))

    # Fill area under total line
    poly = [(cx0, cy1), *pts_total, (cx1, cy1)]
    draw.polygon(poly, fill=(255, 75, 75, 30))

    # Lines
    for i in range(len(pts_total) - 1):
        draw.line([pts_total[i], pts_total[i + 1]], fill=ACCENT_RED, width=2)
        draw.line([pts_pos[i], pts_pos[i + 1]], fill=ACCENT_BLUE, width=2)

    # Anomaly markers (orange circles)
    for ax, ay in anomaly_pts:
        draw.ellipse(
            [(ax - 6, ay - 6), (ax + 6, ay + 6)], fill=ACCENT_YELL, outline=BG_DARK, width=2
        )

    # X-axis labels
    x_labels = [f"-{48 - int(48 * j / (5))}h" for j in range(6)]
    for j, lbl in enumerate(x_labels):
        lx = cx0 + cw * j // 5
        draw.text((lx - 10, cy1 + 6), lbl, fill=TEXT_SEC, font=F["xs"])
    draw.text((cx1 - 14, cy1 + 6), "now", fill=TEXT_SEC, font=F["xs"])

    # Legend
    lx = W - 310
    draw.line([(lx, cy0 + 14), (lx + 28, cy0 + 14)], fill=ACCENT_RED, width=2)
    draw.text((lx + 34, cy0 + 8), "All aircraft", fill=TEXT_PRI, font=F["sm"])
    draw.line([(lx, cy0 + 34), (lx + 28, cy0 + 34)], fill=ACCENT_BLUE, width=2)
    draw.text((lx + 34, cy0 + 28), "GPS-positioned", fill=TEXT_PRI, font=F["sm"])
    draw.ellipse(
        [(lx + 6, cy0 + 50), (lx + 22, cy0 + 66)], fill=ACCENT_YELL, outline=BG_DARK, width=1
    )
    draw.text((lx + 34, cy0 + 48), "Anomaly bucket", fill=TEXT_PRI, font=F["sm"])

    y = cy1 + 28

    # ── Anomaly table expander ────────────────────────────────────────────────
    draw.rounded_rectangle([(16, y), (W - 16, y + 32)], radius=4, fill=BG_CARD)
    draw.text(
        (28, y + 9),
        "🚨  Anomaly buckets for 🇬🇧 London  (10 total)  ▾",
        fill=ACCENT_RED,
        font=F["sm"],
    )
    y += 36

    anom_hdrs = ["Time (UTC)", "Direction", "Aircraft", "Baseline", "Z-score"]
    anom_col_x = [16, 256, 396, 506, 616]
    _table_row(draw, y, anom_hdrs, anom_col_x, BG_CARD2, TEXT_SEC)
    y += 28

    anom_rows = [
        ("2026-02-26 17:00 UTC", "Spike", "60", "20.1", "+3.3"),
        ("2026-02-26 17:05 UTC", "Spike", "58", "20.1", "+3.2"),
        ("2026-02-26 17:10 UTC", "Spike", "55", "20.1", "+3.0"),
        ("2026-02-26 09:30 UTC", "Spike", "57", "20.1", "+3.1"),
    ]
    for i, row in enumerate(anom_rows):
        row_fill = BG_DARK if i % 2 == 0 else BG_CARD
        draw.rectangle([(16, y), (W - 16, y + 26)], fill=row_fill)
        draw.text((anom_col_x[0] + 6, y + 7), row[0], fill=TEXT_SEC, font=F["sm"])
        draw.text((anom_col_x[1] + 6, y + 7), row[1], fill=ACCENT_YELL, font=F["sm"])
        draw.text((anom_col_x[2] + 6, y + 7), row[2], fill=TEXT_PRI, font=F["sm"])
        draw.text((anom_col_x[3] + 6, y + 7), row[3], fill=TEXT_SEC, font=F["sm"])
        draw.text((anom_col_x[4] + 6, y + 7), row[4], fill=ACCENT_RED, font=F["sm"])
        y += 26

    # Footer
    draw.text(
        (16, H - 22),
        "Air Traffic Pulse  ·  Analytics Engineering Portfolio Project  ·  v0.1.0",
        fill=TEXT_SEC,
        font=F["xs"],
    )

    out = DOCS_DIR / "screenshot_timeseries.png"
    img.save(out, "PNG")
    print(f"Saved {out}")


if __name__ == "__main__":
    generate_overview()
    generate_timeseries()
    print("Done.")
