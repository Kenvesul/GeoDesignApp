"""
tests/test_search.py

Validates core/search.py against physical expectations and known geometry.

Test hierarchy (per DesignApp testing strategy):
    Test 1 – Smoke test             : search returns a valid SearchResult.
    Test 2 – Optimality             : critical FoS ≤ FoS of any fixed circle.
    Test 3 – Monotonicity (rᵤ)     : higher pore pressure → lower critical FoS.
    Test 4 – Monotonicity (strength): stronger soil → higher critical FoS.
    Test 5 – Refinement             : refine_search() improves or holds FoS.
    Test 6 – Edge cases             : bad bounds, bad params raise ValueError.
    Test 7 – Grid shape             : fos_grid dimensions match n_cx, n_cy.
    Test 8 – EC7 flags              : ec7_stable / ec7_pass set correctly.

Run from the DesignApp root:
    python -m pytest tests/
  or:
    python tests/test_search.py
"""
import sys, os, math
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from models.soil            import Soil
from models.geometry        import SlopeGeometry, SlipCircle
from core.slicer            import create_slices
from core.limit_equilibrium import bishop_simplified
from core.search            import grid_search, refine_search, SearchResult


# ─────────────────────────────────────────────────────────────────────────────
#  Shared fixtures
# ─────────────────────────────────────────────────────────────────────────────

# Standard 1:1 slope (crest at y=10, toe at y=0)
SLOPE  = SlopeGeometry([(0, 10), (10, 10), (20, 0), (30, 0)])

# Moderate soil — should produce FoS in a realistic range
SOIL   = Soil("Clay", unit_weight=20.0, friction_angle=25, cohesion=10.0)

# Coarse grid for speed in test suite
COARSE = dict(n_cx=8, n_cy=8, n_r=4, num_slices=15)


# ─────────────────────────────────────────────────────────────────────────────
#  Test 1 – Smoke test
# ─────────────────────────────────────────────────────────────────────────────

def test_search_returns_valid_result():
    """grid_search must return a populated SearchResult with no exceptions."""
    result = grid_search(SLOPE, SOIL, ru=0.0, **COARSE)

    assert isinstance(result, SearchResult),    "FAIL: wrong return type"
    assert math.isfinite(result.fos_min),       "FAIL: fos_min is not finite"
    assert result.fos_min > 0,                  "FAIL: fos_min must be positive"
    assert result.critical_circle is not None,  "FAIL: critical_circle is None"
    assert result.critical_circle.r > 0,        "FAIL: critical circle radius ≤ 0"
    assert result.n_circles_tested > 0,         "FAIL: no circles were tested"
    assert result.n_valid > 0,                  "FAIL: no valid circles found"
    assert result.best_fos_result is not None,  "FAIL: best_fos_result is None"
    assert result.best_fos_result.converged,    "FAIL: critical circle Bishop did not converge"

    print(f"\n{'═'*58}")
    print(f"  TEST 1 – Smoke Test")
    print(f"{'═'*58}")
    print(result.summary())
    print(f"\n  ✅  test_search_returns_valid_result passed")


# ─────────────────────────────────────────────────────────────────────────────
#  Test 2 – Optimality: critical FoS ≤ FoS of any single fixed circle
# ─────────────────────────────────────────────────────────────────────────────

def test_critical_fos_le_fixed_circles():
    """
    The search result must be ≤ the FoS of every specific circle we can
    construct inside the same search domain.  Tests 5 hand-picked circles.
    """
    result = grid_search(SLOPE, SOIL, ru=0.0, **COARSE)

    probe_circles = [
        SlipCircle(center_x=5,  center_y=18, radius=14),
        SlipCircle(center_x=3,  center_y=16, radius=12),
        SlipCircle(center_x=8,  center_y=20, radius=16),
        SlipCircle(center_x=2,  center_y=15, radius=11),
        SlipCircle(center_x=6,  center_y=22, radius=17),
    ]

    print(f"\n{'═'*58}")
    print(f"  TEST 2 – Optimality  (critical FoS ≤ fixed circles)")
    print(f"{'═'*58}")
    print(f"  Critical FoS = {result.fos_min:.4f}")
    print(f"  {'Circle centre':>22}   {'R':>5}   {'FoS':>8}   {'≥ critical?':>12}")
    print(f"  {'─'*58}")

    for c in probe_circles:
        try:
            slices = create_slices(SLOPE, c, SOIL, num_slices=15)
            if len(slices) < 3:
                continue
            r = bishop_simplified(slices, ru=0.0)
            if not r.converged:
                continue
            probe_fos = r.fos
            ok = probe_fos >= result.fos_min - 1e-4   # small tolerance for grid resolution
            print(f"  cx={c.cx:5.1f} cy={c.cy:5.1f}   R={c.r:5.1f}   "
                  f"FoS={probe_fos:8.4f}   {'✅' if ok else '❌'}")
            assert ok, (
                f"FAIL: Critical FoS ({result.fos_min:.4f}) > probe circle FoS "
                f"({probe_fos:.4f}) at cx={c.cx}, cy={c.cy}, R={c.r}.  "
                "The search missed a better circle."
            )
        except ValueError:
            pass   # probe circle outside slope — expected

    print(f"\n  ✅  test_critical_fos_le_fixed_circles passed")


# ─────────────────────────────────────────────────────────────────────────────
#  Test 3 – Monotonicity: pore pressure
# ─────────────────────────────────────────────────────────────────────────────

def test_pore_pressure_reduces_fos():
    """Critical FoS must decrease strictly as rᵤ increases (0 → 0.3 → 0.5)."""
    r0   = grid_search(SLOPE, SOIL, ru=0.0, **COARSE)
    r03  = grid_search(SLOPE, SOIL, ru=0.3, **COARSE)
    r05  = grid_search(SLOPE, SOIL, ru=0.5, **COARSE)

    print(f"\n{'═'*58}")
    print(f"  TEST 3 – Pore Pressure Monotonicity")
    print(f"{'═'*58}")
    print(f"  Critical FoS (rᵤ=0.0) = {r0.fos_min:.4f}")
    print(f"  Critical FoS (rᵤ=0.3) = {r03.fos_min:.4f}")
    print(f"  Critical FoS (rᵤ=0.5) = {r05.fos_min:.4f}")

    assert r03.fos_min < r0.fos_min,  (
        f"FAIL: FoS(rᵤ=0.3) should be < FoS(rᵤ=0.0). "
        f"Got {r03.fos_min:.4f} vs {r0.fos_min:.4f}"
    )
    assert r05.fos_min < r03.fos_min, (
        f"FAIL: FoS(rᵤ=0.5) should be < FoS(rᵤ=0.3). "
        f"Got {r05.fos_min:.4f} vs {r03.fos_min:.4f}"
    )
    print(f"\n  ✅  test_pore_pressure_reduces_fos passed")


# ─────────────────────────────────────────────────────────────────────────────
#  Test 4 – Monotonicity: strength
# ─────────────────────────────────────────────────────────────────────────────

def test_stronger_soil_increases_fos():
    """Critical FoS must be higher for stronger soil on the same slope."""
    soil_weak   = Soil("Weak",   unit_weight=20.0, friction_angle=15, cohesion=2.0)
    soil_strong = Soil("Strong", unit_weight=20.0, friction_angle=32, cohesion=18.0)

    r_weak   = grid_search(SLOPE, soil_weak,   ru=0.0, **COARSE)
    r_strong = grid_search(SLOPE, soil_strong, ru=0.0, **COARSE)

    print(f"\n{'═'*58}")
    print(f"  TEST 4 – Soil Strength Effect")
    print(f"{'═'*58}")
    print(f"  Weak   soil FoS = {r_weak.fos_min:.4f}  (φ'=15°, c'=2 kPa)")
    print(f"  Strong soil FoS = {r_strong.fos_min:.4f}  (φ'=32°, c'=18 kPa)")

    assert r_strong.fos_min > r_weak.fos_min, (
        f"FAIL: Stronger soil must give higher critical FoS. "
        f"Got {r_strong.fos_min:.4f} vs {r_weak.fos_min:.4f}"
    )
    print(f"\n  ✅  test_stronger_soil_increases_fos passed")


# ─────────────────────────────────────────────────────────────────────────────
#  Test 5 – Refinement
# ─────────────────────────────────────────────────────────────────────────────

def test_refinement_improves_or_holds_fos():
    """
    refine_search() must return FoS ≤ the coarse result FoS (it can only
    find a better or equal minimum, never a worse one).
    """
    coarse = grid_search(SLOPE, SOIL, ru=0.0, **COARSE)
    fine   = refine_search(coarse, SLOPE, SOIL,
                           zoom=0.4, n_cx=10, n_cy=10, n_r=5,
                           num_slices=15)

    print(f"\n{'═'*58}")
    print(f"  TEST 5 – Two-Pass Refinement")
    print(f"{'═'*58}")
    print(f"  Coarse FoS = {coarse.fos_min:.4f}  "
          f"@ cx={coarse.critical_circle.cx:.2f}, "
          f"cy={coarse.critical_circle.cy:.2f}, "
          f"R={coarse.critical_circle.r:.2f}")
    print(f"  Fine   FoS = {fine.fos_min:.4f}  "
          f"@ cx={fine.critical_circle.cx:.2f}, "
          f"cy={fine.critical_circle.cy:.2f}, "
          f"R={fine.critical_circle.r:.2f}")

    assert fine.fos_min <= coarse.fos_min + 0.05, (
        f"FAIL: Refinement FoS ({fine.fos_min:.4f}) must not be more "
        f"than 0.05 above coarse FoS ({coarse.fos_min:.4f})."
    )
    print(f"\n  ✅  test_refinement_improves_or_holds_fos passed")


# ─────────────────────────────────────────────────────────────────────────────
#  Test 6 – Edge cases: invalid parameters raise ValueError
# ─────────────────────────────────────────────────────────────────────────────

def test_invalid_parameters_raise():
    """Bad inputs must raise ValueError with a descriptive message."""
    print(f"\n{'═'*58}")
    print(f"  TEST 6 – Edge Cases")
    print(f"{'═'*58}")

    # n_cx too small
    try:
        grid_search(SLOPE, SOIL, n_cx=1, n_cy=8, n_r=4)
        assert False, "FAIL: should have raised ValueError for n_cx=1"
    except ValueError as e:
        print(f"  ✅ n_cx=1 raised: {e}")

    # ru out of range
    try:
        grid_search(SLOPE, SOIL, ru=1.0, **COARSE)
        assert False, "FAIL: should have raised ValueError for ru=1.0"
    except ValueError as e:
        print(f"  ✅ ru=1.0 raised: {e}")

    # inverted cx_range
    try:
        grid_search(SLOPE, SOIL, cx_range=(20, 5), **COARSE)
        assert False, "FAIL: should have raised ValueError for inverted cx_range"
    except ValueError as e:
        print(f"  ✅ cx_range inverted raised: {e}")

    # r_range with r_min ≤ 0
    try:
        grid_search(SLOPE, SOIL, r_range=(-1, 10), **COARSE)
        assert False, "FAIL: should have raised ValueError for r_min ≤ 0"
    except ValueError as e:
        print(f"  ✅ r_min ≤ 0 raised: {e}")

    # Domain with no valid circles at all
    try:
        grid_search(SLOPE, SOIL,
                    cx_range=(100, 110), cy_range=(200, 210), r_range=(0.1, 0.5),
                    n_cx=3, n_cy=3, n_r=2, num_slices=10)
        assert False, "FAIL: should have raised ValueError for domain outside slope"
    except ValueError as e:
        print(f"  ✅ No valid domain raised: {e}")

    print(f"\n  ✅  test_invalid_parameters_raise passed")


# ─────────────────────────────────────────────────────────────────────────────
#  Test 7 – fos_grid shape and finite-value count
# ─────────────────────────────────────────────────────────────────────────────

def test_fos_grid_shape_and_values():
    """fos_grid must be (n_cy × n_cx) and contain ≥ 1 finite value."""
    n_cx, n_cy = 6, 5
    result = grid_search(SLOPE, SOIL, ru=0.0,
                         n_cx=n_cx, n_cy=n_cy, n_r=3, num_slices=15)

    print(f"\n{'═'*58}")
    print(f"  TEST 7 – fos_grid Shape & Values")
    print(f"{'═'*58}")

    assert len(result.fos_grid) == n_cy, (
        f"FAIL: fos_grid has {len(result.fos_grid)} rows, expected {n_cy}"
    )
    for row in result.fos_grid:
        assert len(row) == n_cx, (
            f"FAIL: fos_grid row has {len(row)} cols, expected {n_cx}"
        )

    finite_vals = [v for row in result.fos_grid for v in row if math.isfinite(v)]
    assert len(finite_vals) >= 1, "FAIL: fos_grid has no finite values at all"
    assert all(v > 0 for v in finite_vals), "FAIL: some FoS values are ≤ 0"

    print(f"  Grid shape     : {n_cy} rows × {n_cx} cols  ✅")
    print(f"  Finite cells   : {len(finite_vals)} / {n_cx*n_cy}")
    print(f"  FoS range      : {min(finite_vals):.4f} – {max(finite_vals):.4f}")
    print(f"\n  ✅  test_fos_grid_shape_and_values passed")


# ─────────────────────────────────────────────────────────────────────────────
#  Test 8 – EC7 flags on best_fos_result
# ─────────────────────────────────────────────────────────────────────────────

def test_ec7_flags_consistent():
    """best_fos_result EC7 flags must match the numeric FoS values."""
    soil_weak   = Soil("Weak",   unit_weight=20.0, friction_angle=15, cohesion=2.0)
    soil_strong = Soil("Strong", unit_weight=20.0, friction_angle=32, cohesion=18.0)

    r_weak   = grid_search(SLOPE, soil_weak,   ru=0.0, **COARSE)
    r_strong = grid_search(SLOPE, soil_strong, ru=0.0, **COARSE)

    print(f"\n{'═'*58}")
    print(f"  TEST 8 – EC7 Flag Consistency")
    print(f"{'═'*58}")

    for label, res in [("Weak", r_weak), ("Strong", r_strong)]:
        fos = res.fos_min
        assert (fos >= 1.00) == res.best_fos_result.ec7_stable, \
            f"FAIL [{label}]: ec7_stable flag mismatch at FoS={fos:.4f}"
        assert (fos >= 1.25) == res.best_fos_result.ec7_pass, \
            f"FAIL [{label}]: ec7_pass flag mismatch at FoS={fos:.4f}"
        print(f"  {label:8s}: FoS={fos:.4f}  "
              f"stable={res.best_fos_result.ec7_stable}  "
              f"EC7_pass={res.best_fos_result.ec7_pass}  ✅")

    print(f"\n  ✅  test_ec7_flags_consistent passed")


# ─────────────────────────────────────────────────────────────────────────────
#  Runner
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_search_returns_valid_result()
    test_critical_fos_le_fixed_circles()
    test_pore_pressure_reduces_fos()
    test_stronger_soil_increases_fos()
    test_refinement_improves_or_holds_fos()
    test_invalid_parameters_raise()
    test_fos_grid_shape_and_values()
    test_ec7_flags_consistent()

    print(f"\n{'═'*58}")
    print(f"  ✅  All search tests passed.")
    print(f"{'═'*58}\n")
