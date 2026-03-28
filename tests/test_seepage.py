"""
test_seepage.py — Sprint 8 validation suite for seepage.py.

Covers:
    S8-A  Primitive functions: pore_pressure_from_phreatic, ru_at_point.
    S8-B  Dupuit steady-state seepage: flow, phreatic height, boundary conditions.
    S8-C  PhreaticSurface: construction, interpolation, u_at, ru_at.
    S8-D  build_dupuit_surface: parabolic profile → PhreaticSurface.
    S8-E  Physics / monotonicity checks.
    S8-F  Invalid input validation.

Reference values
----------------
All expected values verified from first principles against:
    Bishop, A.W. & Morgenstern, N.R. (1960). Stability coefficients for earth
        slopes. Géotechnique 10(4), 129–150.  → r_u definition and usage.
    Dupuit, J. (1863). Études Théoriques et Pratiques. → q and h(x) formulae.
    Craig's Soil Mechanics, 9th ed., §2.7 (seepage), §9.2 (pore pressure).
    Das, B.M. (2019). Principles of Geotechnical Engineering, §7.8.

Formulae used
-------------
    u      = γ_w × max(0, y_ph − y_base)          [kPa]
    r_u    = u / (γ · h_soil)                       [-]
    q      = k · (h1² − h2²) / (2·L)               [m²/s per m run]
    h(x)   = √(h1² − (h1²−h2²)·x/L)               [m]
"""

import math
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.seepage import (
    pore_pressure_from_phreatic,
    ru_at_point,
    dupuit_seepage_flow,
    dupuit_phreatic_height,
    build_dupuit_surface,
    PhreaticSurface,
    GAMMA_W,
)

TOL_PCT = 0.01   # 0.01 % for analytical formula tests
GAMMA_W_REF = 9.81


# ── Helper ───────────────────────────────────────────────────────────────────
def _check(label, got, exp, tol_pct=TOL_PCT):
    err = abs(got - exp) / max(abs(exp), 1e-12) * 100.0
    ok  = err <= tol_pct
    tag = "PASS" if ok else "FAIL"
    print(f"  {tag}  {label:<46}  expected={exp:>12.6f}  got={got:>12.6f}  err={err:.4f}%")
    assert ok, f"FAIL {label}: expected {exp}, got {got} ({err:.4f}% > {tol_pct}%)"


# ============================================================
#  S8-A  Primitive functions
# ============================================================

def test_pore_pressure_standard():
    """
    Pore pressure from phreatic elevation above base point.

    u = γ_w × (y_ph − y_base)

    Case 1: y_ph=5m, y_base=3m → hw=2m → u=9.81×2=19.62 kPa
    Case 2: y_ph=8m, y_base=2m → hw=6m → u=9.81×6=58.86 kPa

    Reference: Bishop & Morgenstern (1960), eq. (1); Craig §9.2.
    """
    print("\n══  S8-A-1  pore_pressure_from_phreatic — standard cases  ══")
    _check("u (y_ph=5, base=3)",  pore_pressure_from_phreatic(5.0, 3.0), 9.81 * 2.0)
    _check("u (y_ph=8, base=2)",  pore_pressure_from_phreatic(8.0, 2.0), 9.81 * 6.0)
    _check("u (y_ph=10, base=0)", pore_pressure_from_phreatic(10.0, 0.0), 9.81 * 10.0)
    print("  ✅  PASS")


def test_pore_pressure_tension_clamped():
    """
    Below phreatic surface: tension pore pressure clamped to zero.

    Negative pore pressure (capillary suction) is not modelled in EC7
    stability analysis.  u is always ≥ 0.

    Reference: Craig §9.2 — negative pore pressures neglected.
    """
    print("\n══  S8-A-2  pore_pressure clamped to zero for tension  ══")
    _check("u=0 (base > phreatic, tight)",  pore_pressure_from_phreatic(5.0, 7.0),   0.0)
    _check("u=0 (base == phreatic)",         pore_pressure_from_phreatic(5.0, 5.0),   0.0)
    _check("u=0 (base >> phreatic)",         pore_pressure_from_phreatic(0.0, 100.0), 0.0)
    print("  ✅  PASS")


def test_pore_pressure_custom_gamma_w():
    """Custom γ_w applied correctly (e.g. 10.0 kN/m³ for simplified calculation)."""
    print("\n══  S8-A-3  pore_pressure custom γ_w  ══")
    u = pore_pressure_from_phreatic(5.0, 3.0, gamma_w=10.0)
    _check("u (γ_w=10, hw=2)", u, 20.0)
    print("  ✅  PASS")


def test_ru_standard():
    """
    r_u = u / (γ · h_soil)

    Case 1: u=19.62, γ=18, h=5 → r_u = 19.62/90 = 0.21800
    Case 2: u=29.43, γ=20, h=4 → r_u = 29.43/80 = 0.36788

    Reference: Bishop & Morgenstern (1960), stability coefficient definition.
    """
    print("\n══  S8-A-4  ru_at_point — standard cases  ══")
    _check("r_u (u=19.62 γ=18 h=5)", ru_at_point(19.62, 18.0, 5.0), 19.62 / 90.0)
    _check("r_u (u=29.43 γ=20 h=4)", ru_at_point(29.43, 20.0, 4.0), 29.43 / 80.0)
    print("  ✅  PASS")


def test_ru_zero_pore_pressure():
    """r_u = 0 when pore pressure = 0 (soil above phreatic surface)."""
    print("\n══  S8-A-5  ru_at_point = 0 for u=0  ══")
    _check("r_u = 0", ru_at_point(0.0, 18.0, 5.0), 0.0)
    print("  ✅  PASS")


def test_ru_inverse_gamma_h():
    """
    r_u inversely proportional to γ×h.

    For fixed u, doubling γ halves r_u;
    doubling h also halves r_u.

    Reference: Bishop & Morgenstern (1960).
    """
    print("\n══  S8-A-6  ru inverse proportionality  ══")
    u = 20.0
    ru1 = ru_at_point(u, 18.0, 5.0)
    ru2 = ru_at_point(u, 36.0, 5.0)   # γ doubled → ru halved
    ru3 = ru_at_point(u, 18.0, 10.0)  # h doubled  → ru halved
    _check("γ doubled → ru halved",  ru2, ru1 / 2.0)
    _check("h doubled  → ru halved", ru3, ru1 / 2.0)
    print("  ✅  PASS")


def test_ru_phreatic_fraction():
    """
    For phreatic surface at fraction f of soil height above slice base:
        u   = γ_w · f · h
        r_u = γ_w · f / γ

    For γ_w=9.81, γ=18, f=0.5:
        r_u = 9.81 × 0.5 / 18 = 0.272500

    Reference: Bishop & Morgenstern (1960) stability chart basis.
    """
    print("\n══  S8-A-7  ru from phreatic fraction  ══")
    h, gamma, f = 6.0, 18.0, 0.5
    u  = pore_pressure_from_phreatic(f * h, 0.0)   # phreatic at fh, base at 0
    ru = ru_at_point(u, gamma, h)
    ru_exp = GAMMA_W_REF * f / gamma
    _check("r_u (f=0.5, γ=18)", ru, ru_exp)
    print("  ✅  PASS")


# ============================================================
#  S8-B  Dupuit formulas
# ============================================================

def test_dupuit_flow_reference():
    """
    Dupuit seepage flow: q = k(h1² − h2²)/(2L).

    Reference case (Craig §2.7):
        k=1×10⁻⁴ m/s, h1=6m, h2=2m, L=20m
        q = 1e-4 × (36 − 4) / 40 = 1e-4 × 0.8 = 8.0×10⁻⁵ m²/s

    Reference: Craig's Soil Mechanics, 9th ed., §2.7, eq. (2.30).
    """
    print("\n══  S8-B-1  Dupuit seepage flow reference case  ══")
    q = dupuit_seepage_flow(6.0, 2.0, 20.0, 1e-4)
    _check("q (m²/s)", q, 8.0e-5)
    print("  ✅  PASS")


def test_dupuit_flow_zero_head():
    """
    Dupuit flow with free outflow (h2=0): q = k·h1²/(2L).

    k=5×10⁻⁵, h1=5m, L=30m:
        q = 5e-5 × 25 / 60 = 2.0833×10⁻⁵ m²/s
    """
    print("\n══  S8-B-2  Dupuit seepage flow with h2=0  ══")
    q = dupuit_seepage_flow(5.0, 0.0, 30.0, 5e-5)
    _check("q (h2=0)", q, 5e-5 * 25.0 / 60.0)
    print("  ✅  PASS")


def test_dupuit_height_boundary_conditions():
    """
    Dupuit phreatic height satisfies h(0)=h1 and h(L)=h2.

    Reference: Craig §2.7 — boundary conditions of Dupuit solution.
    """
    print("\n══  S8-B-3  Dupuit phreatic height — boundary conditions  ══")
    h1, h2, L = 6.0, 2.0, 20.0
    _check("h(0) = h1 = 6m", dupuit_phreatic_height(h1, h2, L, 0.0),  h1)
    _check("h(L) = h2 = 2m", dupuit_phreatic_height(h1, h2, L, L),    h2)
    print("  ✅  PASS")


def test_dupuit_height_midpoint():
    """
    Dupuit phreatic height at x=L/2.

    h(L/2) = √((h1² + h2²)/2)

    For h1=6, h2=2, L=20, x=10:
        h² = 36 − 32×10/20 = 36 − 16 = 20
        h  = √20 = 4.47214 m

    Reference: Das (2019), §7.8.
    """
    print("\n══  S8-B-4  Dupuit phreatic height at midpoint  ══")
    h1, h2, L = 6.0, 2.0, 20.0
    x   = L / 2.0
    exp = math.sqrt(h1**2 - (h1**2 - h2**2) * x / L)
    _check("h(L/2)", dupuit_phreatic_height(h1, h2, L, x), exp)
    print("  ✅  PASS")


def test_dupuit_height_parabolic_profile():
    """
    Dupuit h²(x) is a linear function of x (parabolic phreatic surface).

    For several x values: h²(x) = h1² − (h1²−h2²)·x/L must be linear.

    Reference: Dupuit (1863); Craig §2.7.
    """
    print("\n══  S8-B-5  Dupuit h²(x) linear in x  ══")
    h1, h2, L = 8.0, 1.0, 40.0
    xs   = [0, 8, 16, 24, 32, 40]
    h_sqs = [(dupuit_phreatic_height(h1, h2, L, x))**2 for x in xs]
    slope = (h_sqs[-1] - h_sqs[0]) / (xs[-1] - xs[0])
    for i, (x, h_sq) in enumerate(zip(xs, h_sqs)):
        expected = h1**2 + slope * x
        _check(f"h²({x}m) on line", h_sq, expected, tol_pct=0.05)
    print("  ✅  PASS")


def test_dupuit_flow_proportional_to_k():
    """q is proportional to k (doubled k → doubled q)."""
    print("\n══  S8-B-6  Dupuit flow proportional to k  ══")
    q1 = dupuit_seepage_flow(5.0, 0.0, 20.0, 1e-4)
    q2 = dupuit_seepage_flow(5.0, 0.0, 20.0, 2e-4)
    _check("q2/q1 = 2", q2 / q1, 2.0)
    print("  ✅  PASS")


# ============================================================
#  S8-C  PhreaticSurface
# ============================================================

def test_phreatic_surface_interpolation():
    """
    Piecewise linear interpolation on PhreaticSurface.

    Points: (0,10), (10,8), (20,5).
        y(0)  = 10.0
        y(5)  = 10 + (8−10)×5/10  = 9.0
        y(10) = 8.0
        y(15) = 8  + (5−8)×5/10   = 6.5
        y(20) = 5.0

    Reference: Craig §9.2 (phreatic line as input to slice method).
    """
    print("\n══  S8-C-1  PhreaticSurface — linear interpolation  ══")
    ps = PhreaticSurface([(0.0, 10.0), (10.0, 8.0), (20.0, 5.0)])
    cases = [(0.0, 10.0), (5.0, 9.0), (10.0, 8.0), (15.0, 6.5), (20.0, 5.0)]
    for x, exp in cases:
        _check(f"y({x})", ps.y_at(x), exp)
    print("  ✅  PASS")


def test_phreatic_surface_extrapolation():
    """
    Outside range: y_at is clamped to nearest boundary (horizontal extension).

    Conservative: assumes phreatic surface does not rise beyond known points.
    """
    print("\n══  S8-C-2  PhreaticSurface — out-of-range clamping  ══")
    ps = PhreaticSurface([(2.0, 5.0), (8.0, 3.0)])
    _check("y(x < x_min) = y at x_min", ps.y_at(-5.0), 5.0)
    _check("y(x > x_max) = y at x_max", ps.y_at(50.0), 3.0)
    print("  ✅  PASS")


def test_phreatic_surface_u_at():
    """
    u_at computes pore pressure at (x, base_y).

    Using points (0,10),(10,8),(20,5):
        y(5) = 9.0 → u(x=5, base=7) = 9.81 × (9−7) = 19.62 kPa
        y(5) = 9.0 → u(x=5, base=12) = 0  (base above phreatic)

    Reference: Bishop & Morgenstern (1960), eq. (1).
    """
    print("\n══  S8-C-3  PhreaticSurface — u_at  ══")
    ps = PhreaticSurface([(0.0, 10.0), (10.0, 8.0), (20.0, 5.0)])
    _check("u(x=5, base=7)",  ps.u_at(5.0, 7.0),  9.81 * 2.0)
    _check("u(x=5, base=12)", ps.u_at(5.0, 12.0), 0.0)
    _check("u(x=10, base=0)", ps.u_at(10.0, 0.0), 9.81 * 8.0)
    print("  ✅  PASS")


def test_phreatic_surface_ru_at():
    """
    ru_at = u(x, base_y) / (γ · h_soil).

    y(5) = 9.0, base=7.0 → u=19.62 kPa, γ=18, h=3m
        r_u = 19.62 / (18 × 3) = 19.62/54 = 0.36333
    """
    print("\n══  S8-C-4  PhreaticSurface — ru_at  ══")
    ps = PhreaticSurface([(0.0, 10.0), (10.0, 8.0), (20.0, 5.0)])
    u_exp = 9.81 * 2.0
    ru_exp = u_exp / (18.0 * 3.0)
    _check("ru(x=5, base=7, γ=18, h=3)", ps.ru_at(5.0, 7.0, 18.0, 3.0), ru_exp)
    print("  ✅  PASS")


def test_phreatic_surface_repr():
    """PhreaticSurface repr is informative."""
    print("\n══  S8-C-5  PhreaticSurface repr  ══")
    ps = PhreaticSurface([(0.0, 5.0), (10.0, 3.0), (20.0, 1.0)])
    r = repr(ps)
    assert "3 nodes" in r
    assert "x=[" in r
    print(f"  repr: {r}  ✓")
    print("  ✅  PASS")


def test_phreatic_surface_validation():
    """PhreaticSurface raises ValueError on invalid inputs."""
    print("\n══  S8-C-6  PhreaticSurface — invalid input validation  ══")
    # Only one point
    try:
        PhreaticSurface([(0.0, 5.0)])
        raise AssertionError("Should have raised")
    except ValueError:
        print("  < 2 points: raised ValueError ✓")
    # Non-increasing x
    try:
        PhreaticSurface([(0.0, 5.0), (10.0, 3.0), (8.0, 2.0)])
        raise AssertionError("Should have raised")
    except ValueError:
        print("  Non-increasing x: raised ValueError ✓")
    # gamma_w <= 0
    try:
        PhreaticSurface([(0.0, 5.0), (10.0, 3.0)], gamma_w=0.0)
        raise AssertionError("Should have raised")
    except ValueError:
        print("  gamma_w=0: raised ValueError ✓")
    print("  ✅  PASS")


# ============================================================
#  S8-D  build_dupuit_surface
# ============================================================

def test_build_dupuit_surface_boundary_conditions():
    """
    build_dupuit_surface: first and last nodes match h1 and h2.

    For h1=6, h2=2, L=20 with y_base=0:
        y(x=0) = 0 + h1 = 6.0
        y(x=L) = 0 + h2 = 2.0
    """
    print("\n══  S8-D-1  build_dupuit_surface — boundary conditions  ══")
    surf = build_dupuit_surface(h1=6.0, h2=2.0, L=20.0, y_base=0.0, n_points=11)
    _check("y at x=0  (= h1)", surf.y_at(surf.x_min), 6.0)
    _check("y at x=L  (= h2)", surf.y_at(surf.x_max), 2.0)
    print("  ✅  PASS")


def test_build_dupuit_surface_midpoint():
    """
    Midpoint phreatic height matches Dupuit formula.

    h1=6, h2=2, L=20: h(10) = √20 = 4.47214m
    """
    print("\n══  S8-D-2  build_dupuit_surface — midpoint height  ══")
    surf = build_dupuit_surface(h1=6.0, h2=2.0, L=20.0, n_points=21)
    exp  = dupuit_phreatic_height(6.0, 2.0, 20.0, 10.0)
    _check("h at x_mid", surf.y_at(10.0), exp, tol_pct=0.05)
    print("  ✅  PASS")


def test_build_dupuit_surface_offset():
    """x_offset and y_base shift the surface correctly."""
    print("\n══  S8-D-3  build_dupuit_surface — x_offset and y_base  ══")
    x_off, y_b = 5.0, 3.0
    h1, h2, L  = 4.0, 1.0, 15.0
    surf = build_dupuit_surface(h1, h2, L, x_offset=x_off, y_base=y_b, n_points=10)
    # At x=x_off, elevation should be y_base + h1
    _check("y at x=x_offset", surf.y_at(x_off), y_b + h1)
    # At x=x_off+L, elevation should be y_base + h2
    _check("y at x=x_offset+L", surf.y_at(x_off + L), y_b + h2)
    print("  ✅  PASS")


# ============================================================
#  S8-E  Physics / monotonicity checks
# ============================================================

def test_dupuit_height_decreasing_downstream():
    """Dupuit phreatic height decreases monotonically from h1 to h2."""
    print("\n══  S8-E-1  Dupuit h(x) decreasing downstream  ══")
    h1, h2, L = 7.0, 1.0, 50.0
    xs = [i * L / 10 for i in range(11)]
    hs = [dupuit_phreatic_height(h1, h2, L, x) for x in xs]
    for i in range(len(hs) - 1):
        assert hs[i] >= hs[i+1] - 1e-9, (
            f"h not decreasing: h({xs[i]})={hs[i]:.4f} < h({xs[i+1]})={hs[i+1]:.4f}"
        )
    print(f"  h spans [{hs[-1]:.3f}, {hs[0]:.3f}] m — strictly decreasing  ✓")
    print("  ✅  PASS")


def test_ru_increases_with_phreatic_height():
    """
    Higher phreatic surface → higher u → higher r_u for same soil column.

    Reference: Bishop & Morgenstern (1960) — r_u characterises pore
    pressure effect on stability.
    """
    print("\n══  S8-E-2  r_u increases with phreatic height  ══")
    gamma, h_soil = 18.0, 8.0
    prev_ru = -1.0
    for hw in [0.5, 1.0, 2.0, 4.0, 6.0]:
        u  = pore_pressure_from_phreatic(hw, 0.0)
        ru = ru_at_point(u, gamma, h_soil)
        assert ru > prev_ru, f"r_u not increasing at hw={hw}"
        prev_ru = ru
    print(f"  r_u strictly increases with hw  ✓")
    print("  ✅  PASS")


def test_dupuit_flow_increases_with_head_difference():
    """Larger (h1²−h2²) → larger q."""
    print("\n══  S8-E-3  Dupuit flow increases with head difference  ══")
    k, L = 1e-4, 20.0
    h2 = 0.0
    prev_q = -1.0
    for h1 in [1.0, 2.0, 4.0, 6.0, 8.0]:
        q = dupuit_seepage_flow(h1, h2, L, k)
        assert q > prev_q
        prev_q = q
    print("  q strictly increasing with h1  ✓")
    print("  ✅  PASS")


def test_phreatic_surface_u_decreases_with_depth():
    """
    u decreases as base_y increases (point approaches phreatic surface).
    u=0 once base_y ≥ phreatic elevation.
    """
    print("\n══  S8-E-4  u decreases as point approaches phreatic surface  ══")
    ps = PhreaticSurface([(0.0, 10.0), (20.0, 10.0)])  # flat at y=10
    prev_u = 9999.0
    for base_y in [0.0, 2.0, 5.0, 8.0, 10.0, 12.0]:
        u = ps.u_at(5.0, base_y)
        assert u <= prev_u + 1e-9
        prev_u = u
    print("  u monotonically decreasing with base_y  ✓")
    print("  ✅  PASS")


# ============================================================
#  S8-F  Invalid input validation
# ============================================================

def test_invalid_primitive_inputs():
    """Primitive functions raise ValueError for invalid inputs."""
    print("\n══  S8-F-1  Invalid inputs to primitive functions  ══")
    # pore_pressure: gamma_w <= 0
    try:
        pore_pressure_from_phreatic(5.0, 3.0, gamma_w=-1.0)
        raise AssertionError("Should have raised")
    except ValueError:
        print("  pore_pressure gamma_w<=0: raised ValueError ✓")

    # ru_at_point: h_soil <= 0
    try:
        ru_at_point(10.0, 18.0, 0.0)
        raise AssertionError("Should have raised")
    except ValueError:
        print("  ru_at h_soil=0: raised ValueError ✓")

    # ru_at_point: gamma <= 0
    try:
        ru_at_point(10.0, 0.0, 5.0)
        raise AssertionError("Should have raised")
    except ValueError:
        print("  ru_at gamma=0: raised ValueError ✓")

    # ru_at_point: u < 0
    try:
        ru_at_point(-1.0, 18.0, 5.0)
        raise AssertionError("Should have raised")
    except ValueError:
        print("  ru_at u<0: raised ValueError ✓")
    print("  ✅  PASS")


def test_invalid_dupuit_inputs():
    """Dupuit functions raise ValueError for physically invalid inputs."""
    print("\n══  S8-F-2  Invalid Dupuit inputs  ══")
    # h1 < h2
    try:
        dupuit_seepage_flow(2.0, 5.0, 20.0, 1e-4)
        raise AssertionError("Should have raised")
    except ValueError:
        print("  h1 < h2: raised ValueError ✓")
    # L <= 0
    try:
        dupuit_seepage_flow(5.0, 2.0, 0.0, 1e-4)
        raise AssertionError("Should have raised")
    except ValueError:
        print("  L=0: raised ValueError ✓")
    # k <= 0
    try:
        dupuit_seepage_flow(5.0, 2.0, 20.0, 0.0)
        raise AssertionError("Should have raised")
    except ValueError:
        print("  k=0: raised ValueError ✓")
    # x out of range
    try:
        dupuit_phreatic_height(5.0, 2.0, 20.0, 25.0)
        raise AssertionError("Should have raised")
    except ValueError:
        print("  x > L: raised ValueError ✓")
    print("  ✅  PASS")


def test_build_dupuit_surface_n_points_invalid():
    """build_dupuit_surface raises if n_points < 2."""
    print("\n══  S8-F-3  build_dupuit_surface n_points < 2  ══")
    try:
        build_dupuit_surface(5.0, 0.0, 20.0, n_points=1)
        raise AssertionError("Should have raised")
    except ValueError:
        print("  n_points=1: raised ValueError ✓")
    print("  ✅  PASS")


# ============================================================
#  Runner
# ============================================================

if __name__ == "__main__":
    tests = [
        # S8-A Primitives
        test_pore_pressure_standard,
        test_pore_pressure_tension_clamped,
        test_pore_pressure_custom_gamma_w,
        test_ru_standard,
        test_ru_zero_pore_pressure,
        test_ru_inverse_gamma_h,
        test_ru_phreatic_fraction,
        # S8-B Dupuit
        test_dupuit_flow_reference,
        test_dupuit_flow_zero_head,
        test_dupuit_height_boundary_conditions,
        test_dupuit_height_midpoint,
        test_dupuit_height_parabolic_profile,
        test_dupuit_flow_proportional_to_k,
        # S8-C PhreaticSurface
        test_phreatic_surface_interpolation,
        test_phreatic_surface_extrapolation,
        test_phreatic_surface_u_at,
        test_phreatic_surface_ru_at,
        test_phreatic_surface_repr,
        test_phreatic_surface_validation,
        # S8-D build_dupuit_surface
        test_build_dupuit_surface_boundary_conditions,
        test_build_dupuit_surface_midpoint,
        test_build_dupuit_surface_offset,
        # S8-E Physics
        test_dupuit_height_decreasing_downstream,
        test_ru_increases_with_phreatic_height,
        test_dupuit_flow_increases_with_head_difference,
        test_phreatic_surface_u_decreases_with_depth,
        # S8-F Validation
        test_invalid_primitive_inputs,
        test_invalid_dupuit_inputs,
        test_build_dupuit_surface_n_points_invalid,
    ]

    passed = failed = 0
    failures = []

    print("\n" + "═"*68)
    print("  SPRINT 8 — Seepage Module (Bishop & Morgenstern 1960 / Dupuit 1863)")
    print("═"*68)

    for fn in tests:
        try:
            fn()
            passed += 1
        except Exception as e:
            import traceback
            failed += 1
            failures.append((fn.__name__, e))
            print(f"\n  ❌  FAIL  {fn.__name__}:\n      {e}")
            traceback.print_exc()

    print("\n" + "═"*68)
    print(f"  SPRINT 8 SEEPAGE RESULTS: {passed}/{passed+failed} passed, {failed} failed")
    print("═"*68)
    if failures:
        for name, err in failures:
            print(f"    - {name}: {err}")
        sys.exit(1)
    else:
        print("\n  ✅  ALL SPRINT 8 SEEPAGE TESTS PASS")
