"""
tests/test_wall_analysis.py

Validates core/wall_analysis.py against hand-calculated reference values
and physical monotonicity expectations.

Textbook fixture (hand-calculated):
    Wall:      h=5m, B=4.5m, b_toe=0.8m, t_stem=0.5/0.4m (tapered), t_base=0.6m
               b_heel = 4.5 - 0.8 - 0.5 = 3.2 m
    Backfill:  gamma=18 kN/m3, phi_k=30, c_k=0 kPa  (cohesionless sand)
    Foundation: same as backfill, delta_b = 2/3 x phi_d (default)
    Surcharge: none, dry (no water table)

    DA1 Combination 1 (M1, gG_unfav=1.35):
        Ka         = tan^2(30) = 0.3333
        Pa_char    = 0.5 x 0.3333 x 18 x 25 = 75.0 kN/m
        H_drive    = 1.35 x 75.0 = 101.25 kN/m
        N          = W_stem(54.0) + W_base(64.8) + W_soil(288.0) = 406.8 kN/m
        delta_b    = 2/3 x 30 = 20.0 deg
        R_slide    = 406.8 x tan(20) = 148.0 kN/m
        FoS_slide  = 148.0 / 101.25 = 1.462  PASS

        x_stem centroid = 0.8 + (2x0.5+0.4)/(3x0.9) x 0.5 = 1.059 m
        MR  = 54x1.059 + 64.8x2.25 + 288x2.9 = 1038.2 kN*m/m
        MO  = 101.25 x (1.667 + 0.6) = 229.5 kN*m/m
        FoS_overturn = 1038.2 / 229.5 = 4.524  PASS

    DA1 Combination 2 (M2, gG_unfav=1.00, g_phi=1.25):
        phi_d = arctan(tan30/1.25) = 24.79 deg
        Ka   approx 0.411
        Pa   approx 92.5 kN/m,   H_drive = 92.5 kN/m
        delta_b = 2/3 x 24.79 = 16.53 deg
        R_slide = 406.8 x tan(16.53) = 120.9 kN/m
        FoS_slide  approx 1.307  PASS

    Governing: DA1-C2 (lower sliding FoS_d).  Overall: PASS.

Reference:
    Craig's Soil Mechanics, 9th ed., Chapter 11 (Retaining walls).
    Eurocode 7 - EN 1997-1:2004, Section 9, Tables A.3/A.4.
    Das, B.M. (2019). Principles of Geotechnical Engineering, Chapter 11.

Run from the DesignApp root:
    python -m pytest tests/
  or:
    python tests/test_wall_analysis.py
"""
import sys, os, math

ROOT = os.path.abspath(os.path.dirname(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from models.soil          import Soil
from models.wall_geometry import RetainingWall
from models.surcharge     import UniformSurcharge
from core.wall_analysis   import (
    analyse_wall_da1,
    WallResult, WallCombinationResult,
    SlidingResult, OverturningResult, WallBearingCheck,
)
from core.rankine_coulomb import ka_rankine


# ---------------------------------------------------------------------------
#  Shared fixtures
# ---------------------------------------------------------------------------

WALL = RetainingWall(
    h_wall      = 5.0,
    b_base      = 4.5,
    b_toe       = 0.8,
    t_stem_base = 0.5,
    t_stem_top  = 0.4,
    t_base      = 0.6,
    delta_wall  = 0.0,
    delta_base  = None,
)

SOIL_SAND   = Soil("Dense Sand",  unit_weight=18.0, friction_angle=30, cohesion=0.0)
SOIL_WEAK   = Soil("Loose Sand",  unit_weight=17.0, friction_angle=22, cohesion=0.0)
SOIL_STRONG = Soil("Very Dense",  unit_weight=20.0, friction_angle=38, cohesion=0.0)
SOIL_CLAY   = Soil("Stiff Clay",  unit_weight=19.0, friction_angle=25, cohesion=10.0)

SURCHARGE_10 = UniformSurcharge(q=10.0)

TOL_PCT = 1.5   # percent tolerance for textbook comparisons


def _pct(a, b):
    return 100.0 * abs(a - b) / max(abs(b), 1e-9)


# ---------------------------------------------------------------------------
#  Test 1 - Smoke test
# ---------------------------------------------------------------------------

def test_analyse_returns_valid_result():
    """analyse_wall_da1 must return a fully populated WallResult."""
    result = analyse_wall_da1(WALL, SOIL_SAND, SOIL_SAND)

    print("\n" + "="*70)
    print("  TEST 1 - Smoke Test")
    print("="*70)
    print(result.summary())

    assert isinstance(result, WallResult)
    assert isinstance(result.comb1, WallCombinationResult)
    assert isinstance(result.comb2, WallCombinationResult)
    assert isinstance(result.comb1.sliding, SlidingResult)
    assert isinstance(result.comb1.overturn, OverturningResult)
    assert isinstance(result.comb1.bearing, WallBearingCheck)
    assert result.comb1.label == "DA1-C1"
    assert result.comb2.label == "DA1-C2"
    assert result.governing in (result.comb1, result.comb2)
    assert result.comb1.sliding.fos_d > 0
    assert result.comb2.sliding.fos_d > 0
    assert result.comb1.overturn.fos_d > 0

    print("\n  PASS  test_analyse_returns_valid_result")


# ---------------------------------------------------------------------------
#  Test 2 - Textbook validation
# ---------------------------------------------------------------------------

def test_textbook_reference_values():
    """
    Validates C1 and C2 FoS against hand-calculated reference (see module
    docstring).  Tolerance: +/-1.5% on all quantities.
    """
    result = analyse_wall_da1(WALL, SOIL_SAND, SOIL_SAND)
    c1 = result.comb1
    c2 = result.comb2

    print("\n" + "="*70)
    print("  TEST 2 - Textbook Reference Validation")
    print("="*70)
    print(f"  {'Quantity':<30}  {'Expected':>10}  {'Computed':>10}  {'Err%':>7}")
    print("  " + "-"*60)

    checks = [
        ("Ka  (C1, Rankine phi=30)",    0.3333,  c1.ka,                 TOL_PCT),
        ("Pa_char C1 (kN/m)",           75.00,   c1.Pa,                 TOL_PCT),
        ("FoS_sliding  C1",              1.462,   c1.sliding.fos_d,      TOL_PCT),
        ("FoS_overturn C1",              4.524,   c1.overturn.fos_d,     TOL_PCT),
        ("FoS_sliding  C2",              1.307,   c2.sliding.fos_d,      2.0),
        ("N_total C1 (kN/m)",           406.8,   c1.sliding.N_total,    TOL_PCT),
    ]

    for label, expected, computed, tol in checks:
        err = _pct(computed, expected)
        ok  = "PASS" if err <= tol else "FAIL"
        print(f"  {ok}  {label:<30}  {expected:>10.3f}  {computed:>10.3f}  {err:>6.2f}%")
        assert err <= tol, \
            f"FAIL: {label} = {computed:.4f}, expected {expected:.4f} (err {err:.2f}%)"

    assert result.governing.label == "DA1-C2", \
        f"FAIL: expected DA1-C2 to govern, got {result.governing.label}"
    assert result.passes, "FAIL: this adequately sized wall should PASS"
    print(f"  PASS  Governing = {result.governing.label}  Overall = PASS")
    print("\n  PASS  test_textbook_reference_values")


# ---------------------------------------------------------------------------
#  Test 3 - Monotonicity: stronger foundation -> higher sliding FoS
# ---------------------------------------------------------------------------

def test_stronger_foundation_increases_sliding_fos():
    """Higher phi on foundation -> larger delta_b -> higher R_slide -> higher FoS."""
    r_weak   = analyse_wall_da1(WALL, SOIL_SAND, SOIL_WEAK)
    r_strong = analyse_wall_da1(WALL, SOIL_SAND, SOIL_STRONG)

    print("\n" + "="*70)
    print("  TEST 3 - Foundation Strength Monotonicity (Sliding)")
    print("="*70)
    for lbl, r, s in [("Weak  found.", r_weak, SOIL_WEAK),
                       ("Strong found.", r_strong, SOIL_STRONG)]:
        print(f"  {lbl} phi={s.phi_k}:  C1={r.comb1.sliding.fos_d:.3f}  C2={r.comb2.sliding.fos_d:.3f}")

    assert r_strong.comb1.sliding.fos_d > r_weak.comb1.sliding.fos_d, "FAIL: C1 monotonicity"
    assert r_strong.comb2.sliding.fos_d > r_weak.comb2.sliding.fos_d, "FAIL: C2 monotonicity"
    print("\n  PASS  test_stronger_foundation_increases_sliding_fos")


# ---------------------------------------------------------------------------
#  Test 4 - Monotonicity: surcharge reduces FoS
# ---------------------------------------------------------------------------

def test_surcharge_reduces_fos():
    """Surcharge adds horizontal driving -> FoS_slide and FoS_overturn both fall."""
    r0  = analyse_wall_da1(WALL, SOIL_SAND, SOIL_SAND)
    rq  = analyse_wall_da1(WALL, SOIL_SAND, SOIL_SAND, surcharge=SURCHARGE_10)

    print("\n" + "="*70)
    print("  TEST 4 - Surcharge Reduces FoS")
    print("="*70)
    for lbl, a, b in [("C1", r0.comb1, rq.comb1), ("C2", r0.comb2, rq.comb2)]:
        print(f"  {lbl}: slide {a.sliding.fos_d:.3f}->{b.sliding.fos_d:.3f}  "
              f"overturn {a.overturn.fos_d:.3f}->{b.overturn.fos_d:.3f}")
        assert b.sliding.fos_d  < a.sliding.fos_d,  f"FAIL [{lbl}]: slide should decrease"
        assert b.overturn.fos_d < a.overturn.fos_d, f"FAIL [{lbl}]: overturn should decrease"
    print("\n  PASS  test_surcharge_reduces_fos")


# ---------------------------------------------------------------------------
#  Test 5 - Monotonicity: weaker backfill -> lower sliding FoS
# ---------------------------------------------------------------------------

def test_weaker_backfill_reduces_sliding_fos():
    """Weaker backfill -> higher Ka -> more thrust -> lower FoS_sliding."""
    r_strong = analyse_wall_da1(WALL, SOIL_STRONG, SOIL_SAND)
    r_weak   = analyse_wall_da1(WALL, SOIL_WEAK,   SOIL_SAND)

    print("\n" + "="*70)
    print("  TEST 5 - Backfill Strength Effect on Sliding FoS")
    print("="*70)
    for lbl, r, s in [("Strong backfill", r_strong, SOIL_STRONG),
                       ("Weak   backfill", r_weak,   SOIL_WEAK)]:
        print(f"  {lbl} phi={s.phi_k}:  C1={r.comb1.sliding.fos_d:.3f}  C2={r.comb2.sliding.fos_d:.3f}")

    assert r_weak.comb1.sliding.fos_d < r_strong.comb1.sliding.fos_d, "FAIL: C1"
    assert r_weak.comb2.sliding.fos_d < r_strong.comb2.sliding.fos_d, "FAIL: C2"
    print("\n  PASS  test_weaker_backfill_reduces_sliding_fos")


# ---------------------------------------------------------------------------
#  Test 6 - EC7 pass/fail logic consistency
# ---------------------------------------------------------------------------

def test_ec7_pass_fail_logic():
    """overall .passes iff BOTH combinations pass (slide AND overturn each)."""
    r_ok   = analyse_wall_da1(WALL, SOIL_SAND, SOIL_SAND)
    r_fail = analyse_wall_da1(WALL, SOIL_SAND, SOIL_WEAK, surcharge=SURCHARGE_10)

    print("\n" + "="*70)
    print("  TEST 6 - EC7 Pass / Fail Logic")
    print("="*70)

    for lbl, res in [("Adequate", r_ok), ("Marginal", r_fail)]:
        c1_ok = res.comb1.sliding.passes and res.comb1.overturn.passes
        c2_ok = res.comb2.sliding.passes and res.comb2.overturn.passes
        expected_overall = c1_ok and c2_ok

        assert res.comb1.passes == c1_ok,      f"FAIL [{lbl}]: comb1.passes"
        assert res.comb2.passes == c2_ok,      f"FAIL [{lbl}]: comb2.passes"
        assert res.passes == expected_overall, f"FAIL [{lbl}]: overall passes"

        print(f"  {lbl:10s}: C1={'PASS' if c1_ok else 'FAIL'}  "
              f"C2={'PASS' if c2_ok else 'FAIL'}  "
              f"Overall={'PASS' if res.passes else 'FAIL'}")

    print("\n  PASS  test_ec7_pass_fail_logic")


# ---------------------------------------------------------------------------
#  Test 7 - Bearing: eccentricity and base pressures self-consistent
# ---------------------------------------------------------------------------

def test_bearing_pressure_self_consistent():
    """
    middle_third must match e <= B/6.
    B_eff must be in (0, B].
    For middle-third case: q_avg = (q_max + q_min)/2 approx N/B.
    """
    result = analyse_wall_da1(WALL, SOIL_SAND, SOIL_SAND)
    B = WALL.b_base

    print("\n" + "="*70)
    print("  TEST 7 - Bearing Pressure Self-Consistency")
    print("="*70)

    for lbl, comb in [("C1", result.comb1), ("C2", result.comb2)]:
        bp = comb.base_press
        b = bp
        print(f"  {lbl}: N={b.N_total:.1f}  e={b.e:.3f}  B/6={B/6:.3f}  "
              f"middle_third={b.middle_third}  q_max={b.q_max:.2f}  q_min={b.q_min:.2f}")

        assert b.middle_third == (b.e <= B / 6.0), f"FAIL [{lbl}]: middle_third flag"
        assert 0 < b.B_eff <= B,                   f"FAIL [{lbl}]: B_eff={b.B_eff:.3f} out of range"

        if b.middle_third:
            q_avg_computed = (b.q_max + b.q_min) / 2.0
            q_avg_expected = b.N_total / B
            err = _pct(q_avg_computed, q_avg_expected)
            assert err < 5.0, f"FAIL [{lbl}]: q_avg err={err:.1f}%"

    print("\n  PASS  test_bearing_pressure_self_consistent")


# ---------------------------------------------------------------------------
#  Test 8 - Wall friction: Coulomb Ka reduces driving, raises FoS
# ---------------------------------------------------------------------------

def test_wall_friction_reduces_driving():
    """delta_wall > 0 selects Coulomb Ka < Rankine Ka -> less thrust -> higher FoS."""
    w_smooth = RetainingWall(h_wall=5.0, b_base=4.5, b_toe=0.8,
                             t_stem_base=0.5, t_stem_top=0.4, t_base=0.6,
                             delta_wall=0.0)
    w_rough  = RetainingWall(h_wall=5.0, b_base=4.5, b_toe=0.8,
                             t_stem_base=0.5, t_stem_top=0.4, t_base=0.6,
                             delta_wall=20.0)

    r_s = analyse_wall_da1(w_smooth, SOIL_SAND, SOIL_SAND)
    r_r = analyse_wall_da1(w_rough,  SOIL_SAND, SOIL_SAND)

    print("\n" + "="*70)
    print("  TEST 8 - Wall Friction: Coulomb < Rankine Ka")
    print("="*70)
    print(f"  Smooth (delta=0):  Ka={r_s.comb1.ka:.4f}  FoS_slide_C1={r_s.comb1.sliding.fos_d:.3f}")
    print(f"  Rough  (delta=20): Ka={r_r.comb1.ka:.4f}  FoS_slide_C1={r_r.comb1.sliding.fos_d:.3f}")

    assert r_r.comb1.ka < r_s.comb1.ka, "FAIL: Coulomb Ka should be < Rankine Ka"
    assert r_r.comb1.sliding.fos_d > r_s.comb1.sliding.fos_d, "FAIL: FoS should increase"
    print("\n  PASS  test_wall_friction_reduces_driving")


# ---------------------------------------------------------------------------
#  Test 9 - Cohesive backfill reduces thrust and raises FoS
# ---------------------------------------------------------------------------

def test_cohesive_backfill_reduces_thrust():
    """Cohesion creates tension zone -> lower Pa -> higher FoS_sliding."""
    r_fric = analyse_wall_da1(WALL, SOIL_SAND, SOIL_SAND)
    r_clay = analyse_wall_da1(WALL, SOIL_CLAY, SOIL_SAND)

    print("\n" + "="*70)
    print("  TEST 9 - Cohesive Backfill Reduces Active Thrust")
    print("="*70)
    print(f"  Cohesionless: Pa_C1={r_fric.comb1.Pa:.2f}  FoS_slide_C1={r_fric.comb1.sliding.fos_d:.3f}")
    print(f"  Clay backfill: Pa_C1={r_clay.comb1.Pa:.2f}  FoS_slide_C1={r_clay.comb1.sliding.fos_d:.3f}")

    assert r_clay.comb1.Pa < r_fric.comb1.Pa, "FAIL: cohesive Pa should be lower"
    assert r_clay.comb1.sliding.fos_d > r_fric.comb1.sliding.fos_d, "FAIL: FoS should increase"
    print("\n  PASS  test_cohesive_backfill_reduces_thrust")


# ---------------------------------------------------------------------------
#  Test 10 - Edge cases raise ValueError
# ---------------------------------------------------------------------------

def test_invalid_geometry_raises():
    """Invalid RetainingWall arguments must raise ValueError."""
    print("\n" + "="*70)
    print("  TEST 10 - Edge Cases / Invalid Parameters")
    print("="*70)

    try:
        RetainingWall(h_wall=5, b_base=3.0, b_toe=2.0,
                      t_stem_base=1.5, t_stem_top=0.4, t_base=0.5)
        assert False, "should raise for negative heel"
    except ValueError as e:
        print(f"  PASS  negative heel: {e}")

    try:
        RetainingWall(h_wall=1.0, b_base=3.0, b_toe=0.5,
                      t_stem_base=0.4, t_stem_top=0.3, t_base=1.0)
        assert False, "should raise for t_base >= h_wall"
    except ValueError as e:
        print(f"  PASS  t_base>=h_wall: {e}")

    try:
        RetainingWall(h_wall=5, b_base=4.0, b_toe=0.5,
                      t_stem_base=0.5, t_stem_top=0.4, t_base=0.5,
                      alpha_wall=30.0)
        assert False, "should raise for alpha_wall=30"
    except ValueError as e:
        print(f"  PASS  alpha_wall=30: {e}")

    print("\n  PASS  test_invalid_geometry_raises")


# ---------------------------------------------------------------------------
#  Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_analyse_returns_valid_result()
    test_textbook_reference_values()
    test_stronger_foundation_increases_sliding_fos()
    test_surcharge_reduces_fos()
    test_weaker_backfill_reduces_sliding_fos()
    test_ec7_pass_fail_logic()
    test_bearing_pressure_self_consistent()
    test_wall_friction_reduces_driving()
    test_cohesive_backfill_reduces_thrust()
    test_invalid_geometry_raises()

    print("\n" + "="*70)
    print("  ALL wall_analysis tests passed.")
    print("="*70 + "\n")
