"""
bearing_capacity.py -- EC7 Annex D bearing resistance for spread foundations.

Implements the EC7 Annex D analytical method for ultimate bearing resistance
of spread foundations on drained (c-phi) and undrained (phi=0) soils.

EC7 Annex D general formula (D.2):
    R/A' = c'*Nc*sc*ic*bc*gc
         + q*Nq*sq*iq*bq*gq
         + 0.5*gamma'*B'*Ngamma*sgamma*igamma*bgamma*ggamma

    R  = bearing resistance (kN for pad, kN/m for strip)
    A' = B'*L' = effective area (m^2 for pad, m for strip per unit run)
    q  = effective overburden at foundation level = gamma_soil * Df  (kPa)
    gamma' = effective unit weight of soil below foundation (kPa/m)

Bearing capacity factors (EC7 Annex D.3):
    Nq     = exp(pi * tan(phi')) * tan^2(45 + phi'/2)
    Nc     = (Nq - 1) * cot(phi')   [phi' > 0]
    Nc     = pi + 2 = 5.14           [phi' = 0, Prandtl limit]
    Ngamma = 2 * (Nq - 1) * tan(phi')

Shape factors (EC7 Annex D.4, rectangle B' <= L'):
    sq     = 1 + (B'/L') * sin(phi')
    sgamma = 1 - 0.3 * (B'/L')
    sc     = (sq*Nq - 1) / (Nq - 1)   [phi' > 0]
    sc     = 1 + 0.2 * (B'/L')         [phi' = 0]
    For strip (B'/L' -> 0): sq = sgamma = sc = 1.0 (no shape correction).

Inclination factors (EC7 Annex D.5):
    m = (2 + B'/L') / (1 + B'/L')   [H acts in B'-direction]
    iq     = (1 - H/(V + A'*c'*cot(phi')))^m
    igamma = (1 - H/(V + A'*c'*cot(phi')))^(m+1)
    ic     = iq - (1 - iq) / (Nc * tan(phi'))
    For vertical load (H = 0): iq = igamma = ic = 1.0.

Base inclination factors (EC7 Annex D.6, base at angle alpha from horizontal):
    bq = bgamma = (1 - alpha * tan(phi'))^2   [alpha in radians]
    bc         = bq - (1 - bq) / (Nc * tan(phi'))
    For horizontal base (alpha = 0): bq = bgamma = bc = 1.0.

Ground inclination factors (EC7 Annex D.7, sloped ground at angle beta):
    gq = ggamma = (1 - tan(beta))^2
    gc         = gq - (1 - gq) / (Nc * tan(phi'))
    For horizontal ground (beta = 0): gq = ggamma = gc = 1.0.

Note on depth factors:
    EC7 Annex D does NOT include depth factors.  Depth factors (e.g. Hansen
    1970) are not part of the normative EC7 formula.  The overburden term
    q = gamma * Df accounts for embedment implicitly.

Reference:
    Eurocode 7 -- EN 1997-1:2004, Annex D (informative).
    Craig's Soil Mechanics, 9th ed., Chapter 8.
    Das, B.M. (2019). Principles of Geotechnical Engineering, Chapter 3.
    Bond, A. & Harris, A. (2008). Decoding Eurocode 7. Chapter 10.

Sign conventions:
    Compressive stresses positive (geotechnical convention).
    V = vertical component of design load on foundation (kN or kN/m).
    H = horizontal component of design load, in B-direction (kN or kN/m).
    Eccentricities e_B, e_L reduce effective dimensions B', L'.

Units:
    Lengths (m), forces (kN), pressures (kPa), unit weights (kN/m^3).
"""

import math
from dataclasses import dataclass, field

from models.foundation import Foundation


# ============================================================
#  Result containers
# ============================================================

@dataclass
class BearingFactors:
    """
    EC7 Annex D bearing capacity factors for a given design friction angle.

    Attributes
    ----------
    phi_d  : Design friction angle phi'_d (degrees).
    Nq     : Surcharge bearing factor.
    Nc     : Cohesion bearing factor.
    Ngamma : Self-weight bearing factor.
    """
    phi_d  : float
    Nq     : float
    Nc     : float
    Ngamma : float

    def __repr__(self) -> str:
        return (
            f"BearingFactors(phi_d={self.phi_d:.2f}deg, "
            f"Nq={self.Nq:.3f}, Nc={self.Nc:.3f}, Ngamma={self.Ngamma:.3f})"
        )


@dataclass
class BearingResult:
    """
    EC7 Annex D ultimate bearing resistance for one foundation/loading case.

    Attributes
    ----------
    R_ult      : Ultimate bearing resistance (kN/m for strip, kN for pad/raft).
    q_ult      : Ultimate bearing pressure R_ult / A_eff (kPa).
    q_net      : Net bearing pressure = q_ult - q_overburden (kPa).
    A_eff      : Effective bearing area (m for strip, m^2 for pad).
    factors    : BearingFactors used.
    phi_d      : Design friction angle applied (degrees).
    c_d        : Design cohesion applied (kPa).
    q_overburden: Effective overburden at foundation level (kPa).
    B_eff      : Effective width B' (m).
    L_eff      : Effective length L' (m, or None for strip).
    sc, sq, sg : Shape factors applied.
    ic, iq, ig : Inclination factors applied.
    bc, bq, bg : Base inclination factors applied.
    gc, gq, gg : Ground inclination factors applied.
    """
    R_ult        : float
    q_ult        : float
    q_net        : float
    A_eff        : float
    factors      : BearingFactors
    phi_d        : float
    c_d          : float
    q_overburden : float
    B_eff        : float
    L_eff        : float | None
    sc           : float
    sq           : float
    sg           : float
    ic           : float
    iq           : float
    ig           : float
    bc           : float
    bq           : float
    bg           : float
    gc           : float
    gq           : float
    gg           : float

    def summary(self) -> str:
        L_str = f"{self.L_eff:.3f} m" if self.L_eff is not None else "strip (inf)"
        return (
            f"  B'={self.B_eff:.3f} m   L'={L_str}   A'={self.A_eff:.4f}\n"
            f"  phi_d={self.phi_d:.2f} deg   c_d={self.c_d:.2f} kPa\n"
            f"  {self.factors}\n"
            f"  Shape : sc={self.sc:.4f}  sq={self.sq:.4f}  sg={self.sg:.4f}\n"
            f"  Incl  : ic={self.ic:.4f}  iq={self.iq:.4f}  ig={self.ig:.4f}\n"
            f"  Base  : bc={self.bc:.4f}  bq={self.bq:.4f}  bg={self.bg:.4f}\n"
            f"  Ground: gc={self.gc:.4f}  gq={self.gq:.4f}  gg={self.gg:.4f}\n"
            f"  q_overburden = {self.q_overburden:.2f} kPa\n"
            f"  q_ult  = {self.q_ult:.2f} kPa   (R_ult = {self.R_ult:.2f})\n"
            f"  q_net  = {self.q_net:.2f} kPa"
        )


# ============================================================
#  1.  Bearing capacity factors  (EC7 Annex D.3)
# ============================================================

def bearing_factors_ec7(phi_d: float) -> BearingFactors:
    """
    EC7 Annex D bearing capacity factors for design friction angle phi'_d.

    Formulae (EC7 Annex D.3):
        Nq     = exp(pi * tan(phi'_d)) * tan^2(45 + phi'_d/2)
        Nc     = (Nq - 1) * cot(phi'_d)          [phi'_d > 0]
        Nc     = pi + 2 = 5.14159...               [phi'_d = 0, Prandtl]
        Ngamma = 2 * (Nq - 1) * tan(phi'_d)

    :param phi_d: Design friction angle phi'_d (degrees).  Must be in [0, 45).
    :return:      BearingFactors dataclass.
    :raises ValueError: If phi_d is out of [0, 45).
    """
    if not (0.0 <= phi_d < 45.0):
        raise ValueError(f"phi_d must be in [0, 45), got {phi_d}")

    phi_r = math.radians(phi_d)

    Nq = math.exp(math.pi * math.tan(phi_r)) * math.tan(math.radians(45.0 + phi_d / 2.0)) ** 2

    if phi_d < 1e-6:   # undrained, phi = 0
        Nc     = math.pi + 2.0   # Prandtl limit: 5.14159
        Ngamma = 0.0
    else:
        Nc     = (Nq - 1.0) / math.tan(phi_r)   # (Nq-1)*cot(phi)
        Ngamma = 2.0 * (Nq - 1.0) * math.tan(phi_r)

    return BearingFactors(phi_d=phi_d, Nq=Nq, Nc=Nc, Ngamma=Ngamma)


# ============================================================
#  2.  Shape factors  (EC7 Annex D.4)
# ============================================================

def _shape_factors(aspect: float, phi_d: float, Nq: float, Nc: float) -> tuple[float, float, float]:
    """
    EC7 Annex D shape factors (sc, sq, sgamma) for a rectangle B'<=L'.

    Formulae (EC7 Annex D.4):
        sq     = 1 + (B'/L') * sin(phi')
        sgamma = 1 - 0.3 * (B'/L')
        sc     = (sq*Nq - 1) / (Nq - 1)   [phi' > 0]
        sc     = 1 + 0.2 * (B'/L')         [phi' = 0]

    :param aspect: B_eff / L_eff (0 for strip, 1 for square).
    :param phi_d:  Design friction angle (degrees).
    :param Nq:     Nq bearing factor.
    :param Nc:     Nc bearing factor.
    :return:       Tuple (sc, sq, sgamma).
    """
    phi_r = math.radians(phi_d)
    sq     = 1.0 + aspect * math.sin(phi_r)
    sgamma = 1.0 - 0.3 * aspect

    if phi_d < 1e-6:   # phi = 0
        sc = 1.0 + 0.2 * aspect
    else:
        sc = (sq * Nq - 1.0) / (Nq - 1.0)

    return sc, sq, sgamma


# ============================================================
#  3.  Inclination factors  (EC7 Annex D.5)
# ============================================================

def _inclination_factors(
    H       : float,
    V       : float,
    A_eff   : float,
    c_d     : float,
    phi_d   : float,
    aspect  : float,
    Nc      : float,
) -> tuple[float, float, float]:
    """
    EC7 Annex D inclination factors (ic, iq, igamma).

    Formulae (EC7 Annex D.5):
        m  = (2 + B'/L') / (1 + B'/L')   [H acts in B'-direction]
        iq = (1 - H/(V + A'*c'*cot(phi')))^m
        ig = (1 - H/(V + A'*c'*cot(phi')))^(m+1)
        ic = iq - (1-iq)/(Nc*tan(phi'))   [phi' > 0]
        ic = 1 - m*H/(A'*c'*Nc)           [phi' = 0]

    :param H:      Horizontal force (kN or kN/m), acting in B'-direction.
    :param V:      Vertical force (kN or kN/m).
    :param A_eff:  Effective area (m for strip, m^2 for pad).
    :param c_d:    Design cohesion (kPa).
    :param phi_d:  Design friction angle (degrees).
    :param aspect: B_eff/L_eff (0 for strip).
    :param Nc:     Nc bearing factor.
    :return:       Tuple (ic, iq, igamma).
    :raises ValueError: If H/V combination is geometrically impossible.
    """
    if H < 0:
        raise ValueError(f"H must be >= 0, got {H}")
    if H == 0.0:
        return 1.0, 1.0, 1.0

    phi_r = math.radians(phi_d)

    # m factor: H acts in B'-direction (conservative; use larger m for H in L'-direction)
    m = (2.0 + aspect) / (1.0 + aspect)

    if phi_d < 1e-6:   # phi = 0
        denom_c = A_eff * c_d * Nc
        if denom_c < 1e-9:
            raise ValueError("phi=0 with c=0: undrained inclination factor undefined.")
        ic = 1.0 - m * H / denom_c
        ic = max(0.0, ic)
        return ic, 1.0, 0.0   # iq=1, igamma=0 for phi=0

    # Denominator for iq, ig: V + A'*c'*cot(phi')
    cot_phi = 1.0 / math.tan(phi_r)
    denom   = V + A_eff * c_d * cot_phi
    if denom < 1e-9:
        raise ValueError("V + A'*c'*cot(phi') = 0: inclination factor undefined.")

    ratio = H / denom
    if ratio > 1.0:
        raise ValueError(
            f"H/denom = {ratio:.4f} > 1 — impossible loading: "
            f"H={H:.2f} exceeds sliding resistance V + A'c'cotφ = {denom:.2f}."
        )

    iq     = (1.0 - ratio) ** m
    igamma = (1.0 - ratio) ** (m + 1.0)
    ic     = iq - (1.0 - iq) / (Nc * math.tan(phi_r))
    ic     = max(0.0, ic)

    return ic, iq, igamma


# ============================================================
#  4.  Base inclination factors  (EC7 Annex D.6)
# ============================================================

def _base_inclination_factors(
    alpha : float,
    phi_d : float,
    Nc    : float,
) -> tuple[float, float, float]:
    """
    EC7 Annex D base inclination factors for a base tilted at angle alpha.

    Formulae (EC7 Annex D.6):
        bq = bgamma = (1 - alpha * tan(phi'))^2   [alpha in radians]
        bc         = bq - (1 - bq) / (Nc * tan(phi'))

    :param alpha: Base inclination from horizontal (degrees).
    :param phi_d: Design friction angle (degrees).
    :param Nc:    Nc bearing factor.
    :return:      Tuple (bc, bq, bgamma).
    """
    if alpha == 0.0:
        return 1.0, 1.0, 1.0

    alpha_r = math.radians(alpha)
    phi_r   = math.radians(phi_d)

    bq     = (1.0 - alpha_r * math.tan(phi_r)) ** 2
    bgamma = bq

    if phi_d < 1e-6:
        bc = 1.0 - 2.0 * alpha_r / (math.pi + 2.0)
    else:
        bc = bq - (1.0 - bq) / (Nc * math.tan(phi_r))

    bc = max(0.0, bc)
    return bc, bq, bgamma


# ============================================================
#  5.  Ground inclination factors  (EC7 Annex D.7)
# ============================================================

def _ground_inclination_factors(
    beta  : float,
    phi_d : float,
    Nc    : float,
) -> tuple[float, float, float]:
    """
    EC7 Annex D ground inclination factors for a sloped ground surface.

    Formulae (EC7 Annex D.7):
        gq = ggamma = (1 - tan(beta))^2
        gc         = gq - (1 - gq) / (Nc * tan(phi'))

    :param beta:  Ground slope angle from horizontal (degrees).  0 = flat.
    :param phi_d: Design friction angle (degrees).
    :param Nc:    Nc bearing factor.
    :return:      Tuple (gc, gq, ggamma).
    """
    if beta == 0.0:
        return 1.0, 1.0, 1.0

    beta_r = math.radians(beta)
    phi_r  = math.radians(phi_d)

    gq     = (1.0 - math.tan(beta_r)) ** 2
    ggamma = gq

    if phi_d < 1e-6:
        gc = 1.0 - 2.0 * beta_r / (math.pi + 2.0)
    else:
        gc = gq - (1.0 - gq) / (Nc * math.tan(phi_r))

    gc = max(0.0, gc)
    return gc, gq, ggamma


# ============================================================
#  6.  Public API: bearing_resistance_ec7
# ============================================================

def bearing_resistance_ec7(
    foundation    : Foundation,
    phi_d         : float,
    c_d           : float,
    gamma_soil    : float,
    V             : float | None = None,
    H             : float        = 0.0,
    beta_ground   : float        = 0.0,
) -> BearingResult:
    """
    EC7 Annex D ultimate bearing resistance for a spread foundation.

    Applies the full EC7 Annex D formula (D.2) including all correction factors:
        R/A' = c'*Nc*sc*ic*bc*gc
             + q*Nq*sq*iq*bq*gq
             + 0.5*gamma'*B'*Ngamma*sgamma*igamma*bgamma*ggamma

    The effective overburden q = gamma_soil * Df (free-field stress at foundation
    level, positive downward).  gamma_soil is used both for q and for the
    self-weight term (gamma' = gamma_soil; a separate gamma_w term for
    submerged conditions is not included here -- pass buoyant weight directly).

    :param foundation:   Foundation geometry (Foundation object).
    :param phi_d:        Design friction angle phi'_d (degrees).  [0, 45).
    :param c_d:          Design cohesion c'_d (kPa).  >= 0.
    :param gamma_soil:   Effective unit weight of soil below foundation (kN/m^3).
    :param V:            Vertical design load on foundation (kN for pad, kN/m for
                         strip).  If None, not used in inclination factors (H must
                         also be 0 in that case).
    :param H:            Horizontal design load in B-direction (kN or kN/m).
                         Default 0 (vertical loading).
    :param beta_ground:  Ground surface slope angle from horizontal (degrees).
                         Default 0 (horizontal ground).
    :return:             BearingResult with full factor breakdown.
    :raises ValueError:  If any parameter is out of range.
    """
    if phi_d < 0 or phi_d >= 45.0:
        raise ValueError(f"phi_d must be in [0, 45), got {phi_d}")
    if c_d < 0:
        raise ValueError(f"c_d must be >= 0, got {c_d}")
    if gamma_soil <= 0:
        raise ValueError(f"gamma_soil must be > 0, got {gamma_soil}")
    if H < 0:
        raise ValueError(f"H must be >= 0, got {H}")
    if H > 0 and V is None:
        raise ValueError("V must be provided when H > 0 (needed for inclination factors).")

    # ── Bearing capacity factors ─────────────────────────────────────────
    bf = bearing_factors_ec7(phi_d)
    Nq, Nc, Ng = bf.Nq, bf.Nc, bf.Ngamma

    # ── Foundation effective dimensions ──────────────────────────────────
    B_eff  = foundation.B_eff
    L_eff  = foundation.L_eff
    A_eff  = foundation.A_eff
    aspect = foundation.aspect    # B'/L' (0 for strip)

    # ── Overburden at foundation level ───────────────────────────────────
    q = gamma_soil * foundation.Df

    # ── Correction factors ───────────────────────────────────────────────
    sc, sq, sg = _shape_factors(aspect, phi_d, Nq, Nc)

    V_for_incl = V if V is not None else 0.0
    ic, iq, ig = _inclination_factors(H, V_for_incl, A_eff, c_d, phi_d, aspect, Nc)

    bc, bq, bg = _base_inclination_factors(foundation.alpha, phi_d, Nc)
    gc, gq, gg = _ground_inclination_factors(beta_ground, phi_d, Nc)

    # ── EC7 Annex D.2 bearing pressure ───────────────────────────────────
    term_c = c_d  * Nc * sc * ic * bc * gc
    term_q = q    * Nq * sq * iq * bq * gq
    term_g = 0.5  * gamma_soil * B_eff * Ng * sg * ig * bg * gg

    q_ult = term_c + term_q + term_g
    q_net = q_ult - q          # net = gross minus overburden
    R_ult = q_ult * A_eff

    return BearingResult(
        R_ult        = R_ult,
        q_ult        = q_ult,
        q_net        = q_net,
        A_eff        = A_eff,
        factors      = bf,
        phi_d        = phi_d,
        c_d          = c_d,
        q_overburden = q,
        B_eff        = B_eff,
        L_eff        = L_eff,
        sc=sc, sq=sq, sg=sg,
        ic=ic, iq=iq, ig=ig,
        bc=bc, bq=bq, bg=bg,
        gc=gc, gq=gq, gg=gg,
    )
