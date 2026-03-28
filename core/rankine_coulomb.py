"""
rankine_coulomb.py -- Earth pressure coefficients and lateral pressure profiles.

Implements both Rankine (1857) and Coulomb (1776) theories for active and
passive earth pressure coefficients, plus functions to compute the full lateral
pressure distribution at any depth.

Theory summary:
    Rankine (smooth wall, horizontal backfill, vertical wall):
        Ka = tan^2(45 - phi'/2) = (1 - sin phi') / (1 + sin phi')
        Kp = tan^2(45 + phi'/2) = (1 + sin phi') / (1 - sin phi')

    Coulomb (general: wall friction delta, backfill slope beta, wall angle alpha):
        Ka and Kp from Coulomb (1776) as cited in EC7 Annex C and Craig Ch.11.
        More accurate when wall friction is mobilised (delta > 0).

    Pressure at depth z (active side, Rankine, drained):
        sigma_a(z) = Ka * (gamma * z - gamma_w * h_w) + Ka * q_surcharge
        or in terms of total/effective:
        sigma_a(z) = Ka * sigma_v'(z)    where sigma_v' = gamma*z - u(z)

    For the purposes of this module:
        - All pressures are EFFECTIVE stresses (pore pressure added separately).
        - Lateral pressure ratio K is applied to EFFECTIVE vertical stress.

Reference:
    Rankine, W.J.M. (1857). On the stability of loose earth. Phil. Trans. R. Soc.
    Coulomb, C.A. (1776). Essai sur une application des regles... Mem. Acad. Roy.
    Craig's Soil Mechanics, 9th ed., Chapter 11 (Earth pressure).
    Eurocode 7 -- EN 1997-1:2004, Annex C (Earth pressure coefficients).
    Das, B.M. (2019). Principles of Geotechnical Engineering, Chapter 11.

Sign conventions:
    Angles in degrees at function boundaries; converted to radians internally.
    phi  = friction angle phi' (degrees)
    delta = wall friction angle delta (degrees); 0 <= delta <= phi
    beta  = backfill inclination from horizontal (degrees); 0 = horizontal
    alpha = wall back face angle from horizontal (degrees); 90 = vertical wall
    All coefficients Ka, Kp >= 0.
    Compressive stresses are positive (geotechnical convention).

Units:
    Depths (m), unit weights (kN/m^3), pressures (kPa).
    Partial factors are dimensionless.
"""

import math
from dataclasses import dataclass


# ============================================================
#  Module constants
# ============================================================

GAMMA_W : float = 9.81   # Unit weight of water (kN/m^3)


# ============================================================
#  Result containers
# ============================================================

@dataclass
class PressureProfile:
    """
    Lateral earth pressure profile over the height of a retaining wall.

    Attributes
    ----------
    depths      : List of depth values z (m) from top of retained soil.
    pressures   : Corresponding effective lateral pressures (kPa).
    resultant   : Total thrust P (kN/m) -- integral of pressure over height.
    y_resultant : Height of resultant above wall base (m).
    ka_or_kp    : Coefficient used (Ka or Kp).
    label       : 'active' or 'passive'.
    """
    depths      : list[float]
    pressures   : list[float]
    resultant   : float
    y_resultant : float
    ka_or_kp    : float
    label       : str


# ============================================================
#  1.  Rankine coefficients  (smooth wall, horizontal backfill, vertical wall)
# ============================================================

def ka_rankine(phi_d: float) -> float:
    """
    Rankine active earth pressure coefficient for a smooth, vertical wall
    with horizontal backfill.

    Formula (Rankine, 1857 / Craig §11.1):
        Ka = tan^2(45 - phi'/2) = (1 - sin phi') / (1 + sin phi')

    :param phi_d: Design friction angle phi'_d (degrees).  Must be in [0, 90).
    :return:      Ka (dimensionless).  Range (0, 1].
    :raises ValueError: If phi_d is out of [0, 90).
    """
    if not (0.0 <= phi_d < 90.0):
        raise ValueError(f"phi_d must be in [0, 90), got {phi_d}")
    phi_r = math.radians(phi_d)
    return math.tan(math.radians(45.0 - phi_d / 2.0)) ** 2


def kp_rankine(phi_d: float) -> float:
    """
    Rankine passive earth pressure coefficient for a smooth, vertical wall
    with horizontal backfill.

    Formula (Rankine, 1857 / Craig §11.1):
        Kp = tan^2(45 + phi'/2) = (1 + sin phi') / (1 - sin phi')

    :param phi_d: Design friction angle phi'_d (degrees).  Must be in [0, 90).
    :return:      Kp (dimensionless).  Range [1, inf).
    :raises ValueError: If phi_d is out of [0, 90).
    """
    if not (0.0 <= phi_d < 90.0):
        raise ValueError(f"phi_d must be in [0, 90), got {phi_d}")
    return math.tan(math.radians(45.0 + phi_d / 2.0)) ** 2


# ============================================================
#  2.  Coulomb coefficients  (general: wall friction, inclined backfill)
# ============================================================

def ka_coulomb(
    phi_d : float,
    delta : float = 0.0,
    beta  : float = 0.0,
    alpha : float = 90.0,
) -> float:
    """
    Coulomb active earth pressure coefficient (general case).

    Formula (Coulomb 1776, EC7 Annex C / Craig §11.2):

        Ka = sin^2(alpha + phi') /
             [ sin^2(alpha) * sin(alpha - delta) *
               ( 1 + sqrt( sin(phi'+delta)*sin(phi'-beta) /
                           (sin(alpha-delta)*sin(alpha+beta)) ) )^2 ]

    For a vertical wall (alpha=90), horizontal backfill (beta=0), smooth (delta=0):
        Reduces exactly to Rankine Ka.

    :param phi_d: Design friction angle phi'_d (degrees).  [0, 90).
    :param delta: Wall friction angle delta (degrees).  [0, phi_d].
                  Recommended: delta = 2/3 * phi' for concrete-on-soil.
    :param beta:  Backfill surface inclination from horizontal (degrees).
                  Positive = slopes upward away from wall.  beta < phi_d.
    :param alpha: Angle of wall BACK FACE from horizontal (degrees).
                  90 = vertical wall.  (45, 90].
    :return:      Ka (dimensionless).
    :raises ValueError: If parameters are out of valid range or geometry is
                        impossible (e.g. beta >= phi_d).
    """
    _validate_coulomb_params(phi_d, delta, beta, alpha, "Ka")

    phi_r   = math.radians(phi_d)
    delta_r = math.radians(delta)
    beta_r  = math.radians(beta)
    alpha_r = math.radians(alpha)

    num = math.sin(alpha_r + phi_r) ** 2

    sin_a_minus_d = math.sin(alpha_r - delta_r)
    sin_a_plus_b  = math.sin(alpha_r + beta_r)

    inner = (
        math.sin(phi_r + delta_r) * math.sin(phi_r - beta_r) /
        (sin_a_minus_d * sin_a_plus_b)
    )
    if inner < 0:
        raise ValueError(
            "Coulomb Ka: impossible geometry — "
            f"phi_d={phi_d}, beta={beta}, alpha={alpha}.  "
            "Ensure beta < phi_d and alpha > delta."
        )

    denom = (
        math.sin(alpha_r) ** 2 *
        sin_a_minus_d *
        (1.0 + math.sqrt(inner)) ** 2
    )

    if abs(denom) < 1e-12:
        raise ValueError(
            "Coulomb Ka: denominator is zero — check wall angle alpha and delta."
        )

    return num / denom


def kp_coulomb(
    phi_d : float,
    delta : float = 0.0,
    beta  : float = 0.0,
    alpha : float = 90.0,
) -> float:
    """
    Coulomb passive earth pressure coefficient (general case).

    Formula (Coulomb 1776, EC7 Annex C / Craig §11.2):

        Kp = sin^2(alpha - phi') /
             [ sin^2(alpha) * sin(alpha + delta) *
               ( 1 - sqrt( sin(phi'+delta)*sin(phi'+beta) /
                           (sin(alpha+delta)*sin(alpha+beta)) ) )^2 ]

    Note: Coulomb Kp significantly OVERESTIMATES passive resistance when
    delta > 0 because the assumed planar failure surface is not correct for
    the passive case.  For design:
        - Use Kp_rankine (delta=0) as a conservative lower bound.
        - Use Kp_coulomb with delta <= phi'/3 for moderate estimates.
        - For delta > phi'/3, use log-spiral methods (not implemented here).

    :param phi_d: Design friction angle phi'_d (degrees).  [0, 90).
    :param delta: Wall friction angle delta (degrees).  [0, phi_d].
    :param beta:  Backfill slope (degrees).  beta < phi_d for stability.
    :param alpha: Wall back face angle from horizontal (degrees).  (45, 90].
    :return:      Kp (dimensionless).
    :raises ValueError: If parameters are invalid.
    """
    _validate_coulomb_params(phi_d, delta, beta, alpha, "Kp")

    phi_r   = math.radians(phi_d)
    delta_r = math.radians(delta)
    beta_r  = math.radians(beta)
    alpha_r = math.radians(alpha)

    num = math.sin(alpha_r - phi_r) ** 2

    sin_a_plus_d = math.sin(alpha_r + delta_r)
    sin_a_plus_b = math.sin(alpha_r + beta_r)

    inner = (
        math.sin(phi_r + delta_r) * math.sin(phi_r + beta_r) /
        (sin_a_plus_d * sin_a_plus_b)
    )
    if inner < 0:
        raise ValueError(
            "Coulomb Kp: impossible geometry — "
            f"phi_d={phi_d}, beta={beta}, alpha={alpha}."
        )

    sqrt_inner = math.sqrt(inner)
    if sqrt_inner >= 1.0:
        raise ValueError(
            f"Coulomb Kp: sqrt term >= 1 (got {sqrt_inner:.4f}) — geometry invalid."
        )

    denom = (
        math.sin(alpha_r) ** 2 *
        sin_a_plus_d *
        (1.0 - sqrt_inner) ** 2
    )

    if abs(denom) < 1e-12:
        raise ValueError(
            "Coulomb Kp: denominator is zero — check wall angle and delta."
        )

    return num / denom


# ============================================================
#  3.  Lateral pressure at depth z
# ============================================================

def active_pressure_at_depth(
    z         : float,
    gamma     : float,
    ka        : float,
    c_d       : float = 0.0,
    gamma_w   : float = GAMMA_W,
    z_w       : float | None = None,
) -> float:
    """
    Effective active lateral earth pressure at depth z.

    For drained (c-phi) soil the Rankine active pressure formula is:
        sigma_a' = Ka * sigma_v' - 2 * c' * sqrt(Ka)
    where sigma_v' = effective vertical stress = gamma*z - u(z).

    Tension zone (sigma_a' < 0): returns 0.0.  Tension cracks are not
    considered for design pressure (conservative).

    Formula (Craig §11.1, EC7 C.3):
        sigma_v  = gamma * z                  (total vertical stress)
        u(z)     = gamma_w * (z - z_w)        if z > z_w, else 0
        sigma_v' = sigma_v - u
        sigma_a' = Ka * sigma_v' - 2*c'*sqrt(Ka)  >= 0

    :param z:       Depth below backfill surface (m).  z >= 0.
    :param gamma:   Soil total unit weight (kN/m^3).
    :param ka:      Active pressure coefficient Ka (dimensionless).
    :param c_d:     Design cohesion c'_d (kPa).  Default 0.0 (cohesionless).
    :param gamma_w: Unit weight of water (kN/m^3).  Default 9.81.
    :param z_w:     Depth to water table (m).  None = dry (no pore pressure).
    :return:        Effective active lateral pressure sigma_a' (kPa).  >= 0.
    :raises ValueError: If z < 0 or ka < 0.
    """
    if z < 0:
        raise ValueError(f"Depth z must be >= 0, got {z}")
    if ka < 0:
        raise ValueError(f"ka must be >= 0, got {ka}")

    sigma_v  = gamma * z
    u        = gamma_w * (z - z_w) if (z_w is not None and z > z_w) else 0.0
    sigma_v_eff = sigma_v - u

    sigma_a = ka * sigma_v_eff - 2.0 * c_d * math.sqrt(ka)
    return max(0.0, sigma_a)


def passive_pressure_at_depth(
    z         : float,
    gamma     : float,
    kp        : float,
    c_d       : float = 0.0,
    gamma_w   : float = GAMMA_W,
    z_w       : float | None = None,
) -> float:
    """
    Effective passive lateral earth pressure at depth z.

    Formula (Craig §11.1):
        sigma_p' = Kp * sigma_v' + 2 * c' * sqrt(Kp)

    :param z:       Depth below ground surface on passive side (m).  z >= 0.
    :param gamma:   Soil total unit weight (kN/m^3).
    :param kp:      Passive pressure coefficient Kp (dimensionless).
    :param c_d:     Design cohesion c'_d (kPa).  Default 0.0.
    :param gamma_w: Unit weight of water (kN/m^3).  Default 9.81.
    :param z_w:     Depth to water table on passive side (m).  None = dry.
    :return:        Effective passive lateral pressure sigma_p' (kPa).
    :raises ValueError: If z < 0 or kp < 0.
    """
    if z < 0:
        raise ValueError(f"Depth z must be >= 0, got {z}")
    if kp < 0:
        raise ValueError(f"kp must be >= 0, got {kp}")

    sigma_v  = gamma * z
    u        = gamma_w * (z - z_w) if (z_w is not None and z > z_w) else 0.0
    sigma_v_eff = sigma_v - u

    return kp * sigma_v_eff + 2.0 * c_d * math.sqrt(kp)


# ============================================================
#  4.  Integrated pressure profiles
# ============================================================

def active_thrust(
    h         : float,
    gamma     : float,
    ka        : float,
    c_d       : float = 0.0,
    gamma_w   : float = GAMMA_W,
    z_w       : float | None = None,
    n_pts     : int   = 100,
) -> tuple[float, float]:
    """
    Total active thrust Pa and its height of application above the base.

    Integrates the active pressure profile sigma_a'(z) from z=0 to z=h
    using the trapezoidal rule.  Works for both cohesive and cohesionless
    soils, and handles a water table at depth z_w.

    :param h:       Wall / retained height (m).
    :param gamma:   Soil unit weight (kN/m^3).
    :param ka:      Active earth pressure coefficient.
    :param c_d:     Design cohesion (kPa).  Default 0.
    :param gamma_w: Unit weight of water (kN/m^3).  Default 9.81.
    :param z_w:     Depth to water table (m).  None = dry.
    :param n_pts:   Integration points (default 100; increase for accuracy).
    :return:        Tuple (Pa [kN/m], y_a [m above base]).
    :raises ValueError: If h <= 0.
    """
    if h <= 0:
        raise ValueError(f"Wall height h must be > 0, got {h}")

    dz    = h / n_pts
    z_arr = [i * dz for i in range(n_pts + 1)]
    p_arr = [
        active_pressure_at_depth(z, gamma, ka, c_d, gamma_w, z_w)
        for z in z_arr
    ]

    # Trapezoidal integration for thrust
    pa = sum(
        0.5 * (p_arr[i] + p_arr[i + 1]) * dz
        for i in range(n_pts)
    )

    if pa <= 0:
        return 0.0, h / 3.0   # no thrust (full tension zone)

    # Moment about base for resultant height
    moment = sum(
        0.5 * (p_arr[i] * (h - z_arr[i]) + p_arr[i + 1] * (h - z_arr[i + 1])) * dz
        for i in range(n_pts)
    )
    y_a = moment / pa
    return pa, y_a


def passive_thrust(
    h         : float,
    gamma     : float,
    kp        : float,
    c_d       : float = 0.0,
    gamma_w   : float = GAMMA_W,
    z_w       : float | None = None,
    n_pts     : int   = 100,
) -> tuple[float, float]:
    """
    Total passive thrust Pp and its height of application above the base.

    :param h:    Embedment depth / passive zone height (m).
    :param gamma: Soil unit weight (kN/m^3).
    :param kp:   Passive earth pressure coefficient.
    :param c_d:  Design cohesion (kPa).
    :param gamma_w: Unit weight of water (kN/m^3).
    :param z_w:  Depth to water table on passive side (m).  None = dry.
    :param n_pts: Integration points.
    :return:     Tuple (Pp [kN/m], y_p [m above base]).
    :raises ValueError: If h <= 0.
    """
    if h <= 0:
        raise ValueError(f"Passive height h must be > 0, got {h}")

    dz    = h / n_pts
    z_arr = [i * dz for i in range(n_pts + 1)]
    p_arr = [
        passive_pressure_at_depth(z, gamma, kp, c_d, gamma_w, z_w)
        for z in z_arr
    ]

    pp = sum(
        0.5 * (p_arr[i] + p_arr[i + 1]) * dz
        for i in range(n_pts)
    )

    if pp <= 0:
        return 0.0, h / 3.0

    moment = sum(
        0.5 * (p_arr[i] * (h - z_arr[i]) + p_arr[i + 1] * (h - z_arr[i + 1])) * dz
        for i in range(n_pts)
    )
    y_p = moment / pp
    return pp, y_p


# ============================================================
#  5.  Private validation helper
# ============================================================

def _validate_coulomb_params(
    phi_d : float,
    delta : float,
    beta  : float,
    alpha : float,
    label : str,
) -> None:
    """Validates Coulomb parameter ranges and raises ValueError if invalid."""
    if not (0.0 <= phi_d < 90.0):
        raise ValueError(f"Coulomb {label}: phi_d must be in [0, 90), got {phi_d}")
    if not (0.0 <= delta <= phi_d):
        raise ValueError(
            f"Coulomb {label}: delta must be in [0, phi_d={phi_d}], got {delta}"
        )
    if not (-30.0 <= beta < phi_d):
        raise ValueError(
            f"Coulomb {label}: beta must be in [-30, phi_d), got {beta}"
        )
    if not (45.0 < alpha <= 90.0):
        raise ValueError(
            f"Coulomb {label}: alpha must be in (45, 90], got {alpha}"
        )
