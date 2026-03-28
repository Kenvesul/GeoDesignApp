"""
seepage.py — Pore pressure from phreatic surface and steady-state seepage.

Two main capabilities:

  1. PhreaticSurface:  Piecewise-linear phreatic line defined by (x, y) co-
     ordinates.  Given a point in the slope (x, z_base) and the height of
     soil above it h_soil, the class computes:
         u(x, z)  = γ_w × max(0,  y_ph(x) − z_base)   [kPa]
         r_u(x,z) = u / (γ × h_soil)                   [-]
     where y_ph(x) is the interpolated phreatic elevation.

     These are the per-slice inputs needed for Bishop Simplified and
     Spencer stability analyses under non-uniform pore pressure.

     Reference:
         Bishop, A.W. & Morgenstern, N.R. (1960). Stability coefficients
         for earth slopes. Géotechnique 10(4), 129–150.

  2. Dupuit steady-state seepage through a homogeneous embankment:
         q(k, h1, h2, L) = k × (h1² − h2²) / (2L)    [m²/s per m run]
         h(x)             = √(h1² − (h1²−h2²)·x/L)   [m]

     The parabolic phreatic surface from Dupuit (1863) is valid for
     homogeneous, isotropic, unconfined flow with a negligible vertical
     velocity component (Dupuit assumption).

     Reference:
         Dupuit, J. (1863). Études Théoriques et Pratiques sur le
         Mouvement des Eaux. Dunod, Paris.
         Craig's Soil Mechanics, 9th ed., §2.7 (seepage analysis).
         Das, B.M. (2019). Principles of Geotechnical Engineering, §7.8.

Nomenclature:
    u         : pore water pressure at a point (kPa).
    r_u       : dimensionless pore pressure ratio = u / (γ·h).
    γ_w       : unit weight of water (kN/m³);  default 9.81.
    γ         : bulk unit weight of soil (kN/m³).
    h_soil    : height of soil above the point of interest (m).
    h_w       : height of water above the point (phreatic head, m).
    h1, h2    : upstream and downstream water levels above the datum (m).
    L         : horizontal seepage path length (m).
    k         : coefficient of permeability (m/s).
    q         : seepage flow per unit width (m²/s).

Sign conventions:
    y (elevation) increases upward.
    x increases in the downstream direction.

Units:
    Lengths (m), pressures (kPa), unit weights (kN/m³).
    Seepage flow (m²/s per metre run of embankment).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

# ── Constants ────────────────────────────────────────────────────────────────

GAMMA_W: float = 9.81   # Unit weight of water (kN/m³)


# ============================================================
#  Primitive pore-pressure functions
# ============================================================

def pore_pressure_from_phreatic(
    phreatic_y : float,
    base_y     : float,
    gamma_w    : float = GAMMA_W,
) -> float:
    """
    Pore pressure at a point from phreatic surface elevation.

    u = γ_w × max(0, y_ph − y_base)

    Tension (phreatic surface below the point) is clamped to zero;
    negative pore pressures are not modelled here.

    Reference:
        Bishop & Morgenstern (1960), eq. (1).
        Craig §9.2 (pore pressure on a slip surface).

    :param phreatic_y : Elevation of phreatic surface (m).
    :param base_y     : Elevation of the point (e.g. slip circle base) (m).
    :param gamma_w    : Unit weight of water (kN/m³).  Default 9.81.
    :return: Pore pressure u (kPa).  Always ≥ 0.
    """
    if gamma_w <= 0.0:
        raise ValueError(f"gamma_w must be > 0, got {gamma_w}")
    h_w = max(0.0, phreatic_y - base_y)
    return gamma_w * h_w


def ru_at_point(
    u       : float,
    gamma   : float,
    h_soil  : float,
) -> float:
    """
    Dimensionless pore pressure ratio r_u at a point.

    r_u = u / (γ · h_soil)

    This is the pore pressure parameter used in Bishop Simplified
    and Spencer stability analyses.

    Reference:
        Bishop & Morgenstern (1960), §3 (stability coefficients).
        Craig §9.2, eq. (9.5).

    :param u      : Pore pressure at the point (kPa).  Must be ≥ 0.
    :param gamma  : Bulk unit weight of soil above the point (kN/m³).
    :param h_soil : Height of soil above the point (m).  Must be > 0.
    :return: r_u (dimensionless).
    :raises ValueError: If h_soil ≤ 0 or gamma ≤ 0.
    """
    if gamma <= 0.0:
        raise ValueError(f"gamma must be > 0, got {gamma}")
    if h_soil <= 0.0:
        raise ValueError(f"h_soil must be > 0, got {h_soil}")
    if u < 0.0:
        raise ValueError(f"u must be >= 0, got {u}")
    return u / (gamma * h_soil)


# ============================================================
#  Dupuit steady-state seepage
# ============================================================

def dupuit_seepage_flow(
    h1 : float,
    h2 : float,
    L  : float,
    k  : float,
) -> float:
    """
    Dupuit (1863) steady seepage flow per unit width through a homogeneous
    unconfined aquifer or embankment.

    q = k · (h1² − h2²) / (2 · L)

    Applies under the Dupuit assumption: the hydraulic gradient equals
    the slope of the free surface, and equipotential lines are vertical.
    Valid for L >> h1 (small free-surface slope).

    Reference:
        Dupuit, J. (1863). Études Théoriques et Pratiques sur le Mouvement
        des Eaux. Dunod, Paris.
        Craig's Soil Mechanics, 9th ed., §2.7, eq. (2.30).
        Das, B.M. (2019). Principles of Geotechnical Engineering, §7.8.

    :param h1 : Upstream water level above the impermeable base (m).
    :param h2 : Downstream water level above the impermeable base (m).
    :param L  : Seepage path length (horizontal distance, m).
    :param k  : Coefficient of permeability (m/s).  Must be > 0.
    :return: Seepage flow q (m²/s per metre run).
    :raises ValueError: If h1 < h2, L ≤ 0, or k ≤ 0.
    """
    if h1 < 0.0:
        raise ValueError(f"h1 must be >= 0, got {h1}")
    if h2 < 0.0:
        raise ValueError(f"h2 must be >= 0, got {h2}")
    if h1 < h2:
        raise ValueError(f"h1 ({h1}) must be >= h2 ({h2}) for downstream flow")
    if L <= 0.0:
        raise ValueError(f"L must be > 0, got {L}")
    if k <= 0.0:
        raise ValueError(f"k must be > 0, got {k}")
    return k * (h1 ** 2 - h2 ** 2) / (2.0 * L)


def dupuit_phreatic_height(
    h1 : float,
    h2 : float,
    L  : float,
    x  : float,
) -> float:
    """
    Dupuit (1863) phreatic surface height at distance x from upstream.

    h(x) = √(h1² − (h1² − h2²) · x / L)

    Derived from the condition that q(x) = const (continuity):
        q = −k · h · dh/dx  ⟹  h² linear in x.

    Reference:
        Craig's Soil Mechanics, 9th ed., §2.7, eq. (2.31).
        Das (2019), §7.8.

    :param h1 : Upstream water level (m).  Must be ≥ h2.
    :param h2 : Downstream water level (m).  Must be ≥ 0.
    :param L  : Seepage path length (m).  Must be > 0.
    :param x  : Distance from upstream face (m).  Must be in [0, L].
    :return: Phreatic surface height h(x) (m above impermeable base).
    :raises ValueError: Invalid inputs.
    """
    if h1 < 0.0:
        raise ValueError(f"h1 must be >= 0, got {h1}")
    if h2 < 0.0:
        raise ValueError(f"h2 must be >= 0, got {h2}")
    if h1 < h2:
        raise ValueError(f"h1 ({h1}) must be >= h2 ({h2})")
    if L <= 0.0:
        raise ValueError(f"L must be > 0, got {L}")
    if not (0.0 - 1e-9 <= x <= L + 1e-9):
        raise ValueError(f"x ({x}) must be in [0, L={L}]")
    x = max(0.0, min(L, x))  # clamp to [0, L]
    h_sq = h1 ** 2 - (h1 ** 2 - h2 ** 2) * x / L
    return math.sqrt(max(0.0, h_sq))


def build_dupuit_surface(
    h1         : float,
    h2         : float,
    L          : float,
    x_offset   : float = 0.0,
    y_base     : float = 0.0,
    n_points   : int   = 21,
    gamma_w    : float = GAMMA_W,
) -> "PhreaticSurface":
    """
    Construct a PhreaticSurface from the Dupuit parabolic profile.

    Useful for inserting a steady-state phreatic line into a slope
    stability analysis.

    :param h1       : Upstream water level above impermeable base (m).
    :param h2       : Downstream water level (m).
    :param L        : Seepage path length (m).
    :param x_offset : Global x-coordinate of the upstream face (m).
    :param y_base   : Elevation of the impermeable base datum (m).
    :param n_points : Number of nodes defining the piecewise line.
                      Must be ≥ 2.
    :param gamma_w  : Unit weight of water (kN/m³).
    :return: PhreaticSurface instance.
    """
    if n_points < 2:
        raise ValueError(f"n_points must be >= 2, got {n_points}")
    xs = [L * i / (n_points - 1) for i in range(n_points)]
    pts = [
        (x_offset + x, y_base + dupuit_phreatic_height(h1, h2, L, x))
        for x in xs
    ]
    return PhreaticSurface(points=pts, gamma_w=gamma_w)


# ============================================================
#  PhreaticSurface
# ============================================================

@dataclass
class PhreaticSurface:
    """
    Piecewise-linear phreatic surface defined by (x, y) co-ordinates.

    The surface is linearly interpolated between nodes.  Outside the
    defined range, the surface is extrapolated as horizontal (clipped
    to the nearest boundary value) — this is conservative for pore
    pressure (overestimates u outside the data range).

    Attributes
    ----------
    points   : List of (x, y) tuples defining the surface.
               Must have ≥ 2 nodes, x values strictly increasing.
    gamma_w  : Unit weight of water (kN/m³).  Default 9.81.

    Methods
    -------
    y_at(x)                       → phreatic elevation at x (m)
    u_at(x, base_y)               → pore pressure at (x, base_y) (kPa)
    ru_at(x, base_y, gamma, h)    → r_u at the point (dimensionless)

    Reference:
        Bishop & Morgenstern (1960). Stability coefficients for earth
        slopes. Géotechnique 10(4), 129–150.
    """

    points  : list   # list of (float, float) — (x, y) in metres
    gamma_w : float = GAMMA_W

    def __post_init__(self) -> None:
        if len(self.points) < 2:
            raise ValueError(
                f"PhreaticSurface requires ≥ 2 points, got {len(self.points)}"
            )
        xs = [p[0] for p in self.points]
        for i in range(len(xs) - 1):
            if xs[i + 1] <= xs[i]:
                raise ValueError(
                    f"PhreaticSurface x-values must be strictly increasing; "
                    f"got {xs[i]:.4f} then {xs[i+1]:.4f} at index {i}"
                )
        if self.gamma_w <= 0.0:
            raise ValueError(f"gamma_w must be > 0, got {self.gamma_w}")

    # ── Geometry ─────────────────────────────────────────────────────────

    @property
    def x_min(self) -> float:
        return self.points[0][0]

    @property
    def x_max(self) -> float:
        return self.points[-1][0]

    def y_at(self, x: float) -> float:
        """
        Interpolate phreatic elevation at position x (m).

        Outside the defined range the surface is extrapolated as constant
        (horizontal extension from the nearest boundary node).

        :param x: Horizontal position (m).
        :return:  Phreatic elevation y (m).
        """
        pts = self.points
        # Clamp x to defined range (conservative horizontal extension)
        if x <= pts[0][0]:
            return pts[0][1]
        if x >= pts[-1][0]:
            return pts[-1][1]
        # Linear interpolation in the interval containing x
        for i in range(len(pts) - 1):
            x0, y0 = pts[i]
            x1, y1 = pts[i + 1]
            if x0 <= x <= x1:
                t = (x - x0) / (x1 - x0)
                return y0 + t * (y1 - y0)
        # Should never reach here (covered by clamp above)
        return pts[-1][1]  # pragma: no cover

    # ── Pore pressure ─────────────────────────────────────────────────────

    def u_at(self, x: float, base_y: float) -> float:
        """
        Pore water pressure at position (x, base_y).

        u = γ_w × max(0,  y_ph(x) − base_y)

        Reference:
            Bishop & Morgenstern (1960), eq. (1).

        :param x      : Horizontal position (m).
        :param base_y : Elevation of the point (m) — e.g. slip circle base.
        :return: Pore pressure u (kPa).  Always ≥ 0.
        """
        return pore_pressure_from_phreatic(self.y_at(x), base_y, self.gamma_w)

    def ru_at(
        self,
        x      : float,
        base_y : float,
        gamma  : float,
        h_soil : float,
    ) -> float:
        """
        Pore pressure ratio r_u at position (x, base_y).

        r_u = u(x, base_y) / (γ · h_soil)

        Reference:
            Bishop & Morgenstern (1960), §3.

        :param x      : Horizontal position (m).
        :param base_y : Elevation of the slip surface at x (m).
        :param gamma  : Bulk unit weight of soil above the point (kN/m³).
        :param h_soil : Height of soil above the slip surface at x (m).
        :return: r_u (dimensionless).
        """
        u = self.u_at(x, base_y)
        return ru_at_point(u, gamma, h_soil)

    # ── Representation ───────────────────────────────────────────────────

    def __repr__(self) -> str:
        return (
            f"PhreaticSurface({len(self.points)} nodes, "
            f"x=[{self.x_min:.2f}, {self.x_max:.2f}] m, "
            f"y=[{self.points[0][1]:.2f}, {self.points[-1][1]:.2f}] m)"
        )
