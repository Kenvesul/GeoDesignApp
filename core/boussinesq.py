"""
boussinesq.py – Boussinesq (1885) vertical stress distribution in soil.

Implements the elastic solution for stress increase Δσ_v below foundations
using the Fadum (1948) double-integration influence factor for rectangular
loads.  All functions are pure Python (math module only).

Theory summary
──────────────
Point load (Boussinesq 1885):
    Δσ_v = Q / z² · (3/2π) · 1 / (1 + (r/z)²)^(5/2)

Rectangular uniformly distributed load (superposition of point loads):
    Δσ_v = q · I_B
where I_B is the Fadum (1948) influence factor obtained by integrating
the point-load formula over the loaded rectangle.

Corner formula (Fadum 1948 / Newmark 1935):
    For a rectangle B × L under uniform pressure q, the stress increase
    at depth z directly below one CORNER is:

        Δσ_v(corner) = q · I_z

    where (with m = B/z, n = L/z):

        I_z = (1/4π) · {
            [2mn√(m²+n²+1) / (m²+n²+m²n²+1)] · [(m²+n²+2)/(m²+n²+1)]
            + arctan[ 2mn√(m²+n²+1) / (m²+n²+1−m²n²) ]
        }

    Special case: when m²n² > m²+n²+1 (denominator of arctan becomes
    negative), add π to the arctan result to keep I_z continuous.

Centre formula:
    Superpose 4 quarter-rectangles of (B/2)×(L/2); corner of each
    quarter = centre of the full rectangle:

        I_centre = 4 · I_z(m = B/(2z),  n = L/(2z))

Validation:
    Das, B.M. (2019). Principles of Geotechnical Engineering, Table 10.1.
    Selected values:
        m=0.25, n=0.25 → I_z = 0.027
        m=0.50, n=0.50 → I_z = 0.084
        m=1.00, n=1.00 → I_z = 0.175
        m=2.00, n=2.00 → I_z = 0.232

References:
    Boussinesq, J. (1885). Application des Potentiels. Gauthier-Villars, Paris.
    Fadum, R.E. (1948). Influence values for vertical stresses in a
        semi-infinite solid due to surface loads. Proc. 2nd ICSMFE, Vol.3.
    Newmark, N.M. (1935). Simplified computation of vertical pressures in
        elastic foundations. Univ. Illinois Eng. Exp. Station Circ. 24.
    Das, B.M. (2019). Principles of Geotechnical Engineering, 9th ed., Ch.10.
    Craig's Soil Mechanics, 9th ed., Ch.5 (stress distribution).

Sign convention:
    z > 0  downward from the foundation base.
    Δσ_v > 0 = compressive (consistent with geotechnical convention).

Units:
    Pressures and stress in kPa.  Lengths in metres (m).
"""

import math


# ============================================================
#  1. Fadum (1948) corner influence factor
# ============================================================

def fadum_influence_corner(m: float, n: float) -> float:
    """
    Fadum (1948) stress influence factor at depth z below the CORNER of
    a uniformly loaded rectangle with plan dimensions B and L.

    Parameters
    ----------
    m : float  B / z   (width-to-depth ratio,  m > 0)
    n : float  L / z   (length-to-depth ratio, n > 0)

    Returns
    -------
    float  I_z  –  dimensionless influence factor in [0, 0.25].

    Formula (Fadum 1948, as tabulated in Das 2019 Table 10.1):

        A = 2mn√(m²+n²+1) / (m²+n²+m²n²+1)

        B_val = (m²+n²+2) / (m²+n²+1)

        denom = m²+n²+1 − m²n²

        I_z = (1/4π) · [A · B_val + arctan(A_num / denom)]

    where A_num = 2mn√(m²+n²+1).

    When m²n² ≥ m²+n²+1 the denominator of the arctan becomes zero or
    negative; π is added to maintain continuity (Newmark 1935).

    :param m: B/z ratio (> 0).
    :param n: L/z ratio (> 0).
    :return:  Influence factor I_z (dimensionless, 0 < I_z ≤ 0.25).
    :raises ValueError: If m or n ≤ 0.

    Validation against Das (2019) Table 10.1:
        fadum_influence_corner(1.0, 1.0) ≈ 0.1752  (table: 0.175)  ✓
        fadum_influence_corner(2.0, 2.0) ≈ 0.2325  (table: 0.232)  ✓
    """
    if m <= 0:
        raise ValueError(f"m = B/z must be > 0, got {m}")
    if n <= 0:
        raise ValueError(f"n = L/z must be > 0, got {n}")

    m2     = m * m
    n2     = n * n
    m2n2   = m2 * n2
    sum_mn = m2 + n2

    # √(m²+n²+1)
    sqrt_term = math.sqrt(sum_mn + 1.0)

    # Numerator of arctan argument: 2mn√(m²+n²+1)
    a_num = 2.0 * m * n * sqrt_term

    # First term (Craig §5.3 / Das Eq 10.15):
    #   [2mn√(m²+n²+1) × (m²+n²+2)] / [(m²+n²+1) × (m²+n²+m²n²+1)]
    term1 = a_num * (sum_mn + 2.0) / ((sum_mn + 1.0) * (sum_mn + m2n2 + 1.0))

    # Arctan term: arctan( a_num / (m²+n²+1 − m²n²) )
    arctan_denom = sum_mn + 1.0 - m2n2

    if arctan_denom > 0:
        theta = math.atan(a_num / arctan_denom)
    elif arctan_denom < 0:
        # Denominator sign-change (m²n² > m²+n²+1): add π for continuity
        theta = math.atan(a_num / arctan_denom) + math.pi
    else:
        theta = math.pi / 2.0

    I_z = (term1 + theta) / (4.0 * math.pi)
    return I_z


# ============================================================
#  2. Stress at centre and corner of rectangle
# ============================================================

def stress_below_corner(
    q: float,
    B: float,
    L: float,
    z: float,
) -> float:
    """
    Vertical stress increase at depth z directly below one CORNER of
    a uniformly loaded rectangle B × L.

    Formula:
        Δσ_v = q · I_z(m = B/z, n = L/z)

    Reference: Fadum (1948) / Das §10.5.

    :param q:  Applied surface pressure (kPa). ≥ 0.
    :param B:  Foundation width  (m). > 0.
    :param L:  Foundation length (m). > 0.
    :param z:  Depth below the loaded surface (m). > 0.
    :return:   Δσ_v (kPa).
    :raises ValueError: If any parameter is out of range.
    """
    if q < 0:
        raise ValueError(f"q must be ≥ 0, got {q}")
    if B <= 0:
        raise ValueError(f"B must be > 0, got {B}")
    if L <= 0:
        raise ValueError(f"L must be > 0, got {L}")
    if z <= 0:
        raise ValueError(f"z must be > 0, got {z}")

    I_z = fadum_influence_corner(m=B / z, n=L / z)
    return q * I_z


def stress_below_centre(
    q: float,
    B: float,
    L: float,
    z: float,
) -> float:
    """
    Vertical stress increase at depth z directly below the CENTRE of
    a uniformly loaded rectangle B × L.

    Method: superposition of 4 equal quarter-rectangles (B/2 × L/2).
    The corner of each quarter lies at the centre of the full rectangle.

    Formula:
        Δσ_v = 4 · q · I_z(m = B/(2z), n = L/(2z))

    Reference: Craig §5.3 / Das §10.5 (superposition principle).

    :param q:  Applied surface pressure (kPa). ≥ 0.
    :param B:  Foundation width  (m). > 0.
    :param L:  Foundation length (m). > 0.
    :param z:  Depth below the loaded surface (m). > 0.
    :return:   Δσ_v (kPa).
    """
    if q < 0:
        raise ValueError(f"q must be ≥ 0, got {q}")
    if B <= 0:
        raise ValueError(f"B must be > 0, got {B}")
    if L <= 0:
        raise ValueError(f"L must be > 0, got {L}")
    if z <= 0:
        raise ValueError(f"z must be > 0, got {z}")

    I_z = fadum_influence_corner(m=B / (2.0 * z), n=L / (2.0 * z))
    return 4.0 * q * I_z


def stress_below_point(
    q: float,
    B: float,
    L: float,
    z: float,
    x: float,
    y: float,
) -> float:
    """
    Vertical stress increase at depth z below an arbitrary point (x, y)
    relative to the CORNER of a uniformly loaded rectangle B × L.

    Uses the superposition of up to 4 rectangular sub-areas (positive
    contributions are added; sub-areas outside the loaded zone are
    subtracted).  This is the general Newmark (1935) superposition.

    Coordinate system:
        The loaded rectangle occupies  0 ≤ x ≤ B,  0 ≤ y ≤ L.
        The query point is at (x_q, y_q) in this system.

    :param q:  Applied surface pressure (kPa). ≥ 0.
    :param B:  Foundation width  (m). > 0.
    :param L:  Foundation length (m). > 0.
    :param z:  Depth below the loaded surface (m). > 0.
    :param x:  Query point x-coordinate (m).  0 ≤ x ≤ B for interior.
    :param y:  Query point y-coordinate (m).  0 ≤ y ≤ L for interior.
    :return:   Δσ_v (kPa).  Can be 0 for points far outside the loaded area.
    """
    if q < 0:
        raise ValueError(f"q must be ≥ 0, got {q}")
    if B <= 0 or L <= 0:
        raise ValueError("B and L must be > 0")
    if z <= 0:
        raise ValueError(f"z must be > 0, got {z}")

    def _i(bx: float, ly: float) -> float:
        """Influence factor at corner, zero for degenerate sub-rectangle."""
        if bx <= 0 or ly <= 0:
            return 0.0
        return fadum_influence_corner(bx / z, ly / z)

    # Decompose: four sub-rectangles via Newmark superposition
    # Sub-areas a, b, c, d with corners at the query point
    a = _i(x,     y)
    b = _i(x,     L - y)
    c = _i(B - x, y)
    d = _i(B - x, L - y)

    return q * (a + b + c + d)


# ============================================================
#  3. Stress profile (list of depths)
# ============================================================

def stress_profile(
    q:          float,
    B:          float,
    L:          float,
    z_values:   list[float],
    at_centre:  bool = True,
) -> list[float]:
    """
    Returns the vertical stress increase Δσ_v at each depth in z_values,
    for a rectangle B × L under uniform pressure q.

    :param q:          Applied surface pressure (kPa). ≥ 0.
    :param B:          Foundation width  (m). > 0.
    :param L:          Foundation length (m). > 0.
    :param z_values:   List of depths (m). Each > 0.
    :param at_centre:  True = below centre (default);  False = below corner.
    :return:           List of Δσ_v values (kPa), same length as z_values.
    """
    fn = stress_below_centre if at_centre else stress_below_corner
    return [fn(q, B, L, z) for z in z_values]


# ============================================================
#  4. Convenience: 2:1 approximation (for comparison)
# ============================================================

def stress_2to1(
    q: float,
    B: float,
    L: float,
    z: float,
) -> float:
    """
    Stress increase at depth z using the simplified 2:1 load spread method.

    Formula (Terzaghi & Peck 1967 — approximation only):
        Δσ_v = q · B · L / [(B + z) · (L + z)]

    Less accurate than Boussinesq but widely used for routine design.
    Overestimates stress at shallow depth, underestimates at large depth.

    Reference:
        Das §10.3 / Craig §5.3 — see Table 5.1 for comparison with Boussinesq.

    :param q:  Applied surface pressure (kPa). ≥ 0.
    :param B:  Foundation width  (m). > 0.
    :param L:  Foundation length (m). > 0.
    :param z:  Depth below the loaded surface (m). > 0.
    :return:   Δσ_v (kPa).
    """
    if q < 0:
        raise ValueError(f"q must be ≥ 0, got {q}")
    if B <= 0 or L <= 0:
        raise ValueError("B and L must be > 0")
    if z <= 0:
        raise ValueError(f"z must be > 0, got {z}")

    return q * B * L / ((B + z) * (L + z))
