"""
plot_wall.py -- Matplotlib cross-section of a gravity/cantilever retaining wall
                with active earth pressure diagram and EC7 DA1 annotation.

Renders:
    1. Natural soil (retained fill and foundation soil).
    2. Wall body: base slab + tapered stem.
    3. Active earth pressure diagram (triangular, from run_wall_analysis).
    4. Result annotation: governing combination, sliding FoS_d, bearing η,
       PASS/FAIL verdict.
    5. Dimension annotations: H, B, toe/heel projection.

Returns a matplotlib Figure; never displays or saves (caller decides).

References:
    Eurocode 7 EN 1997-1:2004, §9 — Retaining structures.
    Craig's Soil Mechanics, 9th ed., Ch.11 — Gravity walls.
    Bond, A. & Harris, A. (2008). Decoding Eurocode 7. Taylor & Francis.

Units: metres (m), kPa, kN/m.
"""

import math
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import Polygon

# ── Colour constants ──────────────────────────────────────────────────────────

_C_SOIL_RET  = "#C8A96E"    # tan  — retained fill
_C_SOIL_FND  = "#A0875A"    # dark tan — foundation soil
_C_CONC      = "#9E9E9E"    # grey — concrete wall
_C_ACTIVE    = "#D62728"    # red  — active pressure diagram
_C_PASSIVE   = "#2CA02C"    # green — passive pressure (if shown)
_C_PASS      = "#2CA02C"    # green — PASS
_C_FAIL      = "#D62728"    # red   — FAIL
_C_DIM       = "#555555"    # grey  — dimensions
_C_ARROW     = "#1A3A5C"    # dark blue — force arrow
_ALPHA_FILL  = 0.55


def plot_retaining_wall(\
    analysis: dict,
    title: str = "Retaining Wall — EC7 DA1",
    figsize: tuple = (10, 8),
) -> plt.Figure:
    """
    Cross-section plot of a retaining wall with earth pressure diagram.

    :param analysis: Result dict from api.run_wall_analysis().
    :param title:    Figure title.
    :param figsize:  (width, height) in inches.
    :return:         matplotlib Figure.

    Reference: Craig §11.2 — retaining wall geometry; §11.4 — pressure diagrams.
    """
    w       = analysis["wall"]
    s       = analysis["soil"]
    H       = float(w["H_wall"])
    B       = float(w["B_base"])
    B_toe   = float(w["B_toe"])
    t_base  = float(w.get("t_base", 0.3))
    t_bot   = float(w.get("t_stem_base", 0.35))
    t_top   = float(w.get("t_stem_top", 0.25))
    Ka      = float(analysis.get("Ka", 0.33))
    gamma   = float(s["gamma"])
    passes  = analysis.get("passes", False)
    gov     = analysis.get("comb2", analysis.get("comb1", {}))

    # ── Coordinate system ─────────────────────────────────────────────────────
    # y=0 at top of base slab; y increases upward; wall stem goes from 0 to H.
    # Toe is at x=0; heel at x=B.
    x_stem_left  = B_toe
    x_stem_right = B_toe + t_bot           # base of stem, right face
    x_stem_rtop  = B_toe + t_top           # top of stem, right face

    # Retain soil starts at x=x_stem_right and extends right
    x_fill_right = B + 0.8

    # Foundation soil goes below y=0
    depth_fnd = max(0.6, t_base + 0.3)

    # ── Figure ────────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=figsize)
    ax.set_title(title, fontsize=11, fontweight="bold", color="#1A3A5C", pad=10)

    # ── Foundation soil ───────────────────────────────────────────────────────
    fnd_xs = [-0.5, -0.5, x_fill_right, x_fill_right]
    fnd_ys = [0.0,  -(depth_fnd), -(depth_fnd), 0.0]
    ax.fill(fnd_xs, fnd_ys, color=_C_SOIL_FND, alpha=_ALPHA_FILL, zorder=1)

    # ── Retained fill ─────────────────────────────────────────────────────────
    fill_xs = [x_stem_right, x_stem_rtop, x_stem_rtop, x_fill_right, x_fill_right, x_stem_right]
    fill_ys = [0.0,          H,            H,            H,           0.0,           0.0]
    ax.fill(fill_xs, fill_ys, color=_C_SOIL_RET, alpha=_ALPHA_FILL, zorder=2)

    # ── Ground surface line (retained side) ───────────────────────────────────
    ax.plot([x_stem_rtop, x_fill_right], [H, H],
            color="#5D4037", linewidth=1.5, zorder=4)
    for xi in [x_stem_rtop + i * 0.3 for i in range(int((x_fill_right - x_stem_rtop) / 0.3) + 1)]:
        ax.plot([xi, xi - 0.12], [H, H + 0.1], color="#5D4037", linewidth=0.8, zorder=4)

    # ── Ground surface (excavation / toe side) ────────────────────────────────
    ax.plot([-0.5, x_stem_left], [0.0, 0.0], color="#5D4037", linewidth=1.5, zorder=4)

    # ── Base slab ─────────────────────────────────────────────────────────────
    base = mpatches.Rectangle(
        (0.0, -t_base), B, t_base,
        linewidth=1.5, edgecolor="#333333", facecolor=_C_CONC, zorder=5,
    )
    ax.add_patch(base)

    # ── Stem (tapered) ────────────────────────────────────────────────────────
    stem_xs = [x_stem_left, x_stem_left,      x_stem_rtop, x_stem_right]
    stem_ys = [0.0,          H,                H,            0.0]
    stem_poly = Polygon(
        list(zip(stem_xs, stem_ys)),
        closed=True,
        linewidth=1.5, edgecolor="#333333", facecolor=_C_CONC, zorder=5,
    )
    ax.add_patch(stem_poly)

    # ── Active earth pressure diagram ─────────────────────────────────────────
    # pa(z) = Ka * gamma * z  (z from top of retained height)
    pa_base = Ka * gamma * H   # kPa at base of stem

    # Scale to plot coordinates: 1 kPa → 0.01 * B / pa_base * B (normalised)
    # Choose a display scale so pa_base maps to ~0.35*H in x
    if pa_base > 0:
        pressure_scale = 0.35 * H / pa_base   # m/kPa
    else:
        pressure_scale = 0.01

    # Pressure diagram extends to the LEFT of the stem's left face
    # (active acts toward excavation side)
    pa_x_top  = x_stem_left                    # no pressure at top
    pa_x_base = x_stem_left - pa_base * pressure_scale   # pressure at base

    pres_xs = [pa_x_top, pa_x_base, x_stem_left, pa_x_top]
    pres_ys = [H,        0.0,        0.0,          H]
    ax.fill(pres_xs, pres_ys, color=_C_ACTIVE, alpha=0.25, zorder=3)
    ax.plot([pa_x_top, pa_x_base, x_stem_left],
            [H,        0.0,        0.0],
            color=_C_ACTIVE, linewidth=1.5, zorder=4)

    # Pressure label
    ax.text(pa_x_base - 0.05, 0.08,
            f"p_a = {pa_base:.1f} kPa\n(Ka·γ·H)",
            ha="right", va="bottom", fontsize=7, color=_C_ACTIVE,
            bbox=dict(boxstyle="round,pad=0.2", facecolor="white",
                      edgecolor=_C_ACTIVE, alpha=0.85))

    # Resultant force arrow
    Pa = 0.5 * Ka * gamma * H**2   # kN/m
    arm = H / 3.0
    ax.annotate(
        "", xy=(x_stem_left, arm),
        xytext=(x_stem_left - pa_base * pressure_scale * 0.66, arm),
        arrowprops=dict(arrowstyle="-|>", color=_C_ARROW, lw=1.5),
        zorder=5,
    )
    ax.text(x_stem_left - pa_base * pressure_scale * 0.33, arm + 0.08,
            f"Pa = {Pa:.1f} kN/m", ha="center", fontsize=7, color=_C_ARROW)

    # ── Dimension annotations ─────────────────────────────────────────────────
    dim_clr = _C_DIM

    # H — wall height
    ax.annotate("", xy=(x_fill_right + 0.35, 0.0), xytext=(x_fill_right + 0.35, H),
                arrowprops=dict(arrowstyle="<->", color=dim_clr, lw=1.0))
    ax.text(x_fill_right + 0.45, H / 2, f"H = {H:.2f} m",
            ha="left", va="center", fontsize=7.5, color=dim_clr)

    # B — base width
    dim_y_base = -t_base - 0.18
    ax.annotate("", xy=(0, dim_y_base), xytext=(B, dim_y_base),
                arrowprops=dict(arrowstyle="<->", color=dim_clr, lw=1.0))
    ax.text(B / 2, dim_y_base - 0.12, f"B = {B:.2f} m",
            ha="center", va="top", fontsize=7.5, color=dim_clr)

    # ── Result annotation box ─────────────────────────────────────────────────
    c_result = _C_PASS if passes else _C_FAIL
    sl  = gov.get("sliding", {})
    ov  = gov.get("overturn", {})
    br  = gov.get("bearing", {})
    lines = [
        f"Governing: {gov.get('label', '?')}",
        f"Ka = {Ka:.4f}",
        f"Sliding  FoS_d = {sl.get('fos_d', '?'):.3f}" if isinstance(sl.get('fos_d'), float) else "Sliding FoS_d = ?",
        f"Overturn FoS_d = {ov.get('fos_d', '?'):.3f}" if isinstance(ov.get('fos_d'), float) else "Overturn FoS_d = ?",
        f"Bearing  η     = {br.get('utilisation', '?'):.3f}" if isinstance(br.get('utilisation'), float) else "Bearing η = ?",
        ("PASS ✓" if passes else "FAIL ✗"),
    ]
    ax.text(
        x_fill_right - 0.05, H - 0.1,
        "\n".join(lines),
        ha="right", va="top", fontsize=7.5,
        bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                  edgecolor=c_result, linewidth=1.5),
        zorder=6,
    )

    # ── Soil label ────────────────────────────────────────────────────────────
    ax.text(x_fill_right - 0.1, H / 2,
            f"{s['name']}\nγ = {s['gamma']:.1f} kN/m³\nφ' = {s.get('phi_k', '?'):.1f}°",
            ha="right", va="center", fontsize=7, color="#5D4037", alpha=0.8)

    # ── Axes tidying ──────────────────────────────────────────────────────────
    x_min = min(pa_x_base - 0.3, -0.6)
    ax.set_xlim(x_min, x_fill_right + 0.7)
    ax.set_ylim(-t_base - 0.45, H + 0.55)
    ax.set_xlabel("Horizontal distance (m)", fontsize=8)
    ax.set_ylabel("Elevation (m, 0 = top of base slab)", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.grid(True, linestyle=":", linewidth=0.4, alpha=0.5)

    fig.tight_layout()
    return fig


def save_wall_plot(analysis: dict, filepath: str, **kwargs) -> None:
    """
    Save the retaining wall cross-section plot to a file.

    :param analysis: Result dict from api.run_wall_analysis().
    :param filepath: Output file path (PNG, PDF, SVG — any matplotlib format).
    :param kwargs:   Forwarded to plot_retaining_wall().
    """
    fig = plot_retaining_wall(analysis, **kwargs)
    fig.savefig(filepath, dpi=150, bbox_inches="tight")
    plt.close(fig)
