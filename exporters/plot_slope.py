"""
plot_slope.py -- Matplotlib cross-section plot of a slope with critical slip circle.

Renders the slope geometry (ground surface polyline), the critical slip circle,
the slice discretisation, and an annotation box with the governing FoS result.
Returns a matplotlib Figure object; does NOT display or save to disk
(the caller decides what to do with the figure).

Reference:
    Craig's Soil Mechanics, 9th ed., Chapter 9 (slope stability figures).
    Bishop, A.W. (1955) -- critical circle visualisation convention.

Sign conventions / coordinates:
    x  -- horizontal, positive right.
    y  -- vertical, positive up.
    All distances in metres.

Units:
    All spatial inputs in metres (m).  FoS dimensionless.
"""

import math
import matplotlib
matplotlib.use("Agg")   # non-interactive backend -- safe for server/test environments
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import Arc, FancyArrowPatch

from models.geometry        import SlopeGeometry, SlipCircle
from core.search            import SearchResult
from core.slicer            import _find_circle_slope_intersections


# ============================================================
#  Colour / style constants
# ============================================================

_C_GROUND   = "#8B6914"   # brown -- soil fill
_C_GROUND_L = "#C8A96E"   # light tan -- ground surface line
_C_CIRCLE   = "#D62728"   # red -- critical slip circle
_C_SLICE    = "#4C72B0"   # blue -- slice borders
_C_WATER    = "#AEC6CF"   # light blue -- water table (future)
_ALPHA_FILL = 0.35


def _ground_y_at_x(slope: SlopeGeometry, x: float) -> float:
    """Piecewise-linear ground interpolation with end clamping."""
    pts = slope.points
    if x <= pts[0][0]:
        return pts[0][1]
    if x >= pts[-1][0]:
        return pts[-1][1]

    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        lo = min(x1, x2)
        hi = max(x1, x2)
        if lo <= x <= hi:
            if abs(x2 - x1) < 1e-9:
                return max(y1, y2)
            t = (x - x1) / (x2 - x1)
            return y1 + t * (y2 - y1)
    return pts[-1][1]


def plot_slope_stability(
    slope   : SlopeGeometry,
    result  : SearchResult,
    title   : str  = "Slope Stability Analysis",
    n_slices: int  = 20,
    ru      : float = 0.0,
    figsize : tuple = (10, 6),
) -> plt.Figure:
    """
    Produces a cross-section plot of the slope with the critical slip circle.

    Draws:
        1. Ground surface polyline (filled below with soil colour).
        2. Critical slip circle arc (below-ground portion only).
        3. Vertical slice borders within the slip mass.
        4. Annotation box: FoS_d, method, circle centre and radius.
        5. Axes labels, grid, and title.

    :param slope:    SlopeGeometry defining the ground surface polyline.
    :param result:   SearchResult from core/search.py (critical circle + FoS).
    :param title:    Figure title string.
    :param n_slices: Number of vertical slice lines to draw (visual only).
    :param ru:       Pore pressure ratio (label only, not used in geometry).
    :param figsize:  Matplotlib figure size tuple (width, height) in inches.
    :return:         matplotlib Figure object.
    """
    circle: SlipCircle = result.critical_circle
    fos   : float      = result.best_fos_result.fos

    fig, ax = plt.subplots(figsize=figsize)

    # ── 1. Ground surface and filled soil body ─────────────────────────────
    xs = [p[0] for p in slope.points]
    ys = [p[1] for p in slope.points]

    x_min = min(xs) - 1.0
    x_max = max(xs) + 1.0
    # The bottom of the visible arc is cy - r (lowest point of circle).
    # Add a small margin below the deepest feature (arc bottom or slope toe).
    arc_bottom = circle.cy - circle.r
    y_min = min(min(ys), arc_bottom) - 0.5

    # Fill polygon: ground surface + baseline
    fill_x = [x_min] + list(xs) + [x_max, x_max, x_min]
    fill_y = [ys[0]]  + list(ys) + [ys[-1], y_min,  y_min]
    ax.fill(fill_x, fill_y, color=_C_GROUND, alpha=_ALPHA_FILL, zorder=1)
    ax.plot(xs, ys, color=_C_GROUND_L, linewidth=2.5, zorder=2, label="Ground surface")

    # ── 2. Critical slip circle (arc below ground surface only) ───────────
    cx, cy, r = circle.cx, circle.cy, circle.r

    # Find the entry and exit x-coordinates of the slip arc (where it
    # intersects the ground surface).  Use the same function as slicer.py
    # so the visualised arc is exactly consistent with the computed slices.
    bounds = _find_circle_slope_intersections(slope, circle)
    if bounds is not None:
        x_entry, x_exit = bounds
    else:
        # Fall back: full lower arc clipped to slope x range
        x_entry = max(circle.x_left,  slope.x_min)
        x_exit  = min(circle.x_right, slope.x_max)

    # Convert x entry/exit to angles on the circle.
    # We parameterise the circle as  x = cx + r·cos(θ), y = cy + r·sin(θ).
    # The lower arc spans θ in [π+ε, 2π-ε] (y below centre).
    # Entry angle (left-hand intersection):
    #   cos(θ_entry) = (x_entry - cx) / r
    def _x_to_angle_lower(x: float) -> float:
        """Angle on the lower arc corresponding to horizontal position x."""
        cos_val = max(-1.0, min(1.0, (x - cx) / r))
        # Lower arc: sin(θ) < 0  →  θ in [π, 2π], i.e. negative acos
        return -math.acos(cos_val)  # returns angle in [-π, 0]

    n_arc = 300
    # Build arc from entry to exit using linspace over x
    import numpy as _np
    arc_xs = _np.linspace(x_entry, x_exit, n_arc)
    arc_ys = []
    for arc_x in arc_xs:
        disc = r**2 - (arc_x - cx)**2
        if disc < 0:
            arc_ys.append(None)
        else:
            arc_ys.append(cy - math.sqrt(disc))   # lower arc

    # Plot as a single continuous segment (filter out None gaps)
    seg_x, seg_y = [], []
    for arc_x, arc_y in zip(arc_xs, arc_ys):
        if arc_y is None:
            if seg_x:
                ax.plot(seg_x, seg_y, color=_C_CIRCLE, linewidth=2.0,
                        linestyle="--", zorder=4)
                seg_x, seg_y = [], []
        else:
            seg_x.append(arc_x)
            seg_y.append(arc_y)

    if seg_x:
        ax.plot(seg_x, seg_y, color=_C_CIRCLE, linewidth=2.5, linestyle="--",
                zorder=4, label=f"Critical circle (FoS={fos:.3f})")

    # Centre marker
    ax.plot(cx, cy, marker="+", color=_C_CIRCLE, markersize=12,
            markeredgewidth=2.0, zorder=5)
    # Draw a thin full-circle outline (dashed, lighter) so the centre
    # context is visible even when the centre is outside the plot area.
    theta_full = [math.radians(t) for t in range(0, 361, 2)]
    full_x = [cx + r * math.cos(t) for t in theta_full]
    full_y = [cy + r * math.sin(t) for t in theta_full]
    ax.plot(full_x, full_y, color=_C_CIRCLE, linewidth=0.5,
            linestyle=":", alpha=0.35, zorder=3)

    # ── 3. Slice borders ──────────────────────────────────────────────────
    # Reuse bounds from the arc calculation above.
    if bounds is not None and x_exit > x_entry and n_slices > 0:
        dx_slice = (x_exit - x_entry) / n_slices
        for i in range(1, n_slices):
            xi = x_entry + i * dx_slice
            # Top: ground surface
            y_top = _ground_y_at_x(slope, xi)
            # Bottom: circle surface
            disc = r**2 - (xi - cx)**2
            if disc < 0:
                continue
            y_bot = cy - math.sqrt(disc)
            if y_bot < y_top:
                ax.plot([xi, xi], [y_bot, y_top],
                        color=_C_SLICE, linewidth=0.6, alpha=0.5, zorder=3)

    # ── 4. Annotation box ────────────────────────────────────────────────
    method = result.best_fos_result.method.replace("_", " ").title()
    ann_text = (
        f"Method : {method}\n"
        f"FoS    : {fos:.4f}\n"
        f"Centre : ({cx:.2f}, {cy:.2f}) m\n"
        f"Radius : {r:.2f} m\n"
        f"ru     : {ru:.2f}"
    )
    ax.text(
        0.02, 0.97, ann_text,
        transform=ax.transAxes,
        fontsize=8, verticalalignment="top",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="white", alpha=0.85, edgecolor="grey"),
        family="monospace",
        zorder=6,
    )

    # ── 5. Formatting ──────────────────────────────────────────────────────
    ax.set_xlim(x_min, x_max)
    ax.set_ylim(y_min, max(ys) + 0.5)
    ax.set_aspect("equal")
    ax.set_xlabel("Horizontal distance (m)", fontsize=9)
    ax.set_ylabel("Elevation (m)", fontsize=9)
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.legend(loc="upper right", fontsize=8)
    ax.grid(True, linestyle=":", linewidth=0.5, alpha=0.6)
    ax.tick_params(labelsize=8)

    fig.tight_layout()
    return fig


def save_slope_plot(
    slope   : SlopeGeometry,
    result  : SearchResult,
    filepath: str,
    title   : str  = "Slope Stability Analysis",
    dpi     : int  = 150,
    **kwargs,
) -> None:
    """
    Convenience wrapper: renders and saves the slope plot to a file.

    :param slope:    SlopeGeometry.
    :param result:   SearchResult.
    :param filepath: Output file path (e.g. 'output/slope.png' or 'slope.pdf').
    :param title:    Figure title.
    :param dpi:      Resolution (dots per inch).  Default 150.
    :param kwargs:   Passed to plot_slope_stability().
    :raises OSError: If the output directory does not exist.
    """
    fig = plot_slope_stability(slope, result, title=title, **kwargs)
    fig.savefig(filepath, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
