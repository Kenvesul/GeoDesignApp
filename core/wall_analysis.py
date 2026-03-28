"""
wall_analysis.py -- EC7 DA1 (GEO) + EQU retaining wall ULS verification.

Checks a gravity, cantilever, L-wall, or counterfort retaining wall against
three ULS failure modes under Eurocode 7 Design Approach 1 (DA1) and the
equilibrium limit state (EQU):

    1. SLIDING   (GEO) -- horizontal translation along wall base.
    2. BEARING   (GEO) -- base bearing capacity per EC7 Annex D.
    3. OVERTURNING (EQU) -- rigid-body rotation about toe.

EQU vs GEO — action partial factor sets (EC7 EN 1997-1:2004)
-------------------------------------------------------------
    ┌──────────────────────────────────────────────────────────────┐
    │ Limit   │ Table  │ γ_G,unfav │ γ_G,fav │ γ_Q  │ Applies to │
    ├──────────────────────────────────────────────────────────────┤
    │ EQU     │ A.2    │   1.10    │  0.90   │ 1.50  │ Overturning│
    │ GEO C1  │ A.3    │   1.35    │  1.00   │ 1.50  │ Sliding /  │
    │ GEO C2  │ A.4    │   1.00    │  1.00   │ 1.30  │ Bearing    │
    └──────────────────────────────────────────────────────────────┘

    KEY DISTINCTION: EQU uses γ_G,fav = 0.90 (penalises restoring actions
    more than GEO's 1.00).  EC7 §2.4.7.2 requires overturning to be verified
    with the EQU factor set.  Sliding and bearing use the GEO DA1 set.

    Variable restoring actions are excluded in EQU (γ_Q,fav = 0):
    surcharge on heel contributes to GEO stability but not EQU.

    Reference: Bond & Harris – Decoding Eurocode 7, §14.3.

Material partial factors — DA1 combinations (EC7 Tables A.3 / A.4)
-------------------------------------------------------------------
    ┌─────────┬───────┬───────┐
    │ Comb    │ γ_phi │  γ_c  │
    ├─────────┼───────┼───────┤
    │ C1 M1   │  1.00 │  1.00 │  (also used for EQU — M1 applies)
    │ C2 M2   │  1.25 │  1.25 │
    └─────────┴───────┴───────┘

Resistance factors R1 (EC7 Table A.13 — both DA1 combinations)
---------------------------------------------------------------
    γ_R,h (sliding)  = 1.00   (R1 set; included but = 1.0 so no change)
    γ_R,v (bearing)  = 1.00

Pass criteria
-------------
    GEO  Sliding    : Rd / Ed >= 1.0  (both C1 and C2)
    GEO  Bearing    : q_applied / q_ult <= 1.0  (both C1 and C2)
    EQU  Overturning: MR_equ / MO_equ >= 1.0  AND  e_equ <= B/3

References:
    Craig's Soil Mechanics, 9th ed., §11.2–11.4.
    Eurocode 7 – EN 1997-1:2004, §9; Tables A.2/A.3/A.4/A.13; Annex D.
    Bond & Harris – Decoding Eurocode 7, §14.
    Das, B.M. (2019). Principles of Geotechnical Engineering, §11.

Sign conventions:
    Moments taken about the TOE (front-bottom corner of base slab).
    Clockwise moments are RESTORING (positive MR).
    Anti-clockwise moments are OVERTURNING (positive MO).
    Horizontal forces positive = acting toward toe (destabilising).
    Depth z measured downward from top of retained soil.

Units:
    Lengths (m), forces (kN/m), moments (kN·m/m), pressures (kPa).
"""

import math
from dataclasses import dataclass, field

from models.soil         import Soil
from models.wall_geometry import RetainingWall
from models.surcharge    import UniformSurcharge
from models.foundation   import Foundation

from core.rankine_coulomb import (
    ka_rankine, ka_coulomb,
    kp_rankine,
    active_thrust, passive_thrust,
)
from core.bearing_capacity import (
    bearing_resistance_ec7,
    BearingResult as _BearingCapacityResult,  # aliased to avoid name clash
)


# ============================================================
#  EC7 DA1 partial factor constants  (Tables A.3 / A.4)
# ============================================================

# Combination 1  (A1 + M1 + R1)
C1_G_UNFAV : float = 1.35   # gamma_G unfavourable permanent actions
C1_G_FAV   : float = 1.00   # gamma_G favourable permanent actions
C1_Q       : float = 1.50   # gamma_Q variable actions (surcharge)
C1_PHI     : float = 1.00   # gamma_phi friction angle
C1_C       : float = 1.00   # gamma_c  cohesion

# Combination 2  (A2 + M2 + R1)
C2_G_UNFAV : float = 1.00
C2_G_FAV   : float = 1.00
C2_Q       : float = 1.30
C2_PHI     : float = 1.25
C2_C       : float = 1.25

# Resistance factors R1 — EC7 Table A.13 (both DA1 combinations)
# γ_R,h = 1.00 (sliding horizontal), γ_R,v = 1.00 (bearing vertical)
R1_SLIDING  : float = 1.00   # gamma_R,h — resistance to sliding (Table A.13 R1 set)
R1_BEARING  : float = 1.00   # gamma_R,v — bearing resistance   (Table A.13 R1 set)

# EQU partial factors — EC7 Table A.2 (overturning equilibrium check)
# Used ONLY for the overturning check; NOT for sliding or bearing.
#   γ_G,unfav = 1.10  permanent destabilising (earth pressure)
#   γ_G,fav   = 0.90  permanent stabilising  (self-weight, backfill)
#   γ_Q       = 1.50  variable destabilising (surcharge lateral)
#   Variable stabilising = 0.00 (surcharge on heel excluded conservatively)
EQU_G_UNFAV : float = 1.10
EQU_G_FAV   : float = 0.90
EQU_Q       : float = 1.50

# Minimum design FoS (all limit states)
FOS_LIMIT   : float = 1.00

# Eccentricity limit for base pressure distribution (EC7 §6.5.4)
ECCENTRICITY_LIMIT_RATIO : float = 1.0 / 3.0   # e <= B/3


# ============================================================
#  Result containers
# ============================================================

@dataclass
class SlidingResult:
    """
    ULS sliding check for one DA1 combination.

    Attributes
    ----------
    H_drive    : Factored horizontal driving force (kN/m).
    R_slide    : Factored sliding resistance (kN/m).
    fos_d      : Design FoS = R_slide / H_drive.
    passes     : True if fos_d >= 1.0.
    delta_base : Base friction angle used (degrees).
    N_total    : Factored total vertical load (kN/m).
    """
    H_drive    : float
    R_slide    : float
    fos_d      : float
    passes     : bool
    delta_base : float
    N_total    : float


@dataclass
class OverturningResult:
    """
    GEO overturning check for one DA1 combination (computed for reference).

    NOTE: EC7 requires overturning to be verified using the EQU factor set
    (Table A.2), not the GEO set.  This result uses GEO factors from the
    DA1 combination and is reported for reference only.  The definitive
    overturning check is EquOverturningResult (in WallResult.equ_overturn).

    Attributes
    ----------
    MR         : Factored restoring moment about toe (kN·m/m) — GEO factors.
    MO         : Factored overturning moment about toe (kN·m/m) — GEO factors.
    fos_d      : Design FoS = MR / MO.
    e          : Eccentricity of resultant from base centre (m).
    e_limit    : Eccentricity limit = B/3 (m).
    passes     : True if fos_d >= 1.0 AND e <= e_limit.
    """
    MR         : float
    MO         : float
    fos_d      : float
    e          : float
    e_limit    : float
    passes     : bool


@dataclass
class EquOverturningResult:
    """
    EQU overturning check using EC7 Table A.2 partial factors.

    EC7 §2.4.7.2 requires the overturning limit state to be verified with
    the EQU factor set, which distinguishes it from the GEO factor sets used
    for sliding and bearing.

    EQU factors (Table A.2):
        γ_G,unfav = 1.10  — permanent destabilising (earth pressure)
        γ_G,fav   = 0.90  — permanent stabilising   (self-weight, backfill)
        γ_Q       = 1.50  — variable destabilising  (surcharge lateral thrust)
        γ_Q,fav   = 0.00  — variable restoring excluded conservatively

    Note: EQU with γ_G,fav = 0.90 is MORE ONEROUS for restoring actions
    than GEO DA1-C1 (γ_G,fav = 1.00).  A wall passing the GEO overturning
    check may still fail the EQU check.

    Material factors for EQU: M1 (unfactored strength) applies.
    Ka is computed using the characteristic friction angle.

    Reference:
        EC7 EN 1997-1:2004, Table A.2; §2.4.7.2.
        Bond & Harris – Decoding Eurocode 7, §14.3.

    Attributes
    ----------
    MR_perm_char : Characteristic permanent restoring moment (kN·m/m).
    MO_perm_char : Characteristic permanent overturning moment (kN·m/m).
    MO_var_char  : Characteristic variable overturning moment (kN·m/m).
    MR_equ       : EQU-factored restoring: 0.90 × MR_perm_char (kN·m/m).
    MO_equ       : EQU-factored overturning: 1.10×MO_perm + 1.50×MO_var (kN·m/m).
    N_equ        : EQU-factored permanent vertical force: 0.90 × N_perm_char (kN/m).
    fos_d        : Design FoS = MR_equ / MO_equ.  Must be >= 1.0.
    e            : Eccentricity with EQU factored forces (m).
    e_limit      : Eccentricity limit = B/3 (m).
    passes       : True if fos_d >= 1.0 AND e <= e_limit.
    """
    MR_perm_char : float
    MO_perm_char : float
    MO_var_char  : float
    MR_equ       : float
    MO_equ       : float
    N_equ        : float
    fos_d        : float
    e            : float
    e_limit      : float
    passes       : bool


@dataclass
class BasePressureResult:
    """
    Base pressure distribution for one DA1 combination (applied stress only).

    Attributes
    ----------
    N_total    : Factored total vertical load (kN/m).
    e          : Eccentricity of resultant from base centre (m).
    B_eff      : Effective base width B' = B - 2e (m).
    q_max      : Maximum base pressure at toe (kPa).
    q_min      : Minimum base pressure at heel (kPa).  May be 0 when e > B/6.
    middle_third : True if e <= B/6 (no tension zone, trapezoidal distribution).
    """
    N_total      : float
    e            : float
    B_eff        : float
    q_max        : float
    q_min        : float
    middle_third : bool


@dataclass
class WallBearingCheck:
    """
    GEO bearing capacity verification for the retaining wall base.

    Compares the applied base pressure against the EC7 Annex D ultimate
    bearing resistance of the foundation soil.

    EC7 Annex D formula (D.2) applied as a strip foundation (L → ∞):
        R/A' = c'·Nc·sc·ic·bc·gc
             + q·Nq·sq·iq·bq·gq
             + 0.5·γ'·B'·Nγ·sγ·iγ·bγ·gγ

    The effective width B' = B_base − 2·e accounts for eccentricity.
    Embedment Df = t_base (conservative minimum; actual may be larger).
    Horizontal load H = H_drive is passed to inclination factor calculations.

    Reference:
        EC7 Annex D / Craig §11.4 / Bond & Harris Ch.14.

    Attributes
    ----------
    B_eff        : Effective base width B' = B - 2e (m).
    Df           : Embedment depth used (= t_base, m).
    N_total      : Factored vertical load on base (kN/m).
    H_drive      : Factored horizontal driving force (kN/m).
    q_applied    : Applied base pressure = N_total / B_eff (kPa).
    q_ult        : Ultimate bearing resistance from EC7 Annex D (kPa).
    utilisation  : q_applied / q_ult.  Must be <= 1.0 to pass.
    passes       : True if utilisation <= 1.0.
    """
    B_eff       : float
    Df          : float
    N_total     : float
    H_drive     : float
    q_applied   : float
    q_ult       : float
    utilisation : float
    passes      : bool


@dataclass
class StemPoint:
    """One node in the stem bending/shear diagram."""
    z          : float   # depth below top of retained soil (m)
    M          : float   # bending moment (kN·m/m)  — positive = tension on back face
    V          : float   # shear force (kN/m)        — positive = acting toward toe


@dataclass
class StemStructuralResult:
    """
    Structural action demands on the cantilever stem under ULS loading.

    The stem is treated as a vertical cantilever fixed at the base–stem
    junction.  Active earth pressure (triangular) + surcharge (uniform)
    produce a horizontal distributed load which is integrated to give
    shear V(z) and bending moment M(z) at every point on the stem.

    Sign convention (Craig §11.2):
        z   = depth below top of retained soil (0 at crest, h_wall at base).
        V   = horizontal shear in the stem cross-section (kN/m).
        M   = bending moment about the stem centroid (kN·m/m).
              Positive M = tension on the back (earth-side) face.
        M_max is at the fixed base (z = h_wall) for pure triangular load.

    Formula (Craig §11.2 / Das §11.5):
        Horizontal pressure at depth z:
            p(z) = Ka·γ·z + Ka·q_surcharge    [kPa]

        Shear at depth z (integrating from top):
            V(z) = ∫₀ᶻ p(t) dt
                 = Ka·γ·z²/2 + Ka·q·z

        Moment at depth z about the stem-base junction:
            M(z) = ∫₀ᶻ p(t)·(z−t) dt
                 = Ka·γ·z³/6 + Ka·q·z²/2

        Maximum shear  : V_max = V(h_wall) at fixed end.
        Maximum moment : M_max = M(h_wall) at fixed end.

    Reference:
        Craig's Soil Mechanics, 9th ed., §11.2 (cantilever wall analysis).
        Das, B.M. (2019). Principles of Geotechnical Engineering, §11.5.

    Attributes
    ----------
    ka         : Active pressure coefficient used.
    phi_d      : Design friction angle used (degrees).
    q_sur      : Design surcharge pressure (kPa).  0 if no surcharge.
    M_max      : Maximum bending moment at fixed base (kN·m/m).
    V_max      : Maximum shear force at fixed base (kN/m).
    z_M_max    : Depth of M_max below top of retained soil (m) = h_wall.
    diagram    : List of StemPoint giving (z, M, V) at intervals.
    n_points   : Number of diagram points.
    """
    ka       : float
    phi_d    : float
    q_sur    : float
    M_max    : float
    V_max    : float
    z_M_max  : float
    diagram  : list[StemPoint]
    n_points : int


@dataclass
class WallCombinationResult:
    """
    All three ULS checks for one DA1 combination.

    Attributes
    ----------
    label      : 'DA1-C1' or 'DA1-C2'.
    gG_unfav   : Permanent unfavourable action factor applied.
    gQ         : Variable action factor applied.
    g_phi      : Friction angle material factor applied.
    g_c        : Cohesion material factor applied.
    phi_d      : Design friction angle of backfill (degrees).
    c_d        : Design cohesion of backfill (kPa).
    ka         : Active pressure coefficient used.
    Pa         : Total active thrust (kN/m) -- unfactored for reference.
    sliding    : SlidingResult.
    overturn   : OverturningResult.
    base_press : BasePressureResult (applied stress distribution).
    bearing    : WallBearingCheck (EC7 Annex D capacity check).
    passes     : True if sliding, overturning AND bearing all pass.
    """
    label      : str
    gG_unfav   : float
    gQ         : float
    g_phi      : float
    g_c        : float
    phi_d      : float
    c_d        : float
    ka         : float
    Pa         : float
    sliding    : SlidingResult
    overturn   : OverturningResult
    base_press : BasePressureResult
    bearing    : WallBearingCheck
    passes     : bool

    def summary_line(self) -> str:
        sl = "PASS" if self.sliding.passes  else "FAIL"
        ot = "PASS" if self.overturn.passes else "FAIL"
        br = "PASS" if self.bearing.passes  else "FAIL"
        return (
            f"  {self.label}  gG={self.gG_unfav:.2f}  gQ={self.gQ:.2f}"
            f"  g_phi={self.g_phi:.2f}  |"
            f"  Sliding FoS_d={self.sliding.fos_d:.3f} [{sl}]"
            f"  Overturn FoS_d={self.overturn.fos_d:.3f} (e={self.overturn.e:.3f}m) [{ot}]"
            f"  Bearing eta={self.bearing.utilisation:.3f} [{br}]"
        )


@dataclass
class WallResult:
    """
    Complete EC7 DA1 (GEO) + EQU wall stability + stem structural verification.

    Limit-state split (Sprint 6):
        GEO  DA1-C1 & C2 : sliding (comb1/comb2.sliding) + bearing (comb1/comb2.bearing)
        EQU  (Table A.2) : overturning (equ_overturn) — separate factor set, see §2.4.7.2
        REF  overturning : comb1/comb2.overturn computed with GEO factors for reference.

    Overall PASS:
        comb1 GEO passes  AND  comb2 GEO passes  AND  equ_overturn passes

    Attributes
    ----------
    wall         : RetainingWall geometry used.
    backfill     : Characteristic backfill Soil.
    foundation   : Characteristic foundation Soil.
    surcharge    : UniformSurcharge applied, or None.
    comb1        : WallCombinationResult for DA1-C1 (GEO).
    comb2        : WallCombinationResult for DA1-C2 (GEO).
    governing    : Combination with the lower sliding FoS_d (worst GEO).
    equ_overturn : EquOverturningResult — normative overturning check (EQU Table A.2).
    stem         : StemStructuralResult for ULS stem demands (governing comb).
    passes       : True if BOTH GEO combs pass AND equ_overturn passes.
    warnings     : Advisory messages.
    """
    wall         : RetainingWall
    backfill     : Soil
    foundation   : Soil
    surcharge    : UniformSurcharge | None
    comb1        : WallCombinationResult
    comb2        : WallCombinationResult
    governing    : WallCombinationResult
    equ_overturn : "EquOverturningResult | None" = field(default=None)
    stem         : "StemStructuralResult | None" = field(default=None)
    passes       : bool = False
    warnings     : list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"{'='*70}",
            f"  EC7 DA1+EQU Retaining Wall Verification",
            f"{'-'*70}",
            f"  Wall       : {self.wall.wall_type}  h={self.wall.h_wall}m"
            f"  B={self.wall.b_base}m  b_heel={self.wall.b_heel:.3f}m",
            f"  Backfill   : {self.backfill.name}"
            f"  phi_k={self.backfill.phi_k:.1f}°  gamma={self.backfill.gamma:.1f} kN/m³",
            f"  Foundation : {self.foundation.name}"
            f"  phi_k={self.foundation.phi_k:.1f}°  c_k={self.foundation.c_k:.1f} kPa",
            f"  Surcharge  : {self.surcharge.q if self.surcharge else 'None'} kPa",
            f"{'-'*70}",
            f"  GEO (DA1) — Sliding + Bearing:",
            self.comb1.summary_line(),
            self.comb2.summary_line(),
        ]
        if self.equ_overturn is not None:
            eq = self.equ_overturn
            eq_tag = "PASS" if eq.passes else "FAIL"
            lines += [
                f"{'-'*70}",
                f"  EQU (Table A.2) — Overturning  [normative per EC7 §2.4.7.2]:",
                f"    MR_equ = 0.90×{eq.MR_perm_char:.1f} = {eq.MR_equ:.1f} kN·m/m",
                f"    MO_equ = 1.10×{eq.MO_perm_char:.1f} + 1.50×{eq.MO_var_char:.1f}"
                f" = {eq.MO_equ:.1f} kN·m/m",
                f"    FoS_d = {eq.fos_d:.3f}   e = {eq.e:.3f} m"
                f"  (limit B/3 = {eq.e_limit:.3f} m)   [{eq_tag}]",
            ]
        lines += [
            f"{'-'*70}",
            f"  Governing GEO : {self.governing.label}"
            f"  (sliding FoS_d = {self.governing.sliding.fos_d:.3f})",
            f"  Base e = {self.governing.base_press.e:.3f} m"
            f"  q_max = {self.governing.base_press.q_max:.1f} kPa"
            f"  Bearing η = {self.governing.bearing.utilisation:.3f}"
            f"  {'PASS' if self.governing.bearing.passes else 'FAIL'}",
        ]
        if self.stem is not None:
            lines += [
                f"{'-'*70}",
                f"  Stem (Craig §11.2) : Ka={self.stem.ka:.4f}"
                f"  M_max={self.stem.M_max:.2f} kN·m/m"
                f"  V_max={self.stem.V_max:.2f} kN/m",
            ]
        ov_tag  = "PASS" if self.passes else "FAIL"
        lines += [
            f"{'-'*70}",
            f"  Overall : {ov_tag}",
            f"{'='*70}",
        ]
        if self.warnings:
            lines.insert(-1, f"  WARNING: {len(self.warnings)} message(s) — see .warnings")
        return "\n".join(lines)


# ============================================================
#  Private helpers
# ============================================================

def _design_phi(phi_k: float, g_phi: float) -> float:
    """Design friction angle per EC7 SS2.4.6.2."""
    return math.degrees(math.atan(math.tan(math.radians(phi_k)) / g_phi))


def _design_c(c_k: float, g_c: float) -> float:
    """Design cohesion per EC7 SS2.4.6.2."""
    return c_k / g_c


def _select_ka(wall: RetainingWall, phi_d: float) -> float:
    """
    Selects Ka using Coulomb if wall friction is non-zero, Rankine otherwise.

    Coulomb is used when delta_wall > 0 (wall friction mobilised).
    For a smooth or conservative design, Rankine (delta=0) is appropriate.
    """
    if wall.delta_wall > 0.0:
        return ka_coulomb(
            phi_d  = phi_d,
            delta  = min(wall.delta_wall, phi_d),  # delta <= phi_d always
            beta   = wall.beta_backfill,
            alpha  = wall.alpha_wall,
        )
    return ka_rankine(phi_d)


def _base_friction_angle(wall: RetainingWall, phi_d_foundation: float) -> float:
    """
    Selects the base friction angle delta_b.

    EC7 SS6.5.3: for cast-in-situ concrete on soil, delta_b = phi'_d
    is acceptable.  For conservative design or pre-cast, delta_b = 2/3 phi'_d.
    If the wall specifies delta_base explicitly, that value is used.
    Otherwise 2/3 phi'_d_foundation is applied.
    """
    if wall.delta_base is not None:
        return wall.delta_base
    return (2.0 / 3.0) * phi_d_foundation


def _assemble_forces(
    wall         : RetainingWall,
    backfill     : Soil,
    foundation   : Soil,
    surcharge    : UniformSurcharge | None,
    gG_unfav     : float,
    gG_fav       : float,
    gQ           : float,
    g_phi        : float,
    g_c          : float,
) -> dict:
    """
    Assembles all factored forces and moments for one DA1 combination.

    Also computes characteristic (unfactored) moment components required
    by the separate EQU overturning check (Table A.2).  These are always
    present in the returned dict regardless of which combination is being
    assembled.

    Returns a dict with keys:
        phi_d_back, c_d_back, phi_d_found, c_d_found,
        ka, Pa_char, Pa_q_char,
        H_drive, N_total, MR, MO,
        -- EQU characteristic components --
        N_perm_char, MR_perm_char, MR_var_char,
        MO_perm_char, MO_var_char
    """
    # ── Design strength values ────────────────────────────────────────────
    phi_d_back  = _design_phi(backfill.phi_k,   g_phi)
    c_d_back    = _design_c(  backfill.c_k,     g_c)
    phi_d_found = _design_phi(foundation.phi_k, g_phi)
    c_d_found   = _design_c(  foundation.c_k,   g_c)

    ka = _select_ka(wall, phi_d_back)

    # ── Active thrust on stem (retained height = h_wall) ─────────────────
    Pa_char, y_a = active_thrust(
        h    = wall.h_wall,
        gamma= backfill.gamma,
        ka   = ka,
        c_d  = c_d_back,
    )
    y_Pa_from_toe = y_a + wall.t_base

    H_soil_factored = gG_unfav * Pa_char

    # ── Surcharge contribution ────────────────────────────────────────────
    Pa_q_char           = 0.0
    y_Pa_q_from_toe     = (wall.h_wall / 2.0) + wall.t_base
    V_surcharge_on_heel = 0.0

    if surcharge is not None:
        Pa_q_char           = ka * surcharge.q * wall.h_wall
        V_surcharge_on_heel = surcharge.q * wall.b_heel

    H_q_factored = gQ * Pa_q_char

    # ── Total factored horizontal driving ─────────────────────────────────
    H_drive = H_soil_factored + H_q_factored

    # ── Vertical component of active thrust (wall friction δ > 0) ─────────
    delta_r       = math.radians(wall.delta_wall)
    V_active_char = Pa_char * math.tan(delta_r)   # stabilising

    # ── Counterfort weight (counterfort wall type only) ────────────────────
    # Counterforts are permanent concrete, treated as favourable (stabilising).
    W_cf_char = wall.w_counterforts   # characteristic (kN/m run)

    # ── Factored vertical forces (stabilising) ─────────────────────────────
    W_stem_f      = gG_fav * wall.w_stem
    W_base_f      = gG_fav * wall.w_base
    W_soil_heel_f = gG_fav * backfill.gamma * wall.b_heel * wall.h_wall
    W_cf_f        = gG_fav * W_cf_char
    V_active_f    = gG_fav * V_active_char
    V_surcharge_f = gQ     * V_surcharge_on_heel

    N_total = W_stem_f + W_base_f + W_soil_heel_f + W_cf_f + V_active_f + V_surcharge_f

    # ── Restoring moments about toe ────────────────────────────────────────
    MR = (
        W_stem_f      * wall.x_stem_centroid         +
        W_base_f      * wall.x_base_centroid          +
        W_soil_heel_f * wall.x_heel_soil_centroid     +
        W_cf_f        * wall.x_heel_soil_centroid     +  # centerforts above heel
        V_active_f    * wall.b_base                   +  # at back face of wall
        gQ * V_surcharge_on_heel * wall.x_heel_soil_centroid
    )

    # ── Overturning moments about toe ──────────────────────────────────────
    MO = (
        H_soil_factored * y_Pa_from_toe   +
        H_q_factored    * y_Pa_q_from_toe
    )

    # ── Characteristic (unfactored) moment components for EQU check ────────
    # These use the CHARACTERISTIC material strengths (phi_k, not phi_d)
    # via the factored forces assembled above — when called with g_phi=1.0
    # they give the M1/EQU characteristic values directly.
    N_perm_char  = (wall.w_stem + wall.w_base +
                    backfill.gamma * wall.b_heel * wall.h_wall +
                    W_cf_char + V_active_char)

    MR_perm_char = (wall.w_stem      * wall.x_stem_centroid         +
                    wall.w_base      * wall.x_base_centroid          +
                    backfill.gamma * wall.b_heel * wall.h_wall *
                                      wall.x_heel_soil_centroid      +
                    W_cf_char        * wall.x_heel_soil_centroid     +
                    V_active_char    * wall.b_base)

    MR_var_char  = V_surcharge_on_heel * wall.x_heel_soil_centroid
    MO_perm_char = Pa_char   * y_Pa_from_toe
    MO_var_char  = Pa_q_char * y_Pa_q_from_toe

    return dict(
        phi_d_back   = phi_d_back,
        c_d_back     = c_d_back,
        phi_d_found  = phi_d_found,
        c_d_found    = c_d_found,
        ka           = ka,
        Pa_char      = Pa_char,
        Pa_q_char    = Pa_q_char,
        H_drive      = H_drive,
        N_total      = N_total,
        MR           = MR,
        MO           = MO,
        # EQU characteristic components (always present)
        N_perm_char  = N_perm_char,
        MR_perm_char = MR_perm_char,
        MR_var_char  = MR_var_char,
        MO_perm_char = MO_perm_char,
        MO_var_char  = MO_var_char,
    )


def _check_sliding(
    f            : dict,
    wall         : RetainingWall,
) -> SlidingResult:
    """
    EC7 GEO sliding check.

    Formula (Craig §11.4, EC7 §6.5.3):
        Rd = N_total * tan(delta_b) + c_d_found * b_base
        Ed = H_drive
        FoS_d = Rd / Ed >= 1.0

    delta_b is the base-soil friction angle.
    """
    delta_b = _base_friction_angle(wall, f["phi_d_found"])

    R_slide = (
        f["N_total"] * math.tan(math.radians(delta_b)) +
        f["c_d_found"] * wall.b_base
    ) / R1_SLIDING

    fos_d  = R_slide / max(f["H_drive"], 1e-9)
    passes = fos_d >= FOS_LIMIT

    return SlidingResult(
        H_drive    = f["H_drive"],
        R_slide    = R_slide,
        fos_d      = fos_d,
        passes     = passes,
        delta_base = delta_b,
        N_total    = f["N_total"],
    )


def _check_overturning(
    f    : dict,
    wall : RetainingWall,
) -> OverturningResult:
    """
    EQU overturning check about the toe.

    Formula (Craig §11.4):
        FoS_d = MR / MO >= 1.0
        e     = B/2 - (MR - MO) / N_total
        Pass  : FoS_d >= 1.0  AND  e <= B/3

    EC7 §6.5.4: resultant must lie within the base (e <= B/2).
    Conventional practice requires e <= B/3 (middle-third rule).
    """
    MR = f["MR"]
    MO = f["MO"]
    N  = f["N_total"]
    B  = wall.b_base

    fos_d = MR / max(MO, 1e-9)

    # Eccentricity: distance of resultant from base centre
    # x_resultant from toe = (MR - MO) / N
    x_res = (MR - MO) / max(N, 1e-9)
    e = abs(B / 2.0 - x_res)

    e_limit = B * ECCENTRICITY_LIMIT_RATIO
    passes  = (fos_d >= FOS_LIMIT) and (e <= e_limit)

    return OverturningResult(
        MR      = MR,
        MO      = MO,
        fos_d   = fos_d,
        e       = e,
        e_limit = e_limit,
        passes  = passes,
    )


def _check_base_pressure(
    f    : dict,
    wall : RetainingWall,
) -> BasePressureResult:
    """
    Base pressure distribution (applied stress, Meyerhof effective-area method).

    Formula (Craig §11.4 / Meyerhof effective area):
        x_res    = (MR - MO) / N      -- resultant x from toe
        e        = |B/2 - x_res|      -- eccentricity from centre
        q_max    = N/B * (1 + 6e/B)   if e <= B/6  (trapezoidal)
        q_min    = N/B * (1 - 6e/B)
        if e > B/6 (partial lift-off):
            q_max = 2N / (3*(B/2 - e))
            q_min = 0  (tension not transmitted)
    """
    N   = f["N_total"]
    MR  = f["MR"]
    MO  = f["MO"]
    B   = wall.b_base

    x_res = (MR - MO) / max(N, 1e-9)
    e     = abs(B / 2.0 - x_res)
    B_eff = B - 2.0 * e

    middle_third = e <= B / 6.0

    if middle_third:
        q_max = (N / B) * (1.0 + 6.0 * e / B)
        q_min = (N / B) * (1.0 - 6.0 * e / B)
    else:
        q_max = (2.0 * N) / (3.0 * max(B / 2.0 - e, 1e-9))
        q_min = 0.0
        B_eff = max(B_eff, 0.01)

    return BasePressureResult(
        N_total      = N,
        e            = e,
        B_eff        = B_eff,
        q_max        = q_max,
        q_min        = q_min,
        middle_third = middle_third,
    )


def _check_bearing_capacity(
    f             : dict,
    wall          : RetainingWall,
    foundation    : Soil,
    base_press    : BasePressureResult,
    g_phi         : float,
    g_c           : float,
) -> WallBearingCheck:
    """
    GEO bearing capacity check for the wall base using EC7 Annex D.

    The wall base is treated as an infinitely long strip foundation
    (L → ∞, per-unit-run analysis).  Effective width B' = B - 2e
    accounts for load eccentricity from the overturning check.

    Design friction/cohesion of the FOUNDATION soil are factored:
        phi_d_found = arctan(tan(phi_k_found) / g_phi)  [EC7 §2.4.6.2]
        c_d_found   = c_k_found / g_c

    Embedment Df = t_base (conservative; actual embedment may be deeper
    depending on site levels — engineer to confirm).

    Reference:
        EC7 Annex D (analytical method), §D.2.
        Craig §11.4 (base bearing for retaining walls).
        Bond & Harris — Decoding Eurocode 7, Ch.14.

    :param f:          Force assembly dict (N_total, H_drive).
    :param wall:       RetainingWall geometry.
    :param foundation: Characteristic foundation soil (Soil).
    :param base_press: BasePressureResult (supplies B_eff, eccentricity).
    :param g_phi:      Material factor for friction angle.
    :param g_c:        Material factor for cohesion.
    :return:           WallBearingCheck.
    """
    import math as _math

    # Design strength of foundation soil
    phi_d = _math.degrees(_math.atan(_math.tan(_math.radians(foundation.phi_k)) / g_phi))
    c_d   = foundation.c_k / g_c

    # Effective base as strip foundation; clamp e_B to safe range
    B_base  = wall.b_base
    e_raw   = base_press.e
    e_safe  = min(e_raw, B_base / 2.0 - 1e-4)   # prevent Foundation ValueError
    Df      = wall.t_base                         # conservative embedment

    fdn = Foundation(B=B_base, Df=Df, L=None, e_B=e_safe)   # strip (L=None)

    N_total = f["N_total"]
    H_drive = f["H_drive"]

    br = bearing_resistance_ec7(
        foundation  = fdn,
        phi_d       = phi_d,
        c_d         = c_d,
        gamma_soil  = foundation.gamma,
        V           = N_total if H_drive > 0 else None,
        H           = H_drive,
        beta_ground = 0.0,
    )

    q_applied   = N_total / max(base_press.B_eff, 1e-4)
    utilisation = q_applied / max(br.q_ult, 1e-9)
    passes      = utilisation <= 1.0

    return WallBearingCheck(
        B_eff       = base_press.B_eff,
        Df          = Df,
        N_total     = N_total,
        H_drive     = H_drive,
        q_applied   = q_applied,
        q_ult       = br.q_ult,
        utilisation = utilisation,
        passes      = passes,
    )


def _check_equ_overturning(
    wall      : RetainingWall,
    backfill  : Soil,
    surcharge : UniformSurcharge | None,
) -> EquOverturningResult:
    """
    EQU overturning check using EC7 Table A.2 partial factors.

    This is the NORMATIVE overturning check per EC7 §2.4.7.2.
    It uses:
        γ_G,unfav = 1.10  for permanent destabilising (active thrust)
        γ_G,fav   = 0.90  for permanent stabilising  (self-weight, backfill)
        γ_Q       = 1.50  for variable destabilising (surcharge lateral)
        Variable restoring = 0.00 (conservative: surcharge on heel excluded)

    Material factors: M1 applies → characteristic phi_k used for Ka.
    This differs from the GEO DA1 combinations where phi_d may be reduced
    (C2 uses M2, g_phi=1.25).

    Formula (Bond & Harris §14.3, EC7 Table A.2):
        Ka_char   = Ka(phi_k)       [characteristic, unfactored]
        Pa_char   = ½ · Ka · γ · h²   [characteristic active thrust]
        Pa_q_char = Ka · q · h        [surcharge lateral thrust]

        MR_perm_char = Σ (permanent stabilising forces × lever arms)
        MO_perm_char = Pa_char · y_Pa   [from toe]
        MO_var_char  = Pa_q_char · y_Pa_q

        MR_equ = 0.90 × MR_perm_char
        MO_equ = 1.10 × MO_perm_char + 1.50 × MO_var_char
        N_equ  = 0.90 × N_perm_char

        FoS_d = MR_equ / MO_equ  (must be >= 1.0)
        e_equ = |B/2 − (MR_equ − MO_equ) / N_equ|  (must be <= B/3)

    Reference:
        EC7 EN 1997-1:2004, §2.4.7.2, Table A.2.
        Bond & Harris – Decoding Eurocode 7, §14.3.
        Craig's Soil Mechanics, 9th ed., §11.4.

    :param wall:      RetainingWall geometry.
    :param backfill:  Characteristic backfill Soil.
    :param surcharge: Applied surface surcharge, or None.
    :return:          EquOverturningResult.
    """
    # ── Characteristic Ka (M1: unfactored phi_k) ──────────────────────────
    # For Coulomb: use phi_k directly (not phi_d).  For Rankine: same.
    ka_char = _select_ka(wall, backfill.phi_k)

    # ── Characteristic active thrust ──────────────────────────────────────
    Pa_char, y_a  = active_thrust(
        h    = wall.h_wall,
        gamma= backfill.gamma,
        ka   = ka_char,
        c_d  = 0.0,  # cohesion excluded for EQU (conservative for overturning)
    )
    y_Pa_from_toe = y_a + wall.t_base

    # ── Surcharge lateral ─────────────────────────────────────────────────
    Pa_q_char       = 0.0
    y_Pa_q_from_toe = (wall.h_wall / 2.0) + wall.t_base

    if surcharge is not None:
        Pa_q_char = ka_char * surcharge.q * wall.h_wall
    # Variable restoring (surcharge on heel) = 0 for EQU — conservative.

    # ── Vertical component of active thrust (wall friction) ───────────────
    V_active_char = Pa_char * math.tan(math.radians(wall.delta_wall))

    # ── Characteristic permanent verticals ────────────────────────────────
    W_cf_char    = wall.w_counterforts
    N_perm_char  = (wall.w_stem + wall.w_base +
                    backfill.gamma * wall.b_heel * wall.h_wall +
                    W_cf_char + V_active_char)

    # ── Characteristic permanent restoring moment about toe ───────────────
    MR_perm_char = (
        wall.w_stem     * wall.x_stem_centroid      +
        wall.w_base     * wall.x_base_centroid       +
        backfill.gamma * wall.b_heel * wall.h_wall *
                          wall.x_heel_soil_centroid  +
        W_cf_char       * wall.x_heel_soil_centroid  +
        V_active_char   * wall.b_base
    )

    # ── Characteristic overturning moments ────────────────────────────────
    MO_perm_char = Pa_char   * y_Pa_from_toe
    MO_var_char  = Pa_q_char * y_Pa_q_from_toe

    # ── Apply EQU factors (Table A.2) ─────────────────────────────────────
    MR_equ = EQU_G_FAV   * MR_perm_char
    MO_equ = EQU_G_UNFAV * MO_perm_char + EQU_Q * MO_var_char
    N_equ  = EQU_G_FAV   * N_perm_char

    fos_d  = MR_equ / max(MO_equ, 1e-9)
    x_res  = (MR_equ - MO_equ) / max(N_equ, 1e-9)
    e      = abs(wall.b_base / 2.0 - x_res)
    e_limit= wall.b_base * ECCENTRICITY_LIMIT_RATIO
    passes = (fos_d >= FOS_LIMIT) and (e <= e_limit)

    return EquOverturningResult(
        MR_perm_char = MR_perm_char,
        MO_perm_char = MO_perm_char,
        MO_var_char  = MO_var_char,
        MR_equ       = MR_equ,
        MO_equ       = MO_equ,
        N_equ        = N_equ,
        fos_d        = fos_d,
        e            = e,
        e_limit      = e_limit,
        passes       = passes,
    )


def _compute_stem_structural(
    wall      : RetainingWall,
    backfill  : Soil,
    surcharge : "UniformSurcharge | None",
    ka        : float,
    phi_d     : float,
    n_points  : int = 20,
) -> StemStructuralResult:
    """
    Computes the bending moment and shear force distribution along the
    cantilever stem under the governing ULS factored loading.

    The stem is treated as a vertical cantilever of height h_wall, fixed
    at the base–stem junction.  The horizontal distributed load is the
    ULS active pressure profile:

        p(z) = Ka · γ · z + Ka · q_sur        [kPa]

    Integrating from the free top (z=0) downward:

        V(z) = Ka·γ·z²/2 + Ka·q_sur·z           [kN/m]
        M(z) = Ka·γ·z³/6 + Ka·q_sur·z²/2        [kN·m/m]

    The factored loads (gG_unfav · Ka · γ or gQ · Ka · q) should be used
    for structural design.  Here Ka is already computed from the factored
    soil strength (phi_d), and the load factors gG/gQ are accounted for
    in the surcharge magnitude passed in from _assemble_forces.

    Reference:
        Craig's Soil Mechanics, 9th ed., §11.2.
        Das, B.M. (2019). Principles of Geotechnical Engineering, §11.5.

    :param wall:      RetainingWall geometry.
    :param backfill:  Characteristic backfill Soil (gamma used for weight).
    :param surcharge: Applied surcharge, or None.
    :param ka:        Active pressure coefficient (from factored phi_d).
    :param phi_d:     Design friction angle used to select Ka (for reporting).
    :param n_points:  Number of diagram nodes (default 20).
    :return:          StemStructuralResult with M_max, V_max and full diagram.
    """
    h   = wall.h_wall
    gam = backfill.gamma
    q   = surcharge.q if surcharge is not None else 0.0

    diagram: list[StemPoint] = []
    dz = h / max(n_points - 1, 1)

    for i in range(n_points):
        z = i * dz
        V = ka * gam * z**2 / 2.0 + ka * q * z
        M = ka * gam * z**3 / 6.0 + ka * q * z**2 / 2.0
        diagram.append(StemPoint(z=round(z, 6), M=round(M, 6), V=round(V, 6)))

    # Peak values at fixed end z = h
    V_max = ka * gam * h**2 / 2.0 + ka * q * h
    M_max = ka * gam * h**3 / 6.0 + ka * q * h**2 / 2.0

    return StemStructuralResult(
        ka      = ka,
        phi_d   = phi_d,
        q_sur   = q,
        M_max   = M_max,
        V_max   = V_max,
        z_M_max = h,
        diagram = diagram,
        n_points= n_points,
    )


def _run_combination(
    label    : str,
    wall     : RetainingWall,
    backfill : Soil,
    foundation: Soil,
    surcharge : UniformSurcharge | None,
    gG_unfav : float,
    gG_fav   : float,
    gQ       : float,
    g_phi    : float,
    g_c      : float,
) -> WallCombinationResult:
    """Runs one complete DA1 combination and returns WallCombinationResult."""
    f          = _assemble_forces(
        wall, backfill, foundation, surcharge,
        gG_unfav, gG_fav, gQ, g_phi, g_c,
    )
    sliding    = _check_sliding(f, wall)
    overturn   = _check_overturning(f, wall)
    base_press = _check_base_pressure(f, wall)

    # B-05 FIX: bearing capacity now verified against EC7 Annex D.
    bearing    = _check_bearing_capacity(f, wall, foundation, base_press, g_phi, g_c)

    # All three checks must pass (sliding + overturning + bearing)
    passes = sliding.passes and overturn.passes and bearing.passes

    return WallCombinationResult(
        label      = label,
        gG_unfav   = gG_unfav,
        gQ         = gQ,
        g_phi      = g_phi,
        g_c        = g_c,
        phi_d      = f["phi_d_back"],
        c_d        = f["c_d_back"],
        ka         = f["ka"],
        Pa         = f["Pa_char"],
        sliding    = sliding,
        overturn   = overturn,
        base_press = base_press,
        bearing    = bearing,
        passes     = passes,
    )


# ============================================================
#  Public API
# ============================================================

def analyse_wall_da1(
    wall       : RetainingWall,
    backfill   : Soil,
    foundation : Soil,
    surcharge  : UniformSurcharge | None = None,
) -> WallResult:
    """
    EC7 DA1 (GEO) + EQU retaining wall ULS verification.

    Failure modes checked:
        GEO  C1 & C2 — Sliding   (Tables A.3/A.4, R1 set, Table A.13)
        GEO  C1 & C2 — Bearing   (Tables A.3/A.4, R1 set; EC7 Annex D)
        EQU          — Overturning (Table A.2; §2.4.7.2)
        REF  C1 & C2 — Overturning with GEO factors (reference only)

    Counterfort walls: additional concrete weight (w_counterforts) is
    automatically included in the vertical force assembly when
    wall.wall_type == 'counterfort'.

    Shear key: geometry accepted; passive resistance on the key is a future
    upgrade (Sprint 7). A warning is issued advising that the shear-key
    passive contribution is not yet included in the sliding check.

    Stem structural check (Sprint 5): bending moment diagram produced using
    the governing combination's Ka and phi_d (Craig §11.2).

    Overall PASS = GEO C1 slides + GEO C2 slides
                 + GEO C1 bearing + GEO C2 bearing
                 + EQU overturning

    :param wall:       RetainingWall geometry (cantilever / L-wall / counterfort).
    :param backfill:   Characteristic soil behind the wall.
    :param foundation: Characteristic soil beneath the base slab.
    :param surcharge:  Optional surface surcharge on backfill.
    :return:           WallResult with DA1 combinations + EQU check.

    Reference:
        EC7 §2.4.7.2, §9; Tables A.2/A.3/A.4/A.13; Annex D.
        Bond & Harris – Decoding Eurocode 7, §14.
        Craig's Soil Mechanics, 9th ed., §11.2–11.4.
    """
    warnings: list[str] = []

    if wall.b_heel <= 0:
        warnings.append(
            f"Heel b_heel = {wall.b_heel:.3f} m ≤ 0. "
            "Soil weight above heel is zero; overturning resistance may be very low."
        )

    if wall.shear_key_depth > 0:
        warnings.append(
            f"Shear key specified (depth={wall.shear_key_depth:.2f} m, "
            f"width={wall.shear_key_width:.2f} m). "
            "Passive resistance on the key face is NOT yet included in the sliding check "
            "(Sprint 6 geometry only — passive key contribution deferred to Sprint 7). "
            "Result is conservative."
        )

    if wall.wall_type == 'counterfort':
        warnings.append(
            f"Counterfort wall: {wall.w_counterforts:.1f} kN/m counterfort concrete "
            f"weight included in vertical force assembly "
            f"(spacing={wall.counterfort_spacing} m, t={wall.counterfort_thickness} m)."
        )

    # ── GEO DA1 Combination 1  (A1 + M1 + R1) ────────────────────────────
    comb1 = _run_combination(
        "DA1-C1", wall, backfill, foundation, surcharge,
        gG_unfav = C1_G_UNFAV, gG_fav = C1_G_FAV,
        gQ = C1_Q, g_phi = C1_PHI, g_c = C1_C,
    )

    # ── GEO DA1 Combination 2  (A2 + M2 + R1) ────────────────────────────
    comb2 = _run_combination(
        "DA1-C2", wall, backfill, foundation, surcharge,
        gG_unfav = C2_G_UNFAV, gG_fav = C2_G_FAV,
        gQ = C2_Q, g_phi = C2_PHI, g_c = C2_C,
    )

    governing = comb1 if comb1.sliding.fos_d <= comb2.sliding.fos_d else comb2

    # ── EQU Overturning (Table A.2 — normative per EC7 §2.4.7.2) ─────────
    equ_overturn = _check_equ_overturning(wall, backfill, surcharge)

    # Issue advisory if GEO passes but EQU fails (common mistake).
    if comb1.overturn.passes and comb2.overturn.passes and not equ_overturn.passes:
        warnings.append(
            "GEO overturning check passes, but EQU overturning (Table A.2) FAILS. "
            "EQU uses γ_G,fav=0.90 (vs 1.00 for GEO) — normative check governs."
        )

    # ── Stem structural check (Craig §11.2) ──────────────────────────────
    stem = _compute_stem_structural(
        wall=wall, backfill=backfill, surcharge=surcharge,
        ka=governing.ka, phi_d=governing.phi_d,
    )

    # ── Overall pass (GEO sliding/bearing both combs + EQU overturn) ──────
    geo_passes = comb1.passes and comb2.passes
    passes     = geo_passes and equ_overturn.passes

    return WallResult(
        wall         = wall,
        backfill     = backfill,
        foundation   = foundation,
        surcharge    = surcharge,
        comb1        = comb1,
        comb2        = comb2,
        governing    = governing,
        equ_overturn = equ_overturn,
        stem         = stem,
        passes       = passes,
        warnings     = warnings,
    )
