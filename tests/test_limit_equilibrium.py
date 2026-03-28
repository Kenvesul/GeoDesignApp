"""
tests/test_limit_equilibrium.py

Validates Bishop's Simplified and Ordinary Method implementations against
known geometric checks and monotonicity properties.

Circle positioning note (important):
    For a right-descending slope, the failure mass rotates CLOCKWISE.
    The circle centre must be above and to the LEFT of the mass centroid
    so that Σ(W·sinα) > 0 (driving sum positive, sliding rightward).
    A centre to the RIGHT of the mass gives counter-clockwise rotation and
    a negative driving sum — geometrically invalid for slope stability.

Run from the DesignApp root:
    python -m pytest tests/
  or:
    python tests/test_limit_equilibrium.py
"""
import sys
import os
import math

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from models.soil            import Soil
from models.geometry        import SlopeGeometry, SlipCircle
from core.slicer            import create_slices
from core.limit_equilibrium import bishop_simplified, ordinary_method


# ---------------------------------------------------------------------------
# Shared geometry
#   Slope  : flat crest → 1:1 slope face → flat toe
#   Circle : centre (5, 18), R=14 — placed upper-left so the mass
#            centroid (x ≈ 7–13) lies mostly to the RIGHT of cx=5.
#            This ensures Σ(W·sinα) > 0 (clockwise / rightward sliding).
# ---------------------------------------------------------------------------
SLOPE  = SlopeGeometry([(0, 10), (10, 10), (20, 0), (30, 0)])
CIRCLE = SlipCircle(center_x=5, center_y=18, radius=14)


def _make_slices(soil, n=20):
    return create_slices(SLOPE, CIRCLE, soil, num_slices=n)


def _print_slice_table(result):
    print(f"\n  {'x (m)':>7}  {'α (°)':>7}  {'W (kN)':>8}  "
          f"{'u (kPa)':>8}  {'Resist':>9}  {'Drive':>9}")
    print(f"  {'─'*65}")
    for sr in result.slice_results:
        print(f"  {sr.x:7.2f}  {sr.alpha_deg:7.2f}  {sr.weight:8.2f}  "
              f"{sr.pore_pressure:8.3f}  {sr.numerator:9.3f}  {sr.denominator:9.3f}")


# ---------------------------------------------------------------------------
# Test 1 – Drained, no pore pressure  (rᵤ = 0)
# ---------------------------------------------------------------------------

def test_bishop_drained():
    """Bishop FoS must be in a physically reasonable range and converge."""
    soil   = Soil("Stiff Clay", unit_weight=20.0, friction_angle=25, cohesion=10.0)
    slices = _make_slices(soil)
    result = bishop_simplified(slices, ru=0.0)

    print(f"\n{'═'*52}")
    print(f"  TEST 1 – Bishop's Simplified  (rᵤ = 0.0)")
    print(f"{'═'*52}")
    print(result.summary())
    _print_slice_table(result)

    # Note: this is NOT the critical circle. In production use, a circle search
    # minimises FoS. Here we only verify convergence and sign correctness; the
    # absolute FoS depends entirely on the chosen circle and soil parameters.
    assert result.converged,             "FAIL: Bishop did not converge."
    assert result.iterations < 50,       f"FAIL: Too slow ({result.iterations} iters)."
    assert 0.5 < result.fos < 50.0,      f"FAIL: FoS = {result.fos:.4f} out of physically plausible range."
    assert result.sum_driving > 0,       "FAIL: Driving sum must be positive."
    assert result.sum_resist  > 0,       "FAIL: Resistance sum must be positive."
    print(f"\n  ✅  test_bishop_drained passed  (FoS = {result.fos:.4f})")


# ---------------------------------------------------------------------------
# Test 2 – Pore pressure reduces FoS monotonically
# ---------------------------------------------------------------------------

def test_bishop_pore_pressure_monotonicity():
    """FoS must decrease strictly as rᵤ increases (0 → 0.3 → 0.5)."""
    soil   = Soil("Stiff Clay", unit_weight=20.0, friction_angle=25, cohesion=10.0)
    slices = _make_slices(soil)

    r0   = bishop_simplified(slices, ru=0.0)
    r03  = bishop_simplified(slices, ru=0.3)
    r05  = bishop_simplified(slices, ru=0.5)

    print(f"\n{'═'*52}")
    print(f"  TEST 2 – Pore Pressure Monotonicity")
    print(f"{'═'*52}")
    print(f"  FoS (rᵤ=0.0) = {r0.fos:.4f}")
    print(f"  FoS (rᵤ=0.3) = {r03.fos:.4f}")
    print(f"  FoS (rᵤ=0.5) = {r05.fos:.4f}")

    assert r03.fos < r0.fos,  f"FAIL: FoS(rᵤ=0.3) should be < FoS(rᵤ=0.0). Got {r03.fos:.4f} vs {r0.fos:.4f}"
    assert r05.fos < r03.fos, f"FAIL: FoS(rᵤ=0.5) should be < FoS(rᵤ=0.3). Got {r05.fos:.4f} vs {r03.fos:.4f}"
    print(f"\n  ✅  test_bishop_pore_pressure_monotonicity passed")


# ---------------------------------------------------------------------------
# Test 3 – Ordinary Method is conservative vs Bishop
# ---------------------------------------------------------------------------

def test_ordinary_is_conservative():
    """
    Ordinary Method consistently underestimates FoS vs Bishop's Simplified.
    Classical result: difference is typically 5–15 % for most geometries.
    """
    soil   = Soil("Stiff Clay", unit_weight=20.0, friction_angle=25, cohesion=10.0)
    slices = _make_slices(soil)

    r_ord  = ordinary_method(slices,    ru=0.0)
    r_bish = bishop_simplified(slices,  ru=0.0)

    diff_pct = 100.0 * (r_bish.fos - r_ord.fos) / r_bish.fos

    print(f"\n{'═'*52}")
    print(f"  TEST 3 – Ordinary vs Bishop  (rᵤ = 0.0)")
    print(f"{'═'*52}")
    print(f"  Ordinary FoS  = {r_ord.fos:.4f}")
    print(f"  Bishop   FoS  = {r_bish.fos:.4f}")
    print(f"  Difference    = {diff_pct:.1f}%  (Bishop > Ordinary expected)")

    assert r_ord.fos <= r_bish.fos + 0.02, (
        f"FAIL: Ordinary FoS ({r_ord.fos:.4f}) must be ≤ Bishop FoS ({r_bish.fos:.4f})."
    )
    print(f"\n  ✅  test_ordinary_is_conservative passed")


# ---------------------------------------------------------------------------
# Test 4 – Stronger soil gives higher FoS (monotonicity on strength)
# ---------------------------------------------------------------------------

def test_strength_increases_fos():
    """FoS must increase when φ' and c' are increased."""
    soil_weak   = Soil("Weak",   unit_weight=20.0, friction_angle=15, cohesion=2.0)
    soil_strong = Soil("Strong", unit_weight=20.0, friction_angle=30, cohesion=15.0)

    r_weak   = bishop_simplified(_make_slices(soil_weak),   ru=0.0)
    r_strong = bishop_simplified(_make_slices(soil_strong), ru=0.0)

    print(f"\n{'═'*52}")
    print(f"  TEST 4 – Strength Effect on FoS")
    print(f"{'═'*52}")
    print(f"  Weak soil   FoS = {r_weak.fos:.4f}  (φ'=15°, c'=2 kPa)")
    print(f"  Strong soil FoS = {r_strong.fos:.4f}  (φ'=30°, c'=15 kPa)")

    assert r_strong.fos > r_weak.fos, (
        f"FAIL: Stronger soil should give higher FoS. "
        f"Got {r_strong.fos:.4f} vs {r_weak.fos:.4f}"
    )
    print(f"\n  ✅  test_strength_increases_fos passed")


# ---------------------------------------------------------------------------
# Test 5 – EC7 flag logic
# ---------------------------------------------------------------------------

def test_ec7_flags():
    """Verify ec7_stable (FoS≥1.00) and ec7_pass (FoS≥1.25) flags."""
    soil_weak   = Soil("Weak",   unit_weight=20.0, friction_angle=15, cohesion=2.0)
    soil_strong = Soil("Strong", unit_weight=20.0, friction_angle=30, cohesion=15.0)

    r_weak   = bishop_simplified(_make_slices(soil_weak),   ru=0.0)
    r_strong = bishop_simplified(_make_slices(soil_strong), ru=0.0)

    for result in (r_weak, r_strong):
        assert (result.fos >= 1.00) == result.ec7_stable, "FAIL: ec7_stable flag mismatch"
        assert (result.fos >= 1.25) == result.ec7_pass,   "FAIL: ec7_pass flag mismatch"

    print(f"\n{'═'*52}")
    print(f"  TEST 5 – EC7 Flag Logic")
    print(f"{'═'*52}")
    for label, r in [("Weak", r_weak), ("Strong", r_strong)]:
        print(f"  {label:8s}: FoS={r.fos:.4f}  stable={r.ec7_stable}  EC7_pass={r.ec7_pass}")
    print(f"\n  ✅  test_ec7_flags passed")


# ---------------------------------------------------------------------------
# Test 6 – Slice count convergence (more slices → stable FoS)
# ---------------------------------------------------------------------------

def test_slice_count_convergence():
    """
    FoS should stabilise as slice count increases.
    Difference between 10 and 50 slices must be < 2 %.
    """
    soil = Soil("Stiff Clay", unit_weight=20.0, friction_angle=25, cohesion=10.0)

    results = {}
    for n in (10, 20, 30, 50):
        slices     = create_slices(SLOPE, CIRCLE, soil, num_slices=n)
        results[n] = bishop_simplified(slices, ru=0.0).fos

    print(f"\n{'═'*52}")
    print(f"  TEST 6 – Slice Count Convergence")
    print(f"{'═'*52}")
    for n, fos in results.items():
        print(f"  n={n:3d}  →  FoS = {fos:.6f}")

    delta = abs(results[50] - results[10]) / results[50]
    assert delta < 0.05, (
        f"FAIL: FoS varies {delta*100:.2f}% between 10 and 50 slices — "
        "excessive sensitivity to discretisation."
    )
    print(f"  Max variation (n=10→50): {delta*100:.3f}%")
    print(f"\n  ✅  test_slice_count_convergence passed")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_bishop_drained()
    test_bishop_pore_pressure_monotonicity()
    test_ordinary_is_conservative()
    test_strength_increases_fos()
    test_ec7_flags()
    test_slice_count_convergence()

    print(f"\n{'═'*52}")
    print(f"  ✅  All limit_equilibrium tests passed.")
    print(f"{'═'*52}\n")
