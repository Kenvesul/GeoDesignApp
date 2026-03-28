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
    y_min = min(ys) - circle.r * 1.1   # room below circle

    # Fill polygon: ground surface + baseline
    fill_x = [x_min] + list(xs) + [x_max, x_max, x_min]
    fill_y = [ys[0]]  + list(ys) + [ys[-1], y_min,  y_min]
    ax.fill(fill_x, fill_y, color=_C_GROUND, alpha=_ALPHA_FILL, zorder=1)
    ax.plot(xs, ys, color=_C_GROUND_L, linewidth=2.5, zorder=2, label="Ground surface")

    # ── 2. Critical slip circle (arc below ground surface only) ───────────
    cx, cy, r = circle.cx, circle.cy, circle.r

    # Parametric arc: find angles where circle intersects the ground
    # For a full circle, draw 0 to 2pi and clip with ground surface fill.
    # Simplification: draw the full circle arc clipped below ground profile.
    theta = [math.radians(t) for t in range(0, 361)]
    circ_x = [cx + r * math.cos(t) for t in theta]
    circ_y = [cy + r * math.sin(t) for t in theta]

    # Only plot points that are below the ground surface
    def _ground_y_at_x(x):
        return slope.get_y_at_x(x)

    arc_x, arc_y = [], []
    for px, py in zip(circ_x, circ_y):
        if slope.x_min <= px <= slope.x_max:
            ground_y = _ground_y_at_x(px)
            if ground_y is not None and py <= ground_y + 0.05:
                arc_x.append(px)
                arc_y.append(py)
        else:
            if arc_x:
                ax.plot(arc_x, arc_y, color=_C_CIRCLE, linewidth=2.0,
                        linestyle="--", zorder=4)
                arc_x, arc_y = [], []

    if arc_x:
        ax.plot(arc_x, arc_y, color=_C_CIRCLE, linewidth=2.0, linestyle="--",
                zorder=4, label=f"Critical circle (FoS={fos:.3f})")

    # Centre marker
    ax.plot(cx, cy, marker="+", color=_C_CIRCLE, markersize=10, markeredgewidth=2, zorder=5)

    # ── 3. Slice borders ──────────────────────────────────────────────────
    # Find the x-extent of the slip circle intersecting the slope
    # entry point (toe) and exit point (crest)
    bounds = _find_circle_slope_intersections(slope, circle)
    if bounds is not None:
        x_entry, x_exit = bounds
    else:
        x_entry = x_exit = 0.0

    if x_exit > x_entry and n_slices > 0:
        dx_slice = (x_exit - x_entry) / n_slices
        for i in range(1, n_slices):
            xi = x_entry + i * dx_slice
            # Top: ground surface
            y_top = _ground_y_at_x(xi)
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
