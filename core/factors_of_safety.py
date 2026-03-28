"""
factors_of_safety.py – EC7 Design Approach 1 (DA1) verification gate.

Applies Eurocode 7 Design Approach 1 to circular slope stability analysis.
DA1 requires TWO calculation combinations; the governing (lower FoS_d)
combination controls the design decision.

EC7 approach for overall slope stability (§11.5.1):
    The "material factoring approach" is used.  Partial factors γ_M are
    applied to the characteristic soil strength parameters to produce design
    values.  The analysis is then run with the factored (design) soil, and
    the result must satisfy FoS_design ≥ 1.0.  This is consistent with the
    fundamental EC7 requirement E_d ≤ R_d, expressed in terms of FoS as:

        FoS_d = R_d / E_d ≥ 1.0

    where both resistance and driving are evaluated using design values.

Combination summary (EC7 Tables A.3 / A.4):
    ┌──────────────┬───────────┬────────┬────────────────────────────┐
    │ Combination  │  Set      │  γ_φ   │  γ_c                       │
    ├──────────────┼───────────┼────────┼────────────────────────────┤
    │ DA1 – Comb 1 │  M1       │  1.00  │  1.00  (char. strength)    │
    │ DA1 – Comb 2 │  M2       │  1.25  │  1.25  (reduced strength)  │
    └──────────────┴───────────┴────────┴────────────────────────────┘

    Comb 1 with M1 uses characteristic strength → FoS_d(C1) = FoS_char.
    Comb 2 with M2 reduces strength → FoS_d(C2) is always lower.
    Comb 2 governs for GEO slope stability in virtually all practical cases.
    The software evaluates and reports both; the engineer signs off on both.

Pass criterion:
    Each combination independently passes if FoS_d ≥ 1.0.
    The overall verification passes only if BOTH combinations pass.

Reference:
    Eurocode 7 – EN 1997-1:2004, §2.4.7.3, §11.5, Tables A.3–A.4.
    Craig's Soil Mechanics, 9th ed., §9.6 (EC7 application to slopes).
    Bond & Harris – Decoding Eurocode 7, Chapter 12.

Units:
    All lengths in metres (m), stresses in kPa, angles in degrees.
    Partial factors are dimensionless.
"""

import math
from dataclasses import dataclass, field
from copy        import copy

from models.soil   import Soil
from models.geometry import SlopeGeometry
from core.search   import grid_search, SearchResult


# ============================================================
#  EC7 Partial factor constants  (EC7 Tables A.3 / A.4)
# ============================================================
#  M1 set – Combination 1 (A1+M1+R1)
M1_GAMMA_PHI : float = 1.00   # γ_φ  – friction angle partial factor
M1_GAMMA_C   : float = 1.00   # γ_c  – cohesion partial factor

#  M2 set – DA1-C2, DA3
M2_GAMMA_PHI : float = 1.25   # γ_φ
M2_GAMMA_C   : float = 1.25   # γ_c

#  R1 set – overall stability resistance (EC7 Table A.14)
R1_GAMMA_R   : float = 1.00

#  R2 set – overall stability resistance (EC7 Table A.14)
R2_GAMMA_R   : float = 1.10   # DA2 applies this to the characteristic FoS

#  R3 set – overall stability resistance (EC7 Table A.14)
R3_GAMMA_R   : float = 1.00   # same as R1 for overall stability

#  Minimum acceptable FoS_d (all DAs)
FOS_D_LIMIT  : float = 1.00   # E_d ≤ R_d  →  FoS_d ≥ 1.0


# ============================================================
#  CombinationResult – single combination output
# ============================================================

@dataclass
class CombinationResult:
    """
    Outcome of a single DA1 combination.

    Attributes
    ----------
    label          : 'DA1-C1' or 'DA1-C2'.
    gamma_phi      : Partial factor applied to tan φ'_k (–).
    gamma_c        : Partial factor applied to c'_k (–).
    phi_d          : Design friction angle φ'_d (degrees).
    c_d            : Design cohesion c'_d (kN/m²).
    search_result  : Full SearchResult from grid_search() with design soil.
    fos_d          : Design Factor of Safety = search_result.fos_min (–).
    passes         : True if fos_d ≥ FOS_D_LIMIT (1.0).
    """
    label         : str
    gamma_phi     : float
    gamma_c       : float
    phi_d         : float
    c_d           : float
    search_result : SearchResult
    fos_d         : float
    passes        : bool

    def summary_line(self) -> str:
        tick = '✅ PASS' if self.passes else '❌ FAIL'
        return (
            f"  {self.label}  γ_φ={self.gamma_phi:.2f}  γ_c={self.gamma_c:.2f}"
            f"  →  φ'_d={self.phi_d:.2f}°  c'_d={self.c_d:.3f} kPa"
            f"  |  FoS_d={self.fos_d:.4f}  {tick}"
        )


# ============================================================
#  DA2Result
# ============================================================

@dataclass
class DA2Result:
    """
    Outcome of the EC7 DA2 verification for slope stability.

    DA2 uses characteristic material strengths (M1 set) and applies
    a resistance factor γ_R = 1.10 (R2 set, EC7 Table A.14) post-search:
        FoS_d(DA2) = FoS_char / γ_R

    Pass criterion equivalent: FoS_char ≥ 1.10.

    Reference: Bond & Harris (2008). Decoding Eurocode 7, §14.3.

    Attributes
    ----------
    label    : 'DA2'.
    gamma_R  : Resistance partial factor (R2_GAMMA_R = 1.10).
    fos_char : Characteristic FoS (grid search with M1 factors).
    fos_d    : Design FoS = fos_char / gamma_R.
    passes   : True if fos_d ≥ FOS_D_LIMIT.
    """
    label    : str
    gamma_R  : float
    fos_char : float
    fos_d    : float
    passes   : bool

    def summary_line(self) -> str:
        tick = '✅ PASS' if self.passes else '❌ FAIL'
        return (
            f"  {self.label}  γ_R={self.gamma_R:.2f}  (M1 strengths)  "
            f"FoS_char={self.fos_char:.4f}  →  FoS_d={self.fos_d:.4f}  {tick}"
        )


# ============================================================
#  VerificationResult – DA1 + DA2 + DA3 output
# ============================================================

@dataclass
class VerificationResult:
    """
    Complete output of the EC7 slope stability verification (DA1 + DA2 + DA3).

    Attributes
    ----------
    soil_char  : Characteristic Soil passed by the caller.
    slope      : SlopeGeometry used.
    ru         : Pore pressure ratio rᵤ used.
    comb1      : CombinationResult for DA1-C1 (M1, R1).
    comb2      : CombinationResult for DA1-C2 (M2, R1).
    governing  : The DA1 CombinationResult with the lower FoS_d.
    fos_char   : Characteristic FoS (Comb 1, γ_M = 1.0).
    fos_d_min  : Governing design FoS (lowest DA1 combo).
    passes     : True if BOTH DA1 combinations pass.
    da2        : DA2Result (characteristic FoS ÷ γ_R = 1.10).
    da3_fos_d  : DA3 FoS_d (= DA1-C2 fos_d; Bond & Harris 2008 §14.4).
    da3_passes : True if DA3 passes (FoS_d ≥ 1.0).
    warnings   : Aggregated warnings from both searches.
    """
    soil_char  : Soil
    slope      : SlopeGeometry
    ru         : float
    comb1      : CombinationResult
    comb2      : CombinationResult
    governing  : CombinationResult
    fos_char   : float
    fos_d_min  : float
    passes     : bool
    da2        : "DA2Result | None"  = field(default=None)
    da3_fos_d  : float               = field(default=0.0)
    da3_passes : bool                = field(default=False)
    warnings   : list[str]           = field(default_factory=list)

    def summary(self) -> str:
        """Formatted multi-line verification report (DA1 + DA2 + DA3)."""
        da2_line = (self.da2.summary_line() if self.da2 is not None
                    else "  DA2: not computed")
        da3_tick = '✅ PASS' if self.da3_passes else '❌ FAIL'
        da3_line = (
            f"  DA3  γ_φ={M2_GAMMA_PHI:.2f}  γ_c={M2_GAMMA_C:.2f}  "
            f"γ_R={R3_GAMMA_R:.2f}  (≡ DA1-C2 for slopes)  "
            f"FoS_d={self.da3_fos_d:.4f}  {da3_tick}"
        )
        lines = [
            f"{'═'*70}",
            f"  EC7 Slope Stability Verification — DA1 / DA2 / DA3",
            f"{'─'*70}",
            f"  Soil (char.)   : {self.soil_char.name}",
            f"  φ'_k = {self.soil_char.phi_k:.1f}°   "
            f"c'_k = {self.soil_char.c_k:.2f} kPa   "
            f"γ = {self.soil_char.gamma:.1f} kN/m³",
            f"  rᵤ             : {self.ru:.3f}",
            f"  FoS_char       : {self.fos_char:.4f}  (γ_M = 1.0)",
            f"{'─'*70}",
            f"  EC7 DA1 — both combinations must pass (EN 1997-1 §2.4.7.3.2):",
            self.comb1.summary_line(),
            self.comb2.summary_line(),
            f"  Governing DA1  : {self.governing.label}  "
            f"(FoS_d = {self.fos_d_min:.4f})",
            f"{'─'*70}",
            f"  EC7 DA2 — M1 strengths + R2 resistance factor (§2.4.7.3.3):",
            da2_line,
            f"{'─'*70}",
            f"  EC7 DA3 — M2 factors + R3 (§2.4.7.3.4):",
            da3_line,
            f"{'─'*70}",
            f"  DA1 Overall    : "
            f"{'✅ PASS' if self.passes else '❌ FAIL'}",
            f"{'═'*70}",
        ]
        if self.warnings:
            lines.insert(-1, f"  ⚠️  {len(self.warnings)} warning(s) — see .warnings")
        return "\n".join(lines)


# ============================================================
#  Private helper
# ============================================================

def _factored_soil(char_soil: Soil,
                   gamma_phi: float,
                   gamma_c:   float) -> Soil:
    """
    Returns a new Soil whose strength parameters are design values per EC7.

    Formula (EC7 §2.4.6.2):
        tan(φ'_d) = tan(φ'_k) / γ_φ   →   φ'_d = arctan(tan(φ'_k) / γ_φ)
        c'_d      = c'_k / γ_c

    Unit weight γ is NOT factored — EC7 §2.4.6.1 explicitly states that
    γ_γ = 1.0 in both combinations for self-weight calculations.

    :param char_soil:  Original Soil with characteristic parameters.
    :param gamma_phi:  Partial factor for friction angle (–).
    :param gamma_c:    Partial factor for cohesion (–).
    :return:           New Soil instance with design values.
    :raises ValueError: If gamma_phi or gamma_c < 1.0.
    """
    if gamma_phi < 1.0:
        raise ValueError(f"gamma_phi must be ≥ 1.0, got {gamma_phi}")
    if gamma_c < 1.0:
        raise ValueError(f"gamma_c must be ≥ 1.0, got {gamma_c}")

    phi_d = math.degrees(
        math.atan(math.tan(math.radians(char_soil.phi_k)) / gamma_phi)
    )
    c_d   = char_soil.c_k / gamma_c

    return Soil(
        name          = f"{char_soil.name} [design γ_φ={gamma_phi:.2f}]",
        unit_weight   = char_soil.gamma,   # γ_γ = 1.0 always
        friction_angle= phi_d,
        cohesion      = c_d,
        gamma_s       = char_soil.gamma_s,
    )


# ============================================================
#  Public API
# ============================================================


def verify_slope_da1(
    slope      : SlopeGeometry,
    soil       : Soil,
    ru         : float = 0.0,
    search_zone: dict[str, float | int] | None = None,
    cx_range   : tuple[float, float] | None = None,
    cy_range   : tuple[float, float] | None = None,
    r_range    : tuple[float, float] | None = None,
    n_cx       : int   = 10,
    n_cy       : int   = 10,
    n_r        : int   = 5,
    num_slices : int   = 20,
    verbose    : bool  = False,
) -> VerificationResult:
    """
    EC7 Design Approach 1 verification for circular slope stability (GEO),
    extended to also compute DA2 and DA3 results.

    Runs grid_search() TWICE (once per DA1 combination) using factored soil
    strength parameters.  DA2 and DA3 are derived from the same searches
    without additional grid evaluations:

        DA2: FoS_d = FoS_char / γ_R  (R2 set, γ_R = 1.10)
             Reference: EC7 Table A.14; Bond & Harris (2008) §14.3.

        DA3: FoS_d = DA1-C2 fos_d
             Numerically identical to DA1-C2 for slopes in the material-
             factoring approach (Bond & Harris 2008 §14.4 — DA3 uses M2
             factors and R3=1.0, same as DA1-C2).

    The overall DA1 verification passes if and only if BOTH combinations
    satisfy FoS_d ≥ 1.0.

    Formula per combination (EC7 §11.5.1 material-factoring approach):
        φ'_d = arctan( tan(φ'_k) / γ_φ )
        c'_d = c'_k / γ_c
        γ_γ  = 1.0  (unit weight never factored, EC7 §2.4.6.1)
        FoS_d = minimum FoS from grid search with design soil.
        Pass if FoS_d ≥ 1.0.

    :param slope:      Ground surface geometry (SlopeGeometry).
    :param soil:       Characteristic soil parameters (Soil).
    :param ru:         Pore pressure ratio rᵤ (default 0.0).
    :param cx_range:   Search bounds for circle centre x (m). None = auto.
    :param cy_range:   Search bounds for circle centre y (m). None = auto.
    :param r_range:    Search bounds for circle radius   (m). None = auto.
    :param n_cx:       Grid points along cx axis.
    :param n_cy:       Grid points along cy axis.
    :param n_r:        Grid points along R  axis.
    :param num_slices: Slices per Bishop evaluation.
    :param verbose:    Print search progress if True.
    :return:           VerificationResult with DA1, DA2, and DA3 results.
    :raises ValueError: If parameters are out of range or no valid circle
                        is found for either combination.
    """
    if not (0.0 <= ru < 1.0):
        raise ValueError(f"rᵤ must be in [0, 1), got {ru}")

    search_kwargs = dict(
        ru         = ru,
        search_zone = search_zone,
        cx_range   = cx_range,
        cy_range   = cy_range,
        r_range    = r_range,
        n_cx       = n_cx,
        n_cy       = n_cy,
        n_r        = n_r,
        num_slices = num_slices,
        verbose    = verbose,
    )

    # ── DA1 Combination 1  (M1: γ_φ=1.00, γ_c=1.00, R1: γ_R=1.00) ───────
    soil_c1   = _factored_soil(soil, M1_GAMMA_PHI, M1_GAMMA_C)
    search_c1 = grid_search(slope, soil_c1, **search_kwargs)

    comb1 = CombinationResult(
        label         = "DA1-C1",
        gamma_phi     = M1_GAMMA_PHI,
        gamma_c       = M1_GAMMA_C,
        phi_d         = soil_c1.phi_k,
        c_d           = soil_c1.c_k,
        search_result = search_c1,
        fos_d         = search_c1.fos_min,
        passes        = search_c1.fos_min >= FOS_D_LIMIT,
    )

    # ── DA1 Combination 2  (M2: γ_φ=1.25, γ_c=1.25, R1: γ_R=1.00) ───────
    soil_c2   = _factored_soil(soil, M2_GAMMA_PHI, M2_GAMMA_C)
    search_c2 = grid_search(slope, soil_c2, **search_kwargs)

    comb2 = CombinationResult(
        label         = "DA1-C2",
        gamma_phi     = M2_GAMMA_PHI,
        gamma_c       = M2_GAMMA_C,
        phi_d         = soil_c2.phi_k,
        c_d           = soil_c2.c_k,
        search_result = search_c2,
        fos_d         = search_c2.fos_min,
        passes        = search_c2.fos_min >= FOS_D_LIMIT,
    )

    governing  = comb2 if comb2.fos_d <= comb1.fos_d else comb1
    fos_char   = search_c1.fos_min

    # ── DA2  (A1+M1+R2: same search as C1, apply γ_R=1.10 post-search) ───
    fos_d_da2 = fos_char / R2_GAMMA_R
    da2 = DA2Result(
        label    = "DA2",
        gamma_R  = R2_GAMMA_R,
        fos_char = fos_char,
        fos_d    = fos_d_da2,
        passes   = fos_d_da2 >= FOS_D_LIMIT,
    )

    # ── DA3  (A2+M2+R3 for geotechnical actions; R3 γ_R=1.0 for slopes) ──
    # Numerically identical to DA1-C2 (Bond & Harris 2008 §14.4).
    da3_fos_d  = comb2.fos_d
    da3_passes = da3_fos_d >= FOS_D_LIMIT

    # ── Aggregate warnings ────────────────────────────────────────────────
    all_warnings: list[str] = []
    for w in search_c1.warnings:
        all_warnings.append(f"[C1] {w}")
    for w in search_c2.warnings:
        all_warnings.append(f"[C2] {w}")

    return VerificationResult(
        soil_char  = soil,
        slope      = slope,
        ru         = ru,
        comb1      = comb1,
        comb2      = comb2,
        governing  = governing,
        fos_char   = fos_char,
        fos_d_min  = governing.fos_d,
        passes     = comb1.passes and comb2.passes,
        da2        = da2,
        da3_fos_d  = da3_fos_d,
        da3_passes = da3_passes,
        warnings   = all_warnings,
    )
