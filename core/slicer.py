"""
slicer.py – Vertical slice geometry for the Method of Slices.

Divides a sliding mass (bounded above by the slope surface and below by a
trial slip circle) into N vertical slices. Slice properties feed directly
into limit-equilibrium engines (Bishop, Spencer, Janbu).

Supports both homogeneous (single Soil) and multi-layer (Stratigraphy) soil
assignment. The Stratigraphy path queries the soil at the slice BASE depth,
consistent with the failure surface materialising within that soil layer.

Reference:
    Craig's Soil Mechanics, 9th ed., Chapter 9 — Method of Slices.
    Craig §9.4 — layered slope stability (multi-layer soil assignment).
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from models.geometry import SlopeGeometry, SlipCircle
from models.soil import Soil

if TYPE_CHECKING:
    from models.stratigraphy import Stratigraphy
    from core.seepage import PhreaticSurface


# ---------------------------------------------------------------------------
# Slice data class
# ---------------------------------------------------------------------------

class Slice:
    """A single vertical slice of the sliding mass."""

    def __init__(
        self,
        x_mid: float,
        width: float,
        height_top: float,
        height_bottom: float,
        soil: Soil,
    ):
        """
        :param x_mid:         Horizontal centre of the slice (m).
        :param width:         Slice width b (m).
        :param height_top:    y-elevation of the ground surface at x_mid (m).
        :param height_bottom: y-elevation of the slip circle at x_mid (m).
        :param soil:          Soil object occupying this slice.
        """
        self.x      = x_mid
        self.b      = width
        self.h_top  = height_top
        self.h_bot  = height_bottom
        self.height = height_top - height_bottom   # h ≥ 0 guaranteed by caller

        # Weight: W = γ · b · h  (kN per metre run)
        self.weight = soil.gamma * self.b * self.height

        # Base inclination α (radians) – set by create_slices
        self.alpha  = 0.0
        self.soil   = soil

        # Per-slice pore pressure u (kPa) at the slip surface.
        # Set by create_slices when a PhreaticSurface is provided.
        # None means "use scalar ru in the LE engine" (backward-compatible).
        # Reference: Bishop & Morgenstern (1960).
        self.u: float | None = None

    def __repr__(self) -> str:
        return (f"Slice(x={self.x:.2f}m, b={self.b:.2f}m, "
                f"h={self.height:.2f}m, W={self.weight:.1f}kN, "
                f"α={math.degrees(self.alpha):.1f}°)")


# ---------------------------------------------------------------------------
# Intersection helper
# ---------------------------------------------------------------------------

def _find_circle_slope_intersections(
    slope: SlopeGeometry,
    circle: SlipCircle,
    n_scan: int = 2000,
) -> tuple[float, float] | None:
    """
    Numerically locates the x-range where the slip circle lies BELOW the
    ground surface (i.e., where a valid sliding mass exists).

    Strategy: scan the circle's horizontal extent and detect sign changes of
        f(x) = y_surface(x) − y_circle(x)
    The slip mass exists where f(x) > 0.

    :param slope:   SlopeGeometry instance.
    :param circle:  SlipCircle instance.
    :param n_scan:  Number of scan points (higher → more accurate).
    :return:        (x_start, x_end) of the valid mass, or None if not found.
    """
    # Scan within the overlap of circle and slope extents
    x_lo = max(circle.x_left,  slope.x_min)
    x_hi = min(circle.x_right, slope.x_max)

    if x_lo >= x_hi:
        return None

    dx    = (x_hi - x_lo) / n_scan
    x_arr = [x_lo + i * dx for i in range(n_scan + 1)]

    def gap(x: float) -> float | None:
        y_s = slope.get_y_at_x(x)
        y_c = circle.get_y_at_x(x)
        if y_s is None or y_c is None:
            return None
        return y_s - y_c

    # Find leftmost entry (gap transitions from ≤0 to >0)
    x_start = x_end = None
    prev = gap(x_arr[0])

    # Edge case: sliding mass begins exactly at the scan boundary
    if prev is not None and prev > 0:
        x_start = x_arr[0]

    for x in x_arr[1:]:
        curr = gap(x)
        if curr is None:
            prev = curr
            continue
        if prev is not None:
            if prev <= 0 and curr > 0:          # entering the mass
                x_start = x
            elif prev > 0 and curr <= 0:        # leaving the mass
                x_end = x
        prev = curr

    # Handle case where scan ends while still inside the mass
    if x_start is not None and x_end is None:
        x_end = x_arr[-1]

    if x_start is None or x_end is None or x_start >= x_end:
        return None

    return x_start, x_end


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def create_slices(
    slope: SlopeGeometry,
    circle: SlipCircle,
    soil: "Soil | None" = None,
    num_slices: int = 10,
    stratigraphy: "Stratigraphy | None" = None,
    phreatic_surface: "PhreaticSurface | None" = None,
) -> list[Slice]:
    """
    Divides the sliding mass into *num_slices* vertical slices.

    Supports two soil assignment modes:

    1. **Homogeneous** (original behaviour, backward-compatible):
       Pass a single ``soil`` object.  Every slice gets the same Soil.

    2. **Multi-layer** (Sprint 3 — Craig §9.4 layered slopes):
       Pass a ``Stratigraphy`` object.  Each slice queries the Stratigraphy
       for the soil at the *base* mid-depth of the slice
       (y_ground − y_circle) / 2 below the ground surface.
       This is consistent with standard practice where strength parameters
       are assigned to the material at the failure surface.

    The base angle α of each slice is derived from the circle geometry:
        tan(α) = (x_mid − cx) / (cy − y_circle)
    A positive α means the base dips in the direction of sliding (right side).

    Reference (multi-layer):
        Craig §9.4 — layered slope stability; soil assigned at slice base.

    :param slope:        Ground surface geometry.
    :param circle:       Trial slip circle.
    :param soil:         Uniform Soil (use this OR stratigraphy, not both).
    :param num_slices:   Number of slices N (recommend 10–20).
    :param stratigraphy: Multi-layer Stratigraphy (optional; overrides soil).
    :return:             List of Slice objects, ordered left to right.
    :raises ValueError:  If neither soil nor stratigraphy is supplied, or if
                         no valid sliding mass is found.
    """
    if stratigraphy is None and soil is None:
        raise ValueError(
            "Provide either a 'soil' (uniform) or 'stratigraphy' (multi-layer)."
        )
    if num_slices < 1:
        raise ValueError("num_slices must be ≥ 1")

    bounds = _find_circle_slope_intersections(slope, circle)
    if bounds is None:
        raise ValueError(
            "No valid sliding mass found: the slip circle does not intersect "
            "the slope surface within the defined geometry."
        )

    x_start, x_end = bounds
    slice_width     = (x_end - x_start) / num_slices
    slices: list[Slice] = []

    for i in range(num_slices):
        x_mid  = x_start + (i + 0.5) * slice_width
        y_surf = slope.get_y_at_x(x_mid)
        y_circ = circle.get_y_at_x(x_mid)

        # Both coordinates must exist and surface must be above the circle
        if y_surf is None or y_circ is None or y_surf <= y_circ:
            continue

        # ── Soil assignment ────────────────────────────────────────────────
        if stratigraphy is not None:
            # Depth of slice base below the ground surface at x_mid.
            # The reference surface is the top-of-slope y at this x.
            # We use the TOP of the slope profile as z=0 (the highest point).
            y_top  = max(p[1] for p in slope.points)
            z_base = max(0.0, y_top - y_circ)   # depth to slip circle base
            slice_soil = stratigraphy.get_soil_at_depth(z_base)
        else:
            slice_soil = soil  # type: ignore[assignment]

        s = Slice(x_mid, slice_width, y_surf, y_circ, slice_soil)

        # Base angle α from circle geometry
        dx      = x_mid - circle.cx
        dy      = circle.cy - y_circ          # always > 0 for lower arc
        s.alpha = math.atan2(dx, dy)

        # ── Per-slice pore pressure (Sprint 9) ────────────────────────────
        # If a PhreaticSurface is provided, compute u at the slip circle base.
        # u = γ_w × max(0, y_ph(x_mid) − y_circ)
        # Reference: Bishop & Morgenstern (1960).
        if phreatic_surface is not None:
            s.u = phreatic_surface.u_at(x_mid, y_circ)

        slices.append(s)

    return slices
