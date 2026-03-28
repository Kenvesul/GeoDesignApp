"""
foundation.py -- Foundation geometry data model.

Pure data container for strip, pad (square/rectangular), and raft foundations.
No geotechnical calculations are performed here; all bearing capacity and
settlement arithmetic lives in core/.

Reference:
    Eurocode 7 -- EN 1997-1:2004, Section 6 (Spread foundations).
    Annex D (Bearing resistance -- analytical method).
    Craig's Soil Mechanics, 9th ed., Chapter 8 (Spread foundations).

Sign conventions:
    B = width of foundation, in the direction of bending / minor axis (m).
    L = length of foundation, perpendicular to B (m).
        L = None denotes an infinite strip (all results per unit run, kN/m).
    e_B, e_L = load eccentricities from foundation centreline (m).
        Positive eccentricity shifts resultant toward the +B or +L edge.
    B_eff = B - 2*e_B,  L_eff = L - 2*e_L  (EC7 Annex D, effective dimensions).
    Df = depth of embedment below the lowest adjacent ground level (m).
    alpha = base inclination from horizontal (degrees, positive tilts downward
            toward +B direction).

Units:
    All lengths in metres (m).  Angles in degrees.  Weights in kN, kN/m.
"""

from __future__ import annotations
import math
from dataclasses import dataclass


# ============================================================
#  Foundation dataclass
# ============================================================

@dataclass
class Foundation:
    """
    Cross-sectional geometry of a spread foundation (strip, pad, or raft).

    Attributes
    ----------
    B              : Foundation width (m).  Must be > 0.
    Df             : Depth of embedment below ground (m).  Must be >= 0.
    L              : Foundation length (m).  None = infinite strip (results per m run).
    e_B            : Load eccentricity in B-direction from centroid (m).  Default 0.
    e_L            : Load eccentricity in L-direction from centroid (m).  Default 0.
    alpha          : Base inclination from horizontal (degrees).  Default 0 (level).
    gamma_concrete : Concrete unit weight (kN/m3).  Default 24.0.

    Derived properties (computed, not stored)
    ------------------------------------------
    B_eff      : Effective width  = B - 2*e_B  (EC7 Annex D §D.3).
    L_eff      : Effective length = L - 2*e_L  (None for strip).
    A_eff      : Effective area per unit run (strip) or total area (pad/raft).
    aspect     : B_eff / L_eff.  0 for strip (used in shape factor formulae as B/L=0).
    is_strip   : True when L is None.
    """
    B              : float
    Df             : float
    L              : float | None = None   # None = infinite strip
    e_B            : float        = 0.0
    e_L            : float        = 0.0
    alpha          : float        = 0.0
    gamma_concrete : float        = 24.0

    def __post_init__(self):
        if self.B <= 0:
            raise ValueError(f"B must be > 0, got {self.B}")
        if self.Df < 0:
            raise ValueError(f"Df must be >= 0, got {self.Df}")
        if self.L is not None:
            if self.L <= 0:
                raise ValueError(f"L must be > 0 (or None for strip), got {self.L}")
            if self.L < self.B:
                raise ValueError(
                    f"L ({self.L}) must be >= B ({self.B}).  "
                    "By convention B is the shorter dimension."
                )
        if abs(self.e_B) >= self.B / 2.0:
            raise ValueError(
                f"Eccentricity e_B ({self.e_B}) must be < B/2 ({self.B/2}).  "
                "Resultant must lie within the base."
            )
        if self.L is not None and abs(self.e_L) >= self.L / 2.0:
            raise ValueError(
                f"Eccentricity e_L ({self.e_L}) must be < L/2 ({self.L/2})."
            )
        if not (-30.0 <= self.alpha <= 30.0):
            raise ValueError(
                f"Base inclination alpha must be in [-30, 30] degrees, got {self.alpha}"
            )

    # ── Effective dimensions  (EC7 Annex D §D.3) ──────────────────────────

    @property
    def B_eff(self) -> float:
        """Effective foundation width B' = B - 2*e_B  (m)."""
        return self.B - 2.0 * self.e_B

    @property
    def L_eff(self) -> float | None:
        """Effective foundation length L' = L - 2*e_L  (m).  None for strip."""
        if self.L is None:
            return None
        return self.L - 2.0 * self.e_L

    @property
    def A_eff(self) -> float:
        """
        Effective foundation area (m^2/m for strip, m^2 for finite).

        For a strip, A_eff = B_eff (per unit run, dimensionally m^2/m = m).
        """
        if self.L is None:
            return self.B_eff
        return self.B_eff * self.L_eff

    @property
    def aspect(self) -> float:
        """
        Effective aspect ratio B_eff / L_eff.

        Returns 0.0 for a strip (used in shape factor formula as B/L -> 0).
        Returns 1.0 for a square (B == L).
        """
        if self.L is None or self.L_eff == 0:
            return 0.0
        return self.B_eff / self.L_eff

    @property
    def is_strip(self) -> bool:
        """True if L is None (infinite strip foundation)."""
        return self.L is None

    # ── Convenience constructors ──────────────────────────────────────────

    @classmethod
    def strip(cls, B: float, Df: float, **kwargs) -> "Foundation":
        """
        Creates an infinite strip foundation (L = None).

        :param B:  Strip width (m).
        :param Df: Embedment depth (m).
        :return:   Foundation instance with L = None.
        """
        return cls(B=B, Df=Df, L=None, **kwargs)

    @classmethod
    def square(cls, B: float, Df: float, **kwargs) -> "Foundation":
        """
        Creates a square pad foundation (L = B).

        :param B:  Side length (m).
        :param Df: Embedment depth (m).
        :return:   Foundation instance with L = B.
        """
        return cls(B=B, Df=Df, L=B, **kwargs)

    @classmethod
    def pad(cls, B: float, L: float, Df: float, **kwargs) -> "Foundation":
        """
        Creates a rectangular pad foundation.

        :param B:  Short side (m).
        :param L:  Long side (m).  Must be >= B.
        :param Df: Embedment depth (m).
        :return:   Foundation instance.
        """
        return cls(B=B, Df=Df, L=L, **kwargs)

    # ── Representation ────────────────────────────────────────────────────

    def __repr__(self) -> str:
        shape = "Strip" if self.is_strip else ("Square" if self.L == self.B else "Pad")
        dims  = f"B={self.B}m" if self.is_strip else f"B={self.B}m x L={self.L}m"
        return f"Foundation({shape}, {dims}, Df={self.Df}m)"
