"""
surcharge.py – Surcharge load data models for retaining wall and bearing analysis.

Pure data containers only.  No geotechnical calculations are performed here.
The conversion of surcharge geometry into horizontal wall pressures is the
responsibility of core/wall_analysis.py.

Reference:
    Craig's Soil Mechanics, 9th ed., §11.3 (Surcharge loads on retained soil).
    Terzaghi (1954) – Theoretical Soil Mechanics, lateral stress from point/line loads.
    Eurocode 7 – EN 1997-1:2004, §9.3 (Actions on retaining structures).

Sign conventions:
    All distances measured horizontally from the back face of the wall stem.
    Positive x -> away from wall, into the backfill.
    Surcharge intensities are always positive (compressive).

Units:
    Lengths (m), pressures (kPa), line loads (kN/m), point loads (kN).
"""

from dataclasses import dataclass


# ============================================================
#  Uniform Surcharge  (most common case)
# ============================================================

@dataclass
class UniformSurcharge:
    """
    Uniformly distributed load applied over the entire backfill surface.

    This is the standard 'traffic surcharge' or 'live load' assumed to
    extend infinitely behind the wall.

    Attributes
    ----------
    q : Intensity (kPa).  Typical values: 5 kPa (lightly loaded), 10-25 kPa (roads).
    """
    q : float

    def __post_init__(self):
        if self.q < 0:
            raise ValueError(f"Surcharge intensity q must be >= 0, got {self.q}")

    def __repr__(self) -> str:
        return f"UniformSurcharge(q={self.q} kPa)"


# ============================================================
#  Line Surcharge  (Boussinesq / image method)
# ============================================================

@dataclass
class LineSurcharge:
    """
    Infinite line load Q (kN/m run) parallel to the wall face, at horizontal
    distance x_s from the back face of the stem.

    Lateral pressure on a rigid wall (Terzaghi, 1954 / Boussinesq image method):
        Exact formula:
            sigma_h(z) = (2*Q/pi) * m^2*n / (m^2 + n^2)^2
        where m = x_s/H, n = z/H, H = wall height, z = depth below top of wall.

    Reference:
        Terzaghi (1954), adapted in Craig S11.3.
        Bowles, Foundation Analysis and Design, 5th ed., S3.12.

    Attributes
    ----------
    Q   : Line load intensity (kN/m run perpendicular to wall cross-section).
    x_s : Horizontal distance from back face of stem to line load (m).  Must be > 0.
    """
    Q   : float
    x_s : float

    def __post_init__(self):
        if self.Q < 0:
            raise ValueError(f"Line load Q must be >= 0, got {self.Q}")
        if self.x_s <= 0:
            raise ValueError(f"x_s must be > 0, got {self.x_s}")

    def __repr__(self) -> str:
        return f"LineSurcharge(Q={self.Q} kN/m, x_s={self.x_s} m)"


# ============================================================
#  Strip Surcharge  (Boussinesq integration)
# ============================================================

@dataclass
class StripSurcharge:
    """
    Uniform strip load q (kPa) applied over a finite width behind the wall.

    Computed via Boussinesq integration; lateral pressure on a rigid wall
    (method of images):
        sigma_h(z) = q/pi * (beta2 - beta1 + sin(beta2)*cos(beta2+2*delta)
                                           - sin(beta1)*cos(beta1+2*delta))
    where beta1, beta2 are angles to the near/far edges from the point at depth z.

    Reference:
        Das, Principles of Geotechnical Engineering, 9th ed., S11.10.
        Craig's Soil Mechanics, 9th ed., S11.3.

    Attributes
    ----------
    q      : Strip load intensity (kPa).
    x_near : Distance from back face of stem to near edge of strip (m).  >= 0.
    x_far  : Distance from back face of stem to far edge of strip (m).  > x_near.
    """
    q      : float
    x_near : float
    x_far  : float

    def __post_init__(self):
        if self.q < 0:
            raise ValueError(f"Strip load q must be >= 0, got {self.q}")
        if self.x_near < 0:
            raise ValueError(f"x_near must be >= 0, got {self.x_near}")
        if self.x_far <= self.x_near:
            raise ValueError(
                f"x_far ({self.x_far}) must be > x_near ({self.x_near})"
            )

    @property
    def width(self) -> float:
        """Width of the strip load (m)."""
        return self.x_far - self.x_near

    def __repr__(self) -> str:
        return (
            f"StripSurcharge(q={self.q} kPa, "
            f"x_near={self.x_near} m, x_far={self.x_far} m)"
        )
