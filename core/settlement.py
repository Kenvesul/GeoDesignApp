"""
settlement.py -- Foundation settlement calculations (EC7 Section 6).

Implements three settlement components:
    1. Immediate (elastic) settlement   -- granular soils or short-term in clay
    2. Primary consolidation settlement -- cohesive soils (Terzaghi method)
    3. Time-rate of consolidation       -- Terzaghi 1D theory (Cv method)

EC7 Section 6 defines the SLS criterion:
    s_d <= s_lim   (design settlement <= serviceability limit)
Typical limits (EC7 Table A.2, and CIRIA C580):
    Isolated foundations: s_lim = 25 mm (total), delta/L = 1/300 (differential)
    Raft foundations:     s_lim = 50 mm

Immediate settlement formula (Das 2019 §11.5 / Steinbrenner 1934):

    s_i = q_net · B' · (1 − ν²) / E_s · I_s · rigid_factor

    where B' = B/2 (half-width for centre-point computation using the
    Steinbrenner double-rectangle superposition, Das Eq 11.21).

    I_s = F₁ + (1−2ν)/(1−ν) · F₂   (Steinbrenner 1934 / Das Eqs 11.22–11.23)

    F₁ = (1/π) · { m₁·ln[(1+√(m₁²+1))·√(m₁²+n₁²) / (m₁·√(m₁²+n₁²+1))]
                  + ln[(m₁+√(m₁²+1))·√(1+n₁²) / √(m₁²+n₁²+1)] }

    F₂ = (n₁/2π) · arctan( m₁ / (n₁·√(m₁²+n₁²+1)) )

    with  m₁ = L/B    (foundation aspect ratio, L ≥ B)
          n₁ = 2H/B   (depth ratio, H = depth to rigid stratum or ∞)

    For H → ∞:  F₂ → 0,  I_s → F₁ (depth-invariant).

    Rigid-foundation correction: multiply by 0.80 (Bowles 1996, §5.3,
    based on Timoshenko & Goodier solution for rigid circular foundation).

    Backward-compatible: if I_s is supplied explicitly, the legacy formula
        s_i = q_net · B · (1 − ν²) / E_s · I_s · rigid_factor
    is used instead (original behaviour).

Primary consolidation (Terzaghi Cc / Cs method):
    NC clay:  s_c = Cc * H / (1 + e0) * log10((sigma_v0 + delta_sigma) / sigma_v0)
    OC clay (sigma_vf <= sigma_pc):
              s_c = Cs * H / (1 + e0) * log10((sigma_v0 + delta_sigma) / sigma_v0)
    OC clay (sigma_vf > sigma_pc, crossing yield):
              s_c = Cs*H/(1+e0)*log10(sigma_pc/sigma_v0)
                  + Cc*H/(1+e0)*log10((sigma_v0+delta_sigma)/sigma_pc)

Time-rate (Terzaghi 1D, EC7 Annex A reference / Das Chapter 7):
    U = degree of consolidation (0 to 1).
    Tv = time factor (dimensionless).
    t  = Tv * H_dr^2 / cv

    Tv approximation (Terzaghi, widely reproduced, e.g. Das §11.8):
        U <= 0.60: Tv = (pi/4) * U^2
        U >  0.60: Tv = 1.781 - 0.933 * log10(100 * (1 - U))  [Carman-Kozeny fit]

Reference:
    Eurocode 7 -- EN 1997-1:2004, Section 6 (Spread foundations, SLS).
    Terzaghi, K. (1943). Theoretical Soil Mechanics. Wiley.
    Das, B.M. (2019). Principles of Geotechnical Engineering, Chs 7 and 11.
    Craig's Soil Mechanics, 9th ed., Chapters 7 and 8.
    Bowles, J.E. (1996). Foundation Analysis and Design, 5th ed., Chapter 5.
    Steinbrenner, W. (1934). Tafeln zur Setzungsberechnung. Strasse 1, 121–124.

Sign conventions:
    All settlements positive downward (compression positive).
    Stresses: sigma_v0 = in-situ effective vertical stress (kPa, compressive +).
    delta_sigma = stress increase from foundation load (kPa, always >= 0).

Units:
    Lengths (m), settlements (m), times (years unless noted), stresses (kPa).
    cv units: m^2/year.
"""

import math
from dataclasses import dataclass


# ============================================================
#  Constants
# ============================================================

S_LIM_ISOLATED : float = 0.025   # 25 mm -- EC7 default SLS limit, isolated foundation
S_LIM_RAFT     : float = 0.050   # 50 mm -- EC7 default SLS limit, raft foundation


# ============================================================
#  Result containers
# ============================================================

@dataclass
class ImmediateSettlementResult:
    """
    Immediate (elastic) settlement result.

    Attributes
    ----------
    s_i          : Immediate settlement (m).
    q_net        : Net applied pressure (kPa).
    B            : Foundation width (m).
    L            : Foundation length (m).  None = legacy (square assumed).
    E_s          : Soil elastic modulus used (kPa).
    nu           : Poisson's ratio used.
    I_s          : Steinbrenner influence factor.
    rigid_factor : Rigidity correction (0.8 for rigid, 1.0 for flexible).
    formula      : 'steinbrenner' (Das 2019, B'=B/2) or 'legacy' (full B).
    """
    s_i          : float
    q_net        : float
    B            : float
    L            : float | None
    E_s          : float
    nu           : float
    I_s          : float
    rigid_factor : float
    formula      : str = "legacy"


@dataclass
class ConsolidationResult:
    """
    Primary consolidation settlement result (Terzaghi Cc/Cs method).

    Attributes
    ----------
    s_c         : Total consolidation settlement (m).
    s_c_oc      : OC portion (Cs branch) of settlement (m).  0 for NC clay.
    s_c_nc      : NC portion (Cc branch) of settlement (m).
    H           : Layer thickness used (m).
    Cc          : Compression index.
    Cs          : Swelling/recompression index.
    e0          : Initial void ratio.
    sigma_v0    : Initial effective vertical stress (kPa).
    sigma_vf    : Final effective vertical stress (kPa).
    sigma_pc    : Preconsolidation pressure (kPa).
    is_nc       : True if NC clay (sigma_v0 >= sigma_pc, or sigma_pc not specified).
    """
    s_c      : float
    s_c_oc   : float
    s_c_nc   : float
    H        : float
    Cc       : float
    Cs       : float
    e0       : float
    sigma_v0 : float
    sigma_vf : float
    sigma_pc : float
    is_nc    : bool


@dataclass
class TimeSettlementResult:
    """
    Time-rate of consolidation result.

    Attributes
    ----------
    t          : Time to reach degree of consolidation U (years).
    U          : Target degree of consolidation (fraction, 0-1).
    Tv         : Time factor.
    H_dr       : Drainage path length (m).
    cv         : Coefficient of consolidation (m^2/year).
    """
    t    : float
    U    : float
    Tv   : float
    H_dr : float
    cv   : float


# ============================================================
#  Steinbrenner (1934) influence factor
# ============================================================

def Is_steinbrenner(
    L:         float,
    B:         float,
    nu:        float = 0.3,
    H_layer:   float = float("inf"),
) -> float:
    """
    Steinbrenner (1934) influence factor I_s for immediate settlement at the
    CENTRE of a flexible rectangular foundation L × B.

    This implements the formula from Das (2019) Eqs 11.22–11.23, using the
    B' = B/2 (half-width) convention.  The factor is used in:

        s_i = q_net · B' · (1 − ν²) / E_s · I_s · rigid_factor

    where B' = B/2 and m₁ = L/B, n₁ = 2·H/B.

    Formula (Steinbrenner 1934 / Das 2019 Eqs 11.22–11.23):

        F₁ = (1/π) · {
              m₁ · ln[(1+√(m₁²+1)) · √(m₁²+n₁²) / (m₁ · √(m₁²+n₁²+1))]
            + ln[(m₁+√(m₁²+1)) · √(1+n₁²) / √(m₁²+n₁²+1)]
        }

        F₂ = (n₁/2π) · arctan( m₁ / (n₁·√(m₁²+n₁²+1)) )

        I_s = F₁ + (1−2ν)/(1−ν) · F₂

    For H_layer → ∞:  n₁ → ∞, F₂ → 0, and I_s → F₁_∞ = (1/π)·{
        m₁·ln[(1+√(m₁²+1))/m₁] + ln[m₁+√(m₁²+1)] }.

    Reference:
        Das, B.M. (2019). Principles of Geotechnical Engineering, §11.5.
        Steinbrenner, W. (1934). Tafeln zur Setzungsberechnung.
        Bowles, J.E. (1996). Foundation Analysis and Design, 5th ed., Table 5-4.

    Typical values (centre, flexible, H→∞, ν=0.3):
        L/B=1.0:  I_s ≈ 0.56    (square)
        L/B=2.0:  I_s ≈ 0.76
        L/B=5.0:  I_s ≈ 0.96
        L/B→∞:    I_s → 1.12+   (strip, converges slowly)

    Note on convention: these I_s values are used with B' = B/2, which gives
    approximately HALF the settlement of the legacy formula that uses full B
    with I_s = 0.82.  The Das convention is more theoretically correct.

    :param L:        Foundation length (m). ≥ B > 0.
    :param B:        Foundation width  (m). > 0.
    :param nu:       Poisson's ratio of soil.  Default 0.3.  (0 < ν < 0.5)
    :param H_layer:  Depth to rigid stratum below foundation (m).
                     Use float('inf') for deep compressible layer (default).
    :return:         I_s (dimensionless, > 0).
    :raises ValueError: If parameters are out of range.
    """
    if B <= 0:
        raise ValueError(f"B must be > 0, got {B}")
    if L < B:
        # Enforce L ≥ B convention (swap silently)
        L, B = B, L
    if L <= 0:
        raise ValueError(f"L must be > 0, got {L}")
    if not (0.0 < nu < 0.5):
        raise ValueError(f"nu must be in (0, 0.5), got {nu}")
    if H_layer is not None and H_layer <= 0:
        raise ValueError(f"H_layer must be > 0 (or inf), got {H_layer}")

    m1 = L / B   # aspect ratio ≥ 1

    if math.isinf(H_layer):
        # Limiting form as n₁ → ∞
        # F₁_inf = (1/π) · { m₁·ln[(1+√(m₁²+1))/m₁] + ln[m₁+√(m₁²+1)] }
        sqrt_m2p1 = math.sqrt(m1 * m1 + 1.0)
        F1 = (1.0 / math.pi) * (
            m1 * math.log((1.0 + sqrt_m2p1) / m1)
            + math.log(m1 + sqrt_m2p1)
        )
        F2 = 0.0   # F₂ → 0 as n₁ → ∞

    else:
        # n₁ = 2H/B  (Das convention: H_layer measured below foundation base)
        n1 = 2.0 * H_layer / B

        m12  = m1 * m1
        n12  = n1 * n1
        m12n12 = m12 + n12

        sqrt_m2p1  = math.sqrt(m12 + 1.0)          # √(m₁²+1)
        sqrt_mn2   = math.sqrt(m12 + n12)           # √(m₁²+n₁²)
        sqrt_mn2p1 = math.sqrt(m12 + n12 + 1.0)    # √(m₁²+n₁²+1)
        sqrt_n2p1  = math.sqrt(1.0 + n12)           # √(1+n₁²)

        # F₁ — Eq 11.22 (Das 2019)
        term1 = m1 * math.log(
            (1.0 + sqrt_m2p1) * sqrt_mn2 / (m1 * sqrt_mn2p1)
        )
        term2 = math.log(
            (m1 + sqrt_m2p1) * sqrt_n2p1 / sqrt_mn2p1
        )
        F1 = (term1 + term2) / math.pi

        # F₂ — Eq 11.23 (Das 2019)
        if n1 > 0:
            F2 = (n1 / (2.0 * math.pi)) * math.atan(
                m1 / (n1 * sqrt_mn2p1)
            )
        else:
            F2 = 0.0

    # Combine: I_s = F₁ + (1-2ν)/(1-ν) · F₂
    factor_nu = (1.0 - 2.0 * nu) / (1.0 - nu)
    I_s = F1 + factor_nu * F2

    return max(I_s, 1e-9)   # guard against floating-point zero for degenerate cases


# ============================================================
#  1.  Immediate (elastic) settlement
# ============================================================

def immediate_settlement(
    q_net        : float,
    B            : float,
    E_s          : float,
    nu           : float        = 0.3,
    I_s          : float | None = None,
    rigid        : bool         = True,
    L            : float | None = None,
    H_layer      : float        = float("inf"),
) -> ImmediateSettlementResult:
    """
    Immediate (elastic) settlement of a spread foundation.

    Two formula modes
    -----------------
    **Steinbrenner mode** (recommended, Sprint 4):
        Called when ``L`` is supplied (foundation length) and ``I_s`` is None.
        Uses the Das (2019) / Steinbrenner (1934) formula with B' = B/2:

            s_i = q_net · (B/2) · (1 − ν²) / E_s · I_s · rigid_factor

        where I_s = Is_steinbrenner(L, B, nu, H_layer).

        This is more accurate than the legacy mode because I_s is computed
        from the actual foundation dimensions (L/B ratio) and depth to any
        rigid stratum (H_layer).

    **Legacy mode** (backward-compatible):
        Called when ``I_s`` is supplied explicitly, OR when L is None.
        Uses:
            s_i = q_net · B · (1 − ν²) / E_s · I_s · rigid_factor

        Default I_s = 0.82 (square, flexible, Terzaghi 1943 / Craig Table 8.1).

    Rigidity correction (both modes):
        Rigid foundation → multiply by 0.8  (Bowles 1996 §5.3, from the exact
        Timoshenko & Goodier (1951) solution for a rigid circular plate).
        Flexible foundation → factor = 1.0.

    Reference:
        Das, B.M. (2019). §11.5 (Steinbrenner formula with B' = B/2).
        Bowles, J.E. (1996). Table 5-4 (rigidity correction 0.8).
        Craig's Soil Mechanics, 9th ed., §8.3 (settlement overview).

    :param q_net:    Net applied pressure (kPa). = (total load / A) - γ·Df. ≥ 0.
    :param B:        Foundation width (m). > 0.
    :param E_s:      Soil Young's modulus (kPa). > 0.
    :param nu:       Poisson's ratio of soil. Default 0.3 (sand/gravel).
    :param I_s:      Steinbrenner shape factor (–).  Provide for legacy mode.
                     If None and L is given, I_s is computed automatically.
                     If None and L is None, defaults to 0.82 (square, legacy).
    :param rigid:    True = rigid foundation (factor 0.8), False = flexible.
    :param L:        Foundation length (m). If provided, triggers Steinbrenner
                     mode. L ≥ B; if L < B, B and L are swapped automatically.
    :param H_layer:  Depth to rigid stratum below foundation base (m).
                     Use float('inf') for deep compressible layer (default).
    :return:         ImmediateSettlementResult.
    :raises ValueError: If any parameter is out of range.
    """
    if q_net < 0:
        raise ValueError(f"q_net must be >= 0, got {q_net}")
    if B <= 0:
        raise ValueError(f"B must be > 0, got {B}")
    if E_s <= 0:
        raise ValueError(f"E_s must be > 0, got {E_s}")
    if not (0.0 < nu < 0.5):
        raise ValueError(f"nu (Poisson's ratio) must be in (0, 0.5), got {nu}")

    rigid_factor = 0.8 if rigid else 1.0

    if I_s is None and L is not None:
        # ── Steinbrenner mode (Das 2019, B' = B/2) ───────────────────────
        L_use = L
        if L_use < B:
            L_use, B = B, L_use   # enforce L ≥ B
        I_s_val = Is_steinbrenner(L_use, B, nu=nu, H_layer=H_layer)
        B_prime = B / 2.0         # Das Eq 11.21: use half-width for centre
        s_i     = q_net * B_prime * (1.0 - nu ** 2) / E_s * I_s_val * rigid_factor
        formula = "steinbrenner"
    else:
        # ── Legacy mode (full B, explicit or default I_s) ─────────────────
        I_s_val = I_s if I_s is not None else 0.82
        if I_s_val <= 0:
            raise ValueError(f"I_s must be > 0, got {I_s_val}")
        L_use   = L if L is not None else B   # square if not specified
        s_i     = q_net * B * (1.0 - nu ** 2) / E_s * I_s_val * rigid_factor
        formula = "legacy"

    return ImmediateSettlementResult(
        s_i          = s_i,
        q_net        = q_net,
        B            = B,
        L            = L_use,
        E_s          = E_s,
        nu           = nu,
        I_s          = I_s_val,
        rigid_factor = rigid_factor,
        formula      = formula,
    )


# ============================================================
#  2.  Primary consolidation settlement  (Terzaghi Cc/Cs method)
# ============================================================

def consolidation_settlement(
    H            : float,
    Cc           : float,
    e0           : float,
    sigma_v0     : float,
    delta_sigma  : float,
    Cs           : float = 0.0,
    sigma_pc     : float | None = None,
) -> ConsolidationResult:
    """
    Primary consolidation settlement using the Terzaghi Cc/Cs method.

    For normally consolidated clay (NC, sigma_v0 >= sigma_pc):
        s_c = Cc * H / (1 + e0) * log10((sigma_v0 + delta_sigma) / sigma_v0)

    For overconsolidated clay (OC, sigma_vf <= sigma_pc):
        s_c = Cs * H / (1 + e0) * log10((sigma_v0 + delta_sigma) / sigma_v0)

    For OC clay crossing the preconsolidation pressure (sigma_vf > sigma_pc):
        s_c = Cs * H/(1+e0) * log10(sigma_pc / sigma_v0)
            + Cc * H/(1+e0) * log10(sigma_vf / sigma_pc)

    Reference:
        Das, B.M. (2019), Principles of Geotechnical Engineering, §11.7.
        Craig's Soil Mechanics, 9th ed., §7.4.

    :param H:           Compressible layer thickness (m).  > 0.
    :param Cc:          Compression index (slope of e-log sigma_v NC branch).  > 0.
    :param e0:          Initial void ratio.  > 0.
    :param sigma_v0:    Initial effective vertical stress at mid-layer (kPa).  > 0.
    :param delta_sigma: Stress increase from foundation load (kPa).  >= 0.
    :param Cs:          Swelling/recompression index (OC branch).  Default 0.
                        Required for OC clay.
    :param sigma_pc:    Preconsolidation pressure (kPa).  None = NC clay.
    :return:            ConsolidationResult.
    :raises ValueError: If parameters are out of valid range.
    """
    if H <= 0:
        raise ValueError(f"H must be > 0, got {H}")
    if Cc <= 0:
        raise ValueError(f"Cc must be > 0, got {Cc}")
    if e0 <= 0:
        raise ValueError(f"e0 must be > 0, got {e0}")
    if sigma_v0 <= 0:
        raise ValueError(f"sigma_v0 must be > 0, got {sigma_v0}")
    if delta_sigma < 0:
        raise ValueError(f"delta_sigma must be >= 0, got {delta_sigma}")
    if Cs < 0:
        raise ValueError(f"Cs must be >= 0, got {Cs}")
    if sigma_pc is not None and sigma_pc <= 0:
        raise ValueError(f"sigma_pc must be > 0 if provided, got {sigma_pc}")

    sigma_vf = sigma_v0 + delta_sigma

    if delta_sigma == 0.0:
        return ConsolidationResult(
            s_c=0.0, s_c_oc=0.0, s_c_nc=0.0,
            H=H, Cc=Cc, Cs=Cs, e0=e0,
            sigma_v0=sigma_v0, sigma_vf=sigma_vf,
            sigma_pc=sigma_pc if sigma_pc else sigma_v0,
            is_nc=(sigma_pc is None or sigma_v0 >= sigma_pc),
        )

    prefactor = H / (1.0 + e0)

    # ── Determine consolidation state ────────────────────────────────────
    if sigma_pc is None or sigma_v0 >= sigma_pc:
        # NC clay: use Cc for the full stress increase
        s_c_nc = Cc * prefactor * math.log10(sigma_vf / sigma_v0)
        s_c_oc = 0.0
        s_c    = s_c_nc
        sp     = sigma_v0 if sigma_pc is None else sigma_pc
        is_nc  = True

    elif sigma_vf <= sigma_pc:
        # OC clay, stays overconsolidated: use Cs only
        s_c_oc = Cs * prefactor * math.log10(sigma_vf / sigma_v0)
        s_c_nc = 0.0
        s_c    = s_c_oc
        sp     = sigma_pc
        is_nc  = False

    else:
        # OC clay crossing preconsolidation: Cs up to sigma_pc, then Cc beyond
        s_c_oc = Cs * prefactor * math.log10(sigma_pc / sigma_v0)
        s_c_nc = Cc * prefactor * math.log10(sigma_vf  / sigma_pc)
        s_c    = s_c_oc + s_c_nc
        sp     = sigma_pc
        is_nc  = False

    return ConsolidationResult(
        s_c=s_c, s_c_oc=s_c_oc, s_c_nc=s_c_nc,
        H=H, Cc=Cc, Cs=Cs, e0=e0,
        sigma_v0=sigma_v0, sigma_vf=sigma_vf,
        sigma_pc=sp,
        is_nc=is_nc,
    )


# ============================================================
#  3.  Time-rate of consolidation  (Terzaghi 1D)
# ============================================================

def time_factor(U: float) -> float:
    """
    Terzaghi time factor Tv for a given degree of consolidation U.

    Approximation (Das §11.8 / Craig §7.6):
        U <= 0.60: Tv = (pi/4) * U^2              (parabolic, exact for small U)
        U >  0.60: Tv = 1.781 - 0.933*log10(100*(1-U))

    :param U: Degree of consolidation (0 to 1, exclusive).  0 = no consolidation.
    :return:  Time factor Tv (dimensionless).
    :raises ValueError: If U is not in (0, 1).
    """
    if not (0.0 < U < 1.0):
        raise ValueError(f"U must be in (0, 1), got {U}")
    if U <= 0.60:
        return (math.pi / 4.0) * U ** 2
    return 1.781 - 0.933 * math.log10(100.0 * (1.0 - U))


def time_to_consolidation(
    U    : float,
    H_dr : float,
    cv   : float,
) -> TimeSettlementResult:
    """
    Time required to reach degree of consolidation U (Terzaghi 1D theory).

    Formula (Das §11.8):
        t = Tv * H_dr^2 / cv

    :param U:    Target degree of consolidation (0 to 1, exclusive).
    :param H_dr: Drainage path length (m).
                 = H/2 for double drainage (clay drained top and bottom).
                 = H   for single drainage (clay drained one side only).
    :param cv:   Coefficient of consolidation (m^2/year).  > 0.
    :return:     TimeSettlementResult.
    :raises ValueError: If any parameter is out of range.
    """
    if not (0.0 < U < 1.0):
        raise ValueError(f"U must be in (0, 1), got {U}")
    if H_dr <= 0:
        raise ValueError(f"H_dr must be > 0, got {H_dr}")
    if cv <= 0:
        raise ValueError(f"cv must be > 0, got {cv}")

    Tv = time_factor(U)
    t  = Tv * H_dr ** 2 / cv

    return TimeSettlementResult(t=t, U=U, Tv=Tv, H_dr=H_dr, cv=cv)

