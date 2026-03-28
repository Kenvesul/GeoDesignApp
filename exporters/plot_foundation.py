"""
plot_foundation.py -- Matplotlib cross-section of a spread foundation with
                      pressure bulb and EC7 bearing capacity annotation.

Renders:
    1. Soil profile (natural ground + embedment fill).
    2. Foundation block (concrete rectangle) at embedment depth Df.
    3. Stress isobars beneath the footing (semi-elliptic pressure bulb).
    4. Dimension annotations: B, L (if finite), Df.
    5. Annotation box: q_ult_k, utilisation, PASS/FAIL from EC7 DA1.

Returns a matplotlib Figure; never displays or saves (caller decides).

References:
    Eurocode 7 EN 1997-1:2004, Annex D — Bearing capacity formulae.
    Craig's Soil Mechanics, 9th ed., Ch.8 — Stress distribution.
    Das, B.M. (2019). Principles of Geotechnical Engineering, §3.6.

Units: metres (m), kPa, kN.
"""

import math
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch

# ── Colour constants ──────────────────────────────────────────────────────────

_C_SOIL      = "#C8A96E"   # tan — natural soil
_C_FILL      = "#A0875A"   # darker tan — overburden fill
_C_CONC      = "#9E9E9E"   # grey — concrete footing
_C_LOAD      = "#1A3A5C"   # dark blue — applied load arrow
_C_BULB      = "#2E6DA4"   # mid blue — stress contour
_C_PASS      = "#2CA02C"   # green — PASS
_C_FAIL      = "#D62728"   # red — FAIL
_C_DIM       = "#555555"   # grey — dimensions
_ALPHA_FILL  = 0.55
_ALPHA_BULB  = 0.25


def plot_foundation_bearing(\
    analysis: dict,
    title: str = "Foundation Bearing Capacity — EC7 DA1",
    figsize: tuple = (9, 7),
) -> plt.Figure:
    """
    Cross-section plot of an isolated/strip footing with EC7 results.

    :param analysis: Result dict from api.run_foundation_analysis().
    :param title:    Figure title.
    :param figsize:  (width, height) in inches.
    :return:         matplotlib Figure object.

    Reference: Craig §8.1 — stress distribution beneath foundations.
    """
    f       = analysis["foundation"]
    s       = analysis["soil"]
    B       = float(f["B"])
    Df      = float(f["Df"])
    passes  = analysis.get("passes", False)
    gov     = analysis.get("comb2", analysis.get("comb1", {}))
    util    = gov.get("utilisation", None)
    q_ult   = analysis.get("q_ult_k", None)

    # ── Figure / axes setup ───────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=figsize)
    ax.set_title(title, fontsize=11, fontweight="bold", color="#1A3A5C", pad=10)

    # ── Coordinate system ─────────────────────────────────────────────────────
    # y=0 at ground surface; y=-Df at base of footing; y negative = below ground.
    half_B  = B / 2.0
    depth_show = max(Df + 2.0 * B, Df + 1.5)   # how deep to draw
    x_ext   = max(B * 2.0, 2.0)                  # horizontal extent each side

    # ── Natural soil body ─────────────────────────────────────────────────────
    soil_xs = [-x_ext - 0.2, -x_ext - 0.2, x_ext + 0.2, x_ext + 0.2]
    soil_ys = [0.3, -depth_show, -depth_show, 0.3]
    ax.fill(soil_xs, soil_ys, color=_C_SOIL, alpha=_ALPHA_FILL, zorder=1)

    # ── Overburden fill (above footing base, beside footing) ──────────────────
    # Left side
    ax.fill([-x_ext - 0.2, -x_ext - 0.2, -half_B, -half_B],
            [0.2, -Df,      -Df,   0.2],
            color=_C_FILL, alpha=0.65, zorder=2)
    # Right side
    ax.fill([half_B,  half_B,  x_ext + 0.2, x_ext + 0.2],
            [0.2,    -Df,     -Df,         0.2],
            color=_C_FILL, alpha=0.65, zorder=2)

    # ── Ground surface line ───────────────────────────────────────────────────
    ax.axhline(0.0, color="#5D4037", linewidth=1.5, zorder=3)
    # Hatch marks
    for xi in [x * 0.35 for x in range(-5, 6)]:
        ax.plot([xi, xi - 0.15], [0.0, 0.12],
                color="#5D4037", linewidth=0.8, zorder=3)

    # ── Footing rectangle ─────────────────────────────────────────────────────
    footing = mpatches.FancyBboxPatch(
        (-half_B, -Df),
        B, Df * 0.35,
        boxstyle="square,pad=0",
        linewidth=1.5, edgecolor="#333333", facecolor=_C_CONC,
        zorder=4,
    )
    ax.add_patch(footing)

    # ── Applied load arrow ────────────────────────────────────────────────────
    arrow_top  = Df * 0.35 + 0.25
    arrow_tip  = Df * 0.22
    ax.annotate(
        "", xy=(0, -Df + arrow_tip), xytext=(0, arrow_top),
        arrowprops=dict(arrowstyle="-|>", color=_C_LOAD, lw=2.0),
        zorder=5,
    )
    vd_str = f"V_d = {gov.get('Vd', '?'):.1f} kN/m" if "Vd" in gov else "Applied load"
    ax.text(0.12, (arrow_top - Df * 0.05) / 2,
            vd_str, fontsize=7.5, color=_C_LOAD, va="center", zorder=5)

    # ── Stress pressure bulb (simplified Boussinesq isobars) ──────────────────
    # Draw 3 semi-elliptic contours at 50%, 25%, 10% of contact pressure.
    # Contour depths scale approximately as multiples of B.
    footing_base_y = -Df
    for frac, label in [(0.5, "0.5q"), (0.25, "0.25q"), (0.1, "0.1q")]:
        depth_mult = {0.5: 0.5, 0.25: 1.0, 0.1: 2.0}[frac]
        bulb_depth = B * depth_mult
        bulb_width = B * depth_mult * 0.9
        ell = mpatches.Ellipse(
            (0, footing_base_y - bulb_depth / 2),
            width=bulb_width * 2,
            height=bulb_depth,
            fill=False,
            edgecolor=_C_BULB,
            linewidth=0.8,
            linestyle="--",
            alpha=0.55,
            zorder=3,
        )
        ax.add_patch(ell)
        ax.text(bulb_width + 0.05, footing_base_y - bulb_depth / 2,
                label, fontsize=6, color=_C_BULB, va="center", alpha=0.75)

    # ── Dimension annotations ─────────────────────────────────────────────────
    # B dimension (horizontal)
    dim_y = 0.35
    ax.annotate("", xy=(-half_B, dim_y), xytext=(half_B, dim_y),
                arrowprops=dict(arrowstyle="<->", color=_C_DIM, lw=1.0))
    ax.text(0, dim_y + 0.06, f"B = {B:.2f} m",
            ha="center", fontsize=7.5, color=_C_DIM)

    # Df dimension (vertical, left side)
    dim_x = -x_ext + 0.1
    ax.annotate("", xy=(dim_x, 0.0), xytext=(dim_x, -Df),
                arrowprops=dict(arrowstyle="<->", color=_C_DIM, lw=1.0))
    ax.text(dim_x - 0.15, -Df / 2, f"Df\n{Df:.2f} m",
            ha="right", va="center", fontsize=7, color=_C_DIM)

    # ── Result annotation box ─────────────────────────────────────────────────
    c_result = _C_PASS if passes else _C_FAIL
    lines = [
        f"φ'_k = {s['phi_k']:.1f}°   c'_k = {s.get('c_k', 0):.1f} kPa",
        f"γ = {s['gamma']:.1f} kN/m³",
    ]
    if q_ult is not None:
        lines.append(f"q_ult_k = {q_ult:.1f} kPa")
    if util is not None:
        lines.append(f"Utilisation η = {util:.3f}")
    lines.append(("PASS ✓" if passes else "FAIL ✗"))

    box_txt = "\n".join(lines)
    ax.text(
        x_ext - 0.05, -depth_show + 0.2, box_txt,
        ha="right", va="bottom", fontsize=7.5,
        bbox=dict(boxstyle="round,pad=0.4", facecolor="white",
                  edgecolor=c_result, linewidth=1.5),
        color=c_result if not passes else "#333333",
        zorder=6,
    )
    # Colour the PASS/FAIL line
    lines_split = box_txt.split("\n")
    # (the whole textbox already carries the border colour)

    # ── Soil label ────────────────────────────────────────────────────────────
    ax.text(-x_ext + 0.05, -depth_show + 0.2,
            f"{s['name']}\nγ = {s['gamma']:.1f} kN/m³\nφ' = {s['phi_k']:.1f}°",
            fontsize=7, color="#5D4037", va="bottom",
            bbox=dict(boxstyle="round,pad=0.3", facecolor="#FFF9F0",
                      edgecolor="#C8A96E", alpha=0.85))

    # ── Axes tidying ──────────────────────────────────────────────────────────
    ax.set_xlim(-x_ext - 0.3, x_ext + 0.3)
    ax.set_ylim(-depth_show - 0.1, 0.8)
    ax.set_xlabel("Horizontal distance (m)", fontsize=8)
    ax.set_ylabel("Elevation (m, 0 = ground surface)", fontsize=8)
    ax.tick_params(labelsize=7)
    ax.grid(True, linestyle=":", linewidth=0.4, alpha=0.5)

    fig.tight_layout()
    return fig


def save_foundation_plot(analysis: dict, filepath: str, **kwargs) -> None:
    """
    Save the foundation cross-section plot to a file.

    :param analysis: Result dict from api.run_foundation_analysis().
    :param filepath: Output file path (PNG, PDF, SVG — any matplotlib format).
    :param kwargs:   Forwarded to plot_foundation_bearing().
    """
    fig = plot_foundation_bearing(analysis, **kwargs)
    fig.savefig(filepath, dpi=150, bbox_inches="tight")
    plt.close(fig)
