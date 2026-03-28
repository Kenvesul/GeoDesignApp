"""
wall_geometry.py – Retaining wall geometry data model.

Defines a cantilever, L-wall, or counterfort retaining wall by its
cross-sectional dimensions.  All arithmetic is confined to simple
derived properties (areas, centroids, weights); no geotechnical
calculations are performed here.

Wall types supported
--------------------
    'cantilever'   Standard reinforced-concrete cantilever wall.  Stem acts
                   as a vertical cantilever fixed at the base slab.
    'L-wall'       Inverted-T / L-wall.  Geometry identical to cantilever;
                   wall_type is a label used for report generation and to
                   signal that b_toe ≈ 0 is intentional.
    'counterfort'  Counterfort (or buttressed) wall.  Vertical counterforts
                   are cast monolithically with the stem and base slab at
                   regular spacing, stiffening the stem.  The stem spans
                   horizontally between counterforts as a propped slab.
                   For overall stability (sliding/overturning/bearing) the
                   analysis is the same as cantilever but includes the
                   additional concrete weight of the counterforts.

Shear key
---------
    A shear key is a downward projection from the underside of the base
    slab, cast in mass or reinforced concrete.  It develops passive earth
    pressure on its leading face, supplementing the base sliding resistance.
    Modelled by shear_key_depth (m) and shear_key_width (m).

Reference:
    Craig's Soil Mechanics, 9th ed., §11.2–11.3 (wall types & analysis).
    Eurocode 7 – EN 1997-1:2004, §9 (Retaining Structures).
    Bond & Harris – Decoding Eurocode 7, Ch.14.

Sign conventions & geometry layout (plan view, looking along wall):

    ← Toe →|←── Stem ──→|←────── Heel ───────→
    ┌───────┤            ├────────────────────┐  ← top of base slab
    │       │    STEM    │                    │
    │  TOE  │  (taper)   │   RETAINED SOIL    │
    │       │            │   ABOVE HEEL       │
    └───────┴────────────┴────────────────────┘
    ^       ^            ^                    ^
    toe     b_toe        b_toe+t_stem_base    b_base

    Optional shear key below base slab (at or near the toe):
    ╔═══════════════════════════════════════════╗ ← base slab soffit
                │shear│
                │ key │  ← depth = shear_key_depth
                └─────┘  ← key tip

    Moments are computed about the TOE (leftmost edge of base).

Units:
    All lengths in metres (m).  Weights in kN/m (per unit run of wall).
    Angles in degrees (°).
"""

import math
from dataclasses import dataclass, field


# ============================================================
#  Constants
# ============================================================

GAMMA_CONCRETE : float = 24.0   # Reinforced concrete unit weight (kN/m³)
GAMMA_W        : float = 9.81   # Unit weight of water (kN/m³)


# ============================================================
#  RetainingWall dataclass
# ============================================================

@dataclass
class RetainingWall:
    """
    Cross-sectional geometry of a cantilever, L-wall, or counterfort
    retaining wall.

    The stem may be uniformly thick or tapered (t_stem_base > t_stem_top).
    Optional shear key and counterfort geometry are supported.

    Required attributes
    -------------------
    h_wall         : Total wall height from top of base slab to wall crest (m).
    b_base         : Total base slab width (m).  b_toe + t_stem_base + b_heel.
    b_toe          : Toe projection – distance from front face of stem to
                     front edge of base (m).
    t_stem_base    : Stem thickness at the base (m).
    t_stem_top     : Stem thickness at the top (m).  May equal t_stem_base.
    t_base         : Base slab thickness (m).

    Optional geometry attributes
    ----------------------------
    gamma_concrete      : Concrete unit weight γ_c (kN/m³).  Default 24.0.
    delta_wall          : Wall friction angle δ (degrees) for Coulomb Ka.
                          Zero → Rankine (smooth wall).  Default 0.0.
    alpha_wall          : Angle of wall back face from horizontal (degrees).
                          90° = vertical wall.  Default 90.0.
    beta_backfill       : Backfill surface inclination (degrees from horizontal).
                          Zero = horizontal backfill.  Default 0.0.
    delta_base          : Base friction angle δ_b (degrees).
                          If None, wall_analysis uses ⅔φ'_found automatically.
    wall_type           : Wall structural form.  One of:
                              'cantilever'  – standard RC cantilever (default).
                              'L-wall'      – inverted-T / L-wall (b_toe ≈ 0).
                              'counterfort' – counterfort/buttressed wall.
    shear_key_depth     : Depth of shear key projection below base slab soffit (m).
                          Zero = no key.  Default 0.0.
    shear_key_width     : Thickness of shear key in the direction of sliding (m).
                          Must be > 0 if shear_key_depth > 0.  Default 0.0.
    counterfort_spacing : Centre-to-centre spacing of counterforts (m).
                          Required if wall_type == 'counterfort'.  Default 0.0.
    counterfort_thickness: Counterfort rib thickness (m).
                          Required if wall_type == 'counterfort'.  Default 0.0.

    Derived properties (computed, not stored)
    ------------------------------------------
    b_heel         : Heel projection = b_base - b_toe - t_stem_base (m).
    w_counterforts : Extra concrete weight of counterforts per unit run (kN/m).
                     Zero for non-counterfort walls.
    """
    # ── Required geometry ─────────────────────────────────────────────────
    h_wall         : float
    b_base         : float
    b_toe          : float
    t_stem_base    : float
    t_stem_top     : float
    t_base         : float
    # ── Optional ──────────────────────────────────────────────────────────
    gamma_concrete       : float        = GAMMA_CONCRETE
    delta_wall           : float        = 0.0
    alpha_wall           : float        = 90.0
    beta_backfill        : float        = 0.0
    delta_base           : float | None = None
    wall_type            : str          = 'cantilever'
    shear_key_depth      : float        = 0.0
    shear_key_width      : float        = 0.0
    counterfort_spacing  : float        = 0.0
    counterfort_thickness: float        = 0.0

    _VALID_WALL_TYPES = ('cantilever', 'L-wall', 'counterfort')

    def __post_init__(self):
        # ── Geometry validation ───────────────────────────────────────────
        if self.h_wall <= 0:
            raise ValueError(f"h_wall must be > 0, got {self.h_wall}")
        if self.b_base <= 0:
            raise ValueError(f"b_base must be > 0, got {self.b_base}")
        if self.b_toe < 0:
            raise ValueError(f"b_toe must be ≥ 0, got {self.b_toe}")
        if self.t_stem_base <= 0:
            raise ValueError(f"t_stem_base must be > 0, got {self.t_stem_base}")
        if self.t_stem_top <= 0:
            raise ValueError(f"t_stem_top must be > 0, got {self.t_stem_top}")
        if self.t_base <= 0:
            raise ValueError(f"t_base must be > 0, got {self.t_base}")
        if self.gamma_concrete <= 0:
            raise ValueError(f"gamma_concrete must be > 0, got {self.gamma_concrete}")
        if not (0.0 <= self.delta_wall < 90.0):
            raise ValueError(f"delta_wall must be in [0, 90), got {self.delta_wall}")
        if not (45.0 < self.alpha_wall <= 90.0):
            raise ValueError(f"alpha_wall must be in (45, 90], got {self.alpha_wall}")
        if not (-30.0 <= self.beta_backfill < 90.0):
            raise ValueError(f"beta_backfill must be in [-30, 90), got {self.beta_backfill}")
        if self.wall_type not in self._VALID_WALL_TYPES:
            raise ValueError(
                f"wall_type must be one of {self._VALID_WALL_TYPES}, got '{self.wall_type}'"
            )
        # ── Shear key ─────────────────────────────────────────────────────
        if self.shear_key_depth < 0:
            raise ValueError(f"shear_key_depth must be >= 0, got {self.shear_key_depth}")
        if self.shear_key_depth > 0 and self.shear_key_width <= 0:
            raise ValueError(
                "shear_key_width must be > 0 when shear_key_depth > 0, "
                f"got {self.shear_key_width}"
            )
        # ── Counterfort ───────────────────────────────────────────────────
        if self.wall_type == 'counterfort':
            if self.counterfort_spacing <= 0:
                raise ValueError(
                    f"counterfort_spacing must be > 0 for counterfort wall type, "
                    f"got {self.counterfort_spacing}"
                )
            if self.counterfort_thickness <= 0:
                raise ValueError(
                    f"counterfort_thickness must be > 0 for counterfort wall type, "
                    f"got {self.counterfort_thickness}"
                )
        # ── Base geometry ─────────────────────────────────────────────────
        b_heel_derived = self.b_base - self.b_toe - self.t_stem_base
        if b_heel_derived < 0:
            raise ValueError(
                f"Geometry inconsistency: b_toe ({self.b_toe}) + t_stem_base "
                f"({self.t_stem_base}) exceeds b_base ({self.b_base}).  "
                f"b_heel would be {b_heel_derived:.3f} m."
            )
        if self.t_base >= self.h_wall:
            raise ValueError(
                f"t_base ({self.t_base}) must be less than h_wall ({self.h_wall})."
            )

    # ── Derived dimensions ────────────────────────────────────────────────

    @property
    def h_stem(self) -> float:
        """Stem height = retained height above top of base slab (m)."""
        return self.h_wall

    @property
    def b_heel(self) -> float:
        """Heel projection behind the stem (m)."""
        return self.b_base - self.b_toe - self.t_stem_base

    @property
    def t_stem_mean(self) -> float:
        """Mean stem thickness (m) — used for weight and centroid estimates."""
        return (self.t_stem_top + self.t_stem_base) / 2.0

    # ── Component geometry (per unit run of wall, length = 1 m) ──────────

    @property
    def area_stem(self) -> float:
        """Cross-sectional area of the stem (m² per m run)."""
        return self.t_stem_mean * self.h_stem

    @property
    def area_base(self) -> float:
        """Cross-sectional area of the base slab (m² per m run)."""
        return self.b_base * self.t_base

    @property
    def x_stem_centroid(self) -> float:
        """
        Horizontal distance of stem centroid from TOE (m).

        For a trapezoidal stem (wider at base, narrower at top), the
        centroid lies closer to the wider (base) end.  This method uses
        the exact trapezoidal centroid formula measured from the front
        face of the stem, then shifts by b_toe.

        Formula (centroid of trapezoid measured from wider base edge):
            x̄ = (2·t_top + t_base) / (3·(t_top + t_base)) × t_base

        The centroid is then shifted right by b_toe (offset from toe).
        """
        t_b = self.t_stem_base
        t_t = self.t_stem_top
        # Centroid of trapezoid from the front (toe-side) face of stem
        x_from_stem_face = (2 * t_b + t_t) / (3 * (t_b + t_t)) * t_b
        return self.b_toe + x_from_stem_face

    @property
    def x_base_centroid(self) -> float:
        """Horizontal distance of base slab centroid from TOE (m)."""
        return self.b_base / 2.0

    @property
    def x_heel_soil_centroid(self) -> float:
        """
        Horizontal distance of the soil column above the heel from TOE (m).
        (The soil occupying the full b_heel width behind the stem.)
        """
        return self.b_toe + self.t_stem_base + self.b_heel / 2.0

    # ── Component weights (per unit run of wall) ──────────────────────────

    @property
    def w_stem(self) -> float:
        """Self-weight of the stem per unit run (kN/m)."""
        return self.gamma_concrete * self.area_stem

    @property
    def w_base(self) -> float:
        """Self-weight of the base slab per unit run (kN/m)."""
        return self.gamma_concrete * self.area_base

    @property
    def w_counterforts(self) -> float:
        """
        Concrete weight of counterforts per unit run of wall (kN/m).

        Counterforts are solid rectangular ribs spanning from the stem back
        face to the end of the heel slab and full wall height.

        Volume per metre run of wall:
            V_cf = (b_heel × h_wall × counterfort_thickness) / counterfort_spacing

        Returns 0.0 for non-counterfort wall types.

        Reference:
            Craig's Soil Mechanics, 9th ed., §11.3 (counterfort walls).
        """
        if self.wall_type != 'counterfort' or self.counterfort_spacing <= 0:
            return 0.0
        vol_per_m = (
            self.b_heel * self.h_wall * self.counterfort_thickness
        ) / self.counterfort_spacing
        return self.gamma_concrete * vol_per_m

    def __repr__(self) -> str:
        return (
            f"RetainingWall("
            f"type={self.wall_type}, "
            f"h_wall={self.h_wall}m, b_base={self.b_base}m, "
            f"b_toe={self.b_toe}m, b_heel={self.b_heel:.3f}m, "
            f"t_stem_base={self.t_stem_base}m, t_stem_top={self.t_stem_top}m, "
            f"t_base={self.t_base}m"
            + (f", shear_key={self.shear_key_depth}m" if self.shear_key_depth > 0 else "")
            + (f", cf_s={self.counterfort_spacing}m" if self.wall_type == 'counterfort' else "")
            + ")"
        )
