"""
pile.py – Pile geometry data model.

Defines a single pile by its cross-sectional dimensions, installation
method, and material.  All arithmetic is confined to simple derived
properties (areas, perimeter, weight); no capacity calculations are
performed here.

Pile types supported
--------------------
    'driven'    Displacement pile installed by impact or vibration.
                High Ks; full mobilisation of lateral earth pressure.
    'bored'     Non-displacement (replacement) pile.  Reduced Ks;
                stress-relief during augering.
    'CFA'       Continuous Flight Auger pile.  Intermediate Ks;
                auger replaced by grout as drilling proceeds.

Reference:
    Eurocode 7 – EN 1997-1:2004, §7 (Pile Foundations).
    Craig's Soil Mechanics, 9th ed., §11.
    Das, B.M. (2019). Principles of Geotechnical Engineering, §11.

Units:
    All lengths in metres (m).
    Weights in kN (per pile).
    Areas in m².
"""

import math
from dataclasses import dataclass, field


# ── Default constants ─────────────────────────────────────────────────────────

GAMMA_CONCRETE : float = 24.0   # Reinforced concrete unit weight (kN/m³)

# Supported pile types
_VALID_PILE_TYPES : tuple[str, ...] = ('driven', 'bored', 'CFA')
_VALID_MATERIALS  : tuple[str, ...] = ('concrete', 'steel')


# ── PileSoilLayer ─────────────────────────────────────────────────────────────

@dataclass
class PileSoilLayer:
    """
    Represents a single stratum in the soil profile along the pile shaft.

    Each layer is characterised by its thickness, unit weight, strength
    parameters, and soil type.  The soil type governs which capacity
    method is applied:
        'clay'  → alpha method (Tomlinson 1970, undrained).
        'sand'  → beta  method (Meyerhof 1976, drained).

    Attributes
    ----------
    thickness    : Layer thickness (m).  Must be > 0.
    gamma        : Total unit weight γ (kN/m³).
    phi_k        : Characteristic friction angle φ'_k (degrees).
                   Set to 0 for clay (undrained analysis).
    c_k          : Characteristic undrained shear strength c_u (kPa) for
                   clay, or characteristic drained cohesion c'_k for sand.
                   Set to 0 for purely frictional sand layers.
    soil_type    : 'sand' or 'clay'.
    K_s          : Lateral earth pressure coefficient for beta method.
                   If None, the default for the pile type is applied
                   automatically by the capacity engine.
    delta_factor : Interface friction ratio δ/φ'_k (-).
                   Default 2/3 (rough concrete-to-soil, Craig §11).
    label        : Optional descriptive name for this layer.

    Reference:
        Tomlinson (1970) – alpha method for piles in clay.
        Meyerhof (1976)  – beta method for piles in sand.
        Craig §11.1–11.2 (pile shaft resistance methods).
    """
    thickness    : float
    gamma        : float
    phi_k        : float
    c_k          : float
    soil_type    : str
    K_s          : float | None = None
    delta_factor : float = 2.0 / 3.0
    label        : str   = ""

    def __post_init__(self):
        if self.thickness <= 0:
            raise ValueError(f"thickness must be > 0, got {self.thickness}")
        if self.gamma <= 0:
            raise ValueError(f"gamma must be > 0, got {self.gamma}")
        if not (0.0 <= self.phi_k < 90.0):
            raise ValueError(f"phi_k must be in [0, 90), got {self.phi_k}")
        if self.c_k < 0:
            raise ValueError(f"c_k must be >= 0, got {self.c_k}")
        if self.soil_type not in ('sand', 'clay'):
            raise ValueError(
                f"soil_type must be 'sand' or 'clay', got {self.soil_type!r}"
            )
        if self.K_s is not None and self.K_s <= 0:
            raise ValueError(f"K_s must be > 0 if specified, got {self.K_s}")
        if not (0.0 < self.delta_factor <= 1.0):
            raise ValueError(
                f"delta_factor must be in (0, 1], got {self.delta_factor}"
            )
        if self.soil_type == 'sand' and self.phi_k == 0.0:
            raise ValueError(
                "phi_k must be > 0 for soil_type='sand' (beta method requires φ' > 0)"
            )
        if self.soil_type == 'clay' and self.c_k == 0.0:
            raise ValueError(
                "c_k (undrained shear strength) must be > 0 for soil_type='clay'"
            )


# ── Pile dataclass ────────────────────────────────────────────────────────────

@dataclass
class Pile:
    """
    Geometry and installation properties of a single axially-loaded pile.

    Required attributes
    -------------------
    pile_type    : Installation method: 'driven', 'bored', or 'CFA'.
    diameter     : Pile shaft diameter D (m).  For H-piles this is the
                   equivalent square side (not supported in this version;
                   use circular equivalent).
    length       : Pile embedment length L (m) — measured from finished
                   ground level (or top of pile cap) to pile tip.

    Optional attributes
    -------------------
    gamma_concrete : Concrete (or grout) unit weight γ_c (kN/m³).
                     Default 24.0.  For steel piles set to the weighted
                     average of the composite section.
    material       : 'concrete' or 'steel'.  Governs the default interface
                     friction factor δ/φ' in the beta method.
                     Concrete → δ/φ' = 2/3 (rough surface).
                     Steel    → δ/φ' = 1/2 (smooth surface).

    Derived properties (computed, not stored)
    ------------------------------------------
    area_base   : Tip (base) cross-sectional area A_b = π D²/4 (m²).
    perimeter   : Shaft perimeter p = π D (m).
    shaft_area  : Lateral shaft area A_s = p × L (m²).
    volume      : Volume of pile V = A_b × L (m³).
    self_weight : Self-weight W_pile = V × γ_c (kN).
    """
    pile_type      : str
    diameter       : float
    length         : float
    gamma_concrete : float = GAMMA_CONCRETE
    material       : str   = 'concrete'

    def __post_init__(self):
        if self.pile_type not in _VALID_PILE_TYPES:
            raise ValueError(
                f"pile_type must be one of {_VALID_PILE_TYPES}, got {self.pile_type!r}"
            )
        if self.diameter <= 0:
            raise ValueError(f"diameter must be > 0, got {self.diameter}")
        if self.length <= 0:
            raise ValueError(f"length must be > 0, got {self.length}")
        if self.gamma_concrete <= 0:
            raise ValueError(f"gamma_concrete must be > 0, got {self.gamma_concrete}")
        if self.material not in _VALID_MATERIALS:
            raise ValueError(
                f"material must be one of {_VALID_MATERIALS}, got {self.material!r}"
            )

    # ── Derived geometry ──────────────────────────────────────────────────

    @property
    def area_base(self) -> float:
        """Tip cross-sectional area A_b = π D² / 4 (m²)."""
        return math.pi * self.diameter ** 2 / 4.0

    @property
    def perimeter(self) -> float:
        """Shaft perimeter p = π D (m)."""
        return math.pi * self.diameter

    @property
    def shaft_area(self) -> float:
        """Total lateral shaft area A_s = p × L (m²)."""
        return self.perimeter * self.length

    @property
    def volume(self) -> float:
        """Volume of concrete/grout V = A_b × L (m³)."""
        return self.area_base * self.length

    @property
    def self_weight(self) -> float:
        """Pile self-weight W = V × γ_c (kN)."""
        return self.volume * self.gamma_concrete

    @property
    def slenderness(self) -> float:
        """L/D slenderness ratio (dimensionless).  L/D < 4 triggers warning in capacity engine."""
        return self.length / self.diameter

    @property
    def default_delta_factor(self) -> float:
        """
        Default interface friction ratio δ/φ' based on material.

        Reference: Craig §11.2.
            Concrete (rough) → 2/3
            Steel   (smooth) → 1/2
        """
        return 2.0 / 3.0 if self.material == 'concrete' else 1.0 / 2.0

    def __repr__(self) -> str:
        return (
            f"Pile(type={self.pile_type!r}, D={self.diameter}m, "
            f"L={self.length}m, material={self.material!r})"
        )
