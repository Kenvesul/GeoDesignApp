"""
sheet_pile.py — SheetPile model dataclass.

Defines the geometric and structural properties of a sheet pile or embedded
retaining wall needed for:
    • Free-earth support method (Blum 1931 / Craig §12.2) — Sprint 10.
    • Fixed-earth support method (Craig §12.3)             — Sprint 11.
    • Rowe's moment reduction (Rowe, 1952)                 — Sprint 11.

Geometry convention (positive downward from excavation surface):
    z = 0         : excavation level (dredge level / formation level).
    z < 0         : retained side above excavation (−z_retained = retained height).
    z > 0         : embedded below excavation level.
    z_prop        : depth to prop/anchor from the TOP of the pile (m); negative
                    means the prop is above excavation level (typical).

            ┌─────────────────────────┐
            │   Retained side (z < 0) │
     top ─► │                         │ ◄─ z = −h_retained
            │         PROP ──────────►│ ◄─ z_prop  (depth from top, may be 0)
            │                         │
            ├─────────────────────────┤ ◄─ z = 0  (excavation level)
            │                         │
            │   Embedded (z > 0)      │
            │                         │
    base ─► │─────────────────────────│ ◄─ z = d_embed

    Total pile length = h_retained + d_embed

EC7 references:
    EN 1997-1:2004, §9  — Design of retaining structures (general).
    EN 1997-1:2004, §9.7 — Embedded walls (sheet piles, contiguous bored piles).

Other references:
    Blum, H. (1931). Einspannungsverhältnisse bei Bohlwerken. Wilhelm Ernst
        & Sohn, Berlin. — free-earth support embedment formula.
    Craig's Soil Mechanics, 9th ed., §12 (Knappett & Craig).
    BS 8002:2015 — Earth retaining structures.
    Bond, A. & Harris, A. (2008). Decoding Eurocode 7. Taylor & Francis.

Units: metres (lengths), kN/m and kN·m/m (forces and moments).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ── Valid option sets ─────────────────────────────────────────────────────────

_VALID_SUPPORT  = frozenset({"free", "fixed", "propped"})
_VALID_SECTIONS = frozenset({"U", "Z", "H", "flat"})


# ── SheetPile dataclass ───────────────────────────────────────────────────────

@dataclass
class SheetPile:
    """
    Geometric and structural properties of a sheet pile or embedded wall.

    Parameters
    ----------
    h_retained : float
        Retained height — vertical distance from the top of the pile (or from
        the top of the retained soil if different) to the excavation level (m).
        Must be > 0.
        Reference: Craig §12.1.

    d_embed : float
        Embedment depth below the excavation (dredge) level (m).
        For a free-earth analysis this is a DESIGN VARIABLE; the engine
        computes the minimum d_embed required for moment equilibrium.
        For analysis of an existing pile, supply the actual d_embed.
        Must be ≥ 0.

    support : str
        Wall support condition:
            'free'     — free-earth support (cantilevered or propped).
            'fixed'    — fixed-earth support (wall fixed in the embedded soil).
            'propped'  — propped/anchored wall (free-earth method with prop).
        Default: 'free'.
        Reference: Craig §12.2 (free), §12.3 (fixed).

    z_prop : float | None
        Depth of the prop or anchor from the TOP of the pile (m).
        Convention: z_prop ≤ 0 means the prop is above the excavation level
        (e.g. z_prop = −h_retained for a prop at the top of the retained height).
        Set to None if the wall is unpropped (cantilever) or fixed.
        Default: None.

    F_prop_k : float | None
        Characteristic prop/anchor force (kN/m run).  Set after analysis
        when the engine solves for the prop force.  None until computed.
        Default: None.

    section : str
        Sheet pile section type: 'U', 'Z', 'H', or 'flat'.
        Used for section modulus lookup in Sprint 11 (structural check).
        Default: 'U'.

    S_el : float | None
        Elastic section modulus (cm³/m run).  Required for bending stress
        checks in Sprint 11.  None if not yet supplied.
        Default: None.

    label : str
        Human-readable name for reports.  Default: 'Sheet Pile'.

    Derived properties
    ------------------
    total_length : float
        h_retained + d_embed  (m).

    z_excavation : float
        Always 0.0 (excavation level datum — kept for clarity in callers).

    z_toe : float
        Depth of the toe below the excavation level = d_embed (m).

    Notes
    -----
    The model carries *no* soil or pore-pressure data — those live in the
    Soil dataclass.  The engine (core/sheet_pile_analysis.py, Sprint 10)
    consumes SheetPile + Soil objects and returns result dataclasses.
    """

    h_retained : float
    d_embed    : float         = 0.0
    support    : str           = "free"
    z_prop     : Optional[float] = None
    F_prop_k   : Optional[float] = None
    section    : str           = "U"
    S_el       : Optional[float] = None
    label      : str           = "Sheet Pile"

    # ── Validation ────────────────────────────────────────────────────────

    def __post_init__(self) -> None:
        if self.h_retained <= 0.0:
            raise ValueError(
                f"h_retained must be > 0, got {self.h_retained}"
            )
        if self.d_embed < 0.0:
            raise ValueError(
                f"d_embed must be ≥ 0, got {self.d_embed}"
            )
        if self.support not in _VALID_SUPPORT:
            raise ValueError(
                f"support must be one of {sorted(_VALID_SUPPORT)}, "
                f"got {self.support!r}"
            )
        if self.section not in _VALID_SECTIONS:
            raise ValueError(
                f"section must be one of {sorted(_VALID_SECTIONS)}, "
                f"got {self.section!r}"
            )
        if self.S_el is not None and self.S_el <= 0.0:
            raise ValueError(
                f"S_el must be > 0 if supplied, got {self.S_el}"
            )
        if (self.support == "propped") and (self.z_prop is None):
            raise ValueError(
                "z_prop must be supplied when support='propped'."
            )
        if self.z_prop is not None:
            # Prop must be above the pile toe
            z_top = -self.h_retained
            if not (z_top - 1e-9 <= self.z_prop <= self.d_embed + 1e-9):
                raise ValueError(
                    f"z_prop ({self.z_prop:.3f}) must be in the range "
                    f"[{z_top:.3f}, {self.d_embed:.3f}] m "
                    f"(top of pile to pile toe)."
                )

    # ── Derived properties ────────────────────────────────────────────────

    @property
    def total_length(self) -> float:
        """Total pile length = h_retained + d_embed (m)."""
        return self.h_retained + self.d_embed

    @property
    def z_excavation(self) -> float:
        """Excavation level datum (always 0.0 m)."""
        return 0.0

    @property
    def z_toe(self) -> float:
        """Depth of pile toe below excavation level (= d_embed, m)."""
        return self.d_embed

    @property
    def is_propped(self) -> bool:
        """True if the wall has a prop or anchor."""
        return self.support == "propped" and self.z_prop is not None

    @property
    def is_cantilevered(self) -> bool:
        """True if the wall has no prop (free cantilever)."""
        return self.support == "free" and self.z_prop is None

    # ── String representation ─────────────────────────────────────────────

    def __repr__(self) -> str:
        prop_str = f", z_prop={self.z_prop:.2f}m" if self.z_prop is not None else ""
        return (
            f"SheetPile({self.label!r}, h={self.h_retained:.2f}m, "
            f"d={self.d_embed:.2f}m, L={self.total_length:.2f}m, "
            f"support={self.support!r}{prop_str})"
        )
