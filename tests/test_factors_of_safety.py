"""
tests/test_factors_of_safety.py

Validates core/factors_of_safety.py against:
    – Partial factor arithmetic (hand-checkable)
    – Monotonicity:  C2 FoS_d ≤ C1 FoS_d  (M2 always reduces strength)
    – Monotonicity:  higher rᵤ → lower FoS_d for both combinations
    – Monotonicity:  stronger soil → higher FoS_d for both combinations
    – EC7 pass/fail logic
    – Edge cases: invalid parameters raise ValueError

Run from the DesignApp root:
    python -m pytest tests/
  or:
    python tests/test_factors_of_safety.py
"""
import sys, os, math

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from models.soil              import Soil
from models.geometry          import SlopeGeometry
from core.factors_of_safety   import (
    verify_slope_da1, VerificationResult, CombinationResult,
    _factored_soil,
    M1_GAMMA_PHI, M1_GAMMA_C,
    M2_GAMMA_PHI, M2_GAMMA_C,
    FOS_D_LIMIT,
)


# ─────────────────────────────────────────────────────────────────────────────
#  Shared fixtures
# ─────────────────────────────────────────────────────────────────────────────

SLOPE      = SlopeGeometry([(0, 10), (10, 10), (20, 0), (30, 0)])
SOIL_MED   = Soil("Medium Clay", unit_weight=20.0, friction_angle=25, cohesion=10.0)
SOIL_WEAK  = Soil("Weak Clay",   unit_weight=18.0, friction_angle=15, cohesion=3.0)
SOIL_STRONG= Soil("Dense Sand",  unit_weight=20.0, friction_angle=32, cohesion=18.0)

# Coarse grid — fast enough for a test suite
GRID = dict(n_cx=8, n_cy=8, n_r=4, num_slices=15)


# ─────────────────────────────────────────────────────────────────────────────
#  Test 1 – Partial factor arithmetic
# ─────────────────────────────────────────────────────────────────────────────

def test_factored_soil_arithmetic():
    """
    _factored_soil() must compute φ'_d and c'_d exactly per EC7 §2.4.6.2.

    φ'_d = arctan( tan(φ'_k) / γ_φ )
    c'_d = c'_k / γ_c
    γ    is unchanged (γ_γ = 1.0)

    Hand-check with φ'_k=25°, c'_k=10 kPa, γ_φ=γ_c=1.25:
        tan(25°)   = 0.46631
        tan(φ'_d)  = 0.46631 / 1.25 = 0.37305
        φ'_d       = arctan(0.37305) = 20.458°
        c'_d       = 10.0 / 1.25    = 8.0 kPa
    """
    char = Soil("Test", unit_weight=19.0, friction_angle=25.0, cohesion=10.0)
    d    = _factored_soil(char, gamma_phi=1.25, gamma_c=1.25)

    expected_phi_d = math.degrees(math.atan(math.tan(math.radians(25.0)) / 1.25))
    expected_c_d   = 10.0 / 1.25

    print(f"\n{'═'*60}")
    print(f"  TEST 1 – Partial Factor Arithmetic")
    print(f"{'═'*60}")
    print(f"  φ'_k=25°  c'_k=10 kPa  γ_φ=γ_c=1.25")
    print(f"  Expected  φ'_d = {expected_phi_d:.4f}°   c'_d = {expected_c_d:.4f} kPa")
    print(f"  Computed  φ'_d = {d.phi_k:.4f}°   c'_d = {d.c_k:.4f} kPa")
    print(f"  γ unchanged    = {d.gamma:.1f} kN/m³  (expected {char.gamma:.1f})")

    assert abs(d.phi_k  - expected_phi_d) < 1e-8, \
        f"FAIL: φ'_d mismatch: {d.phi_k:.6f} vs {expected_phi_d:.6f}"
    assert abs(d.c_k    - expected_c_d)   < 1e-10, \
        f"FAIL: c'_d mismatch: {d.c_k:.6f} vs {expected_c_d:.6f}"
    assert d.gamma == char.gamma, \
        f"FAIL: unit weight must not change: {d.gamma} vs {char.gamma}"

    # M1 factors leave parameters unchanged
    d_m1 = _factored_soil(char, M1_GAMMA_PHI, M1_GAMMA_C)
    assert abs(d_m1.phi_k - char.phi_k) < 1e-8, "FAIL: M1 must not change φ'_k"
    assert abs(d_m1.c_k   - char.c_k)  < 1e-10, "FAIL: M1 must not change c'_k"

    print(f"  M1 identity check: φ'_d = φ'_k  ✅   c'_d = c'_k  ✅")
    print(f"\n  ✅  test_factored_soil_arithmetic passed")


# ─────────────────────────────────────────────────────────────────────────────
#  Test 2 – Smoke test: VerificationResult is fully populated
# ─────────────────────────────────────────────────────────────────────────────

def test_verify_returns_valid_result():
    """verify_slope_da1 must return a fully populated VerificationResult."""
    result = verify_slope_da1(SLOPE, SOIL_MED, ru=0.0, **GRID)

    print(f"\n{'═'*60}")
    print(f"  TEST 2 – Smoke Test")
    print(f"{'═'*60}")
    print(result.summary())

    assert isinstance(result, VerificationResult), "FAIL: wrong return type"
    assert isinstance(result.comb1, CombinationResult), "FAIL: comb1 missing"
    assert isinstance(result.comb2, CombinationResult), "FAIL: comb2 missing"
    assert result.comb1.label == "DA1-C1",  "FAIL: comb1 label wrong"
    assert result.comb2.label == "DA1-C2",  "FAIL: comb2 label wrong"
    assert math.isfinite(result.fos_char),  "FAIL: fos_char not finite"
    assert math.isfinite(result.fos_d_min), "FAIL: fos_d_min not finite"
    assert result.fos_char > 0,             "FAIL: fos_char must be positive"
    assert result.fos_d_min > 0,            "FAIL: fos_d_min must be positive"
    assert result.governing in (result.comb1, result.comb2), \
        "FAIL: governing must be one of the two combinations"

    print(f"\n  ✅  test_verify_returns_valid_result passed")


# ─────────────────────────────────────────────────────────────────────────────
#  Test 3 – Monotonicity: C2 FoS_d ≤ C1 FoS_d
# ─────────────────────────────────────────────────────────────────────────────

def test_comb2_fos_le_comb1_fos():
    """
    DA1 Comb 2 applies M2 factors (γ_φ=γ_c=1.25), reducing soil strength.
    Therefore FoS_d(C2) must always be ≤ FoS_d(C1).
    This is the fundamental EC7 property: Comb 2 governs GEO checks.
    """
    result = verify_slope_da1(SLOPE, SOIL_MED, ru=0.0, **GRID)

    print(f"\n{'═'*60}")
    print(f"  TEST 3 – Monotonicity: Comb2 FoS ≤ Comb1 FoS")
    print(f"{'═'*60}")
    print(f"  FoS_d (C1, γ_M=1.00) = {result.comb1.fos_d:.4f}")
    print(f"  FoS_d (C2, γ_M=1.25) = {result.comb2.fos_d:.4f}")

    assert result.comb2.fos_d <= result.comb1.fos_d + 1e-4, (
        f"FAIL: C2 FoS_d ({result.comb2.fos_d:.4f}) must be ≤ "
        f"C1 FoS_d ({result.comb1.fos_d:.4f}). "
        "M2 factors must always reduce the FoS."
    )
    assert result.governing.label == "DA1-C2", \
        "FAIL: Comb 2 should govern (lower FoS) for this typical GEO case."

    print(f"\n  ✅  test_comb2_fos_le_comb1_fos passed")


# ─────────────────────────────────────────────────────────────────────────────
#  Test 4 – Monotonicity: pore pressure reduces both FoS_d values
# ─────────────────────────────────────────────────────────────────────────────

def test_pore_pressure_reduces_fos_d():
    """FoS_d for BOTH combinations must decrease as rᵤ increases."""
    r0  = verify_slope_da1(SLOPE, SOIL_MED, ru=0.0, **GRID)
    r03 = verify_slope_da1(SLOPE, SOIL_MED, ru=0.3, **GRID)

    print(f"\n{'═'*60}")
    print(f"  TEST 4 – Pore Pressure Monotonicity")
    print(f"{'═'*60}")
    print(f"  rᵤ=0.0:  C1={r0.comb1.fos_d:.4f}   C2={r0.comb2.fos_d:.4f}")
    print(f"  rᵤ=0.3:  C1={r03.comb1.fos_d:.4f}   C2={r03.comb2.fos_d:.4f}")

    assert r03.comb1.fos_d < r0.comb1.fos_d, (
        f"FAIL: C1 FoS_d should decrease with rᵤ. "
        f"Got {r03.comb1.fos_d:.4f} vs {r0.comb1.fos_d:.4f}"
    )
    assert r03.comb2.fos_d < r0.comb2.fos_d, (
        f"FAIL: C2 FoS_d should decrease with rᵤ. "
        f"Got {r03.comb2.fos_d:.4f} vs {r0.comb2.fos_d:.4f}"
    )
    print(f"\n  ✅  test_pore_pressure_reduces_fos_d passed")


# ─────────────────────────────────────────────────────────────────────────────
#  Test 5 – Monotonicity: stronger soil → higher FoS_d
# ─────────────────────────────────────────────────────────────────────────────

def test_stronger_soil_increases_fos_d():
    """Stronger soil must give higher FoS_d in both combinations."""
    r_weak   = verify_slope_da1(SLOPE, SOIL_WEAK,   ru=0.0, **GRID)
    r_strong = verify_slope_da1(SLOPE, SOIL_STRONG, ru=0.0, **GRID)

    print(f"\n{'═'*60}")
    print(f"  TEST 5 – Soil Strength Monotonicity")
    print(f"{'═'*60}")
    print(f"  Weak   soil:  C1={r_weak.comb1.fos_d:.4f}   C2={r_weak.comb2.fos_d:.4f}")
    print(f"  Strong soil:  C1={r_strong.comb1.fos_d:.4f}   C2={r_strong.comb2.fos_d:.4f}")

    assert r_strong.comb1.fos_d > r_weak.comb1.fos_d, \
        "FAIL: C1 FoS_d must be higher for stronger soil."
    assert r_strong.comb2.fos_d > r_weak.comb2.fos_d, \
        "FAIL: C2 FoS_d must be higher for stronger soil."
    print(f"\n  ✅  test_stronger_soil_increases_fos_d passed")


# ─────────────────────────────────────────────────────────────────────────────
#  Test 6 – EC7 pass / fail logic
# ─────────────────────────────────────────────────────────────────────────────

def test_ec7_pass_fail_logic():
    """
    overall .passes must be True iff BOTH combinations individually pass.
    Individual pass is FoS_d ≥ 1.0.
    """
    r_weak   = verify_slope_da1(SLOPE, SOIL_WEAK,   ru=0.0, **GRID)
    r_strong = verify_slope_da1(SLOPE, SOIL_STRONG, ru=0.0, **GRID)

    print(f"\n{'═'*60}")
    print(f"  TEST 6 – EC7 Pass / Fail Logic")
    print(f"{'═'*60}")

    for label, res in [("Weak", r_weak), ("Strong", r_strong)]:
        c1_should_pass = res.comb1.fos_d >= FOS_D_LIMIT
        c2_should_pass = res.comb2.fos_d >= FOS_D_LIMIT
        overall_should_pass = c1_should_pass and c2_should_pass

        assert res.comb1.passes == c1_should_pass, \
            f"FAIL [{label}]: comb1.passes mismatch at FoS_d={res.comb1.fos_d:.4f}"
        assert res.comb2.passes == c2_should_pass, \
            f"FAIL [{label}]: comb2.passes mismatch at FoS_d={res.comb2.fos_d:.4f}"
        assert res.passes == overall_should_pass, \
            f"FAIL [{label}]: overall .passes mismatch"

        verdict = '✅ PASS' if res.passes else '❌ FAIL'
        print(f"  {label:8s}:  C1={res.comb1.fos_d:.4f}({'✅' if res.comb1.passes else '❌'})  "
              f"C2={res.comb2.fos_d:.4f}({'✅' if res.comb2.passes else '❌'})  "
              f"Overall={verdict}")

    print(f"\n  ✅  test_ec7_pass_fail_logic passed")


# ─────────────────────────────────────────────────────────────────────────────
#  Test 7 – Characteristic FoS == C1 FoS_d (M1 is identity)
# ─────────────────────────────────────────────────────────────────────────────

def test_fos_char_equals_c1_fos_d():
    """
    Because M1 factors are 1.0, the design soil for C1 is identical to the
    characteristic soil.  Therefore fos_char must equal comb1.fos_d exactly.
    """
    result = verify_slope_da1(SLOPE, SOIL_MED, ru=0.0, **GRID)

    print(f"\n{'═'*60}")
    print(f"  TEST 7 – fos_char == C1 FoS_d  (M1 is identity)")
    print(f"{'═'*60}")
    print(f"  fos_char  = {result.fos_char:.6f}")
    print(f"  C1 FoS_d  = {result.comb1.fos_d:.6f}")
    print(f"  Δ         = {abs(result.fos_char - result.comb1.fos_d):.2e}")

    assert abs(result.fos_char - result.comb1.fos_d) < 1e-9, (
        f"FAIL: fos_char ({result.fos_char:.6f}) must equal "
        f"comb1.fos_d ({result.comb1.fos_d:.6f}) when γ_M=1.0."
    )
    print(f"\n  ✅  test_fos_char_equals_c1_fos_d passed")


# ─────────────────────────────────────────────────────────────────────────────
#  Test 8 – Invalid parameters raise ValueError
# ─────────────────────────────────────────────────────────────────────────────

def test_invalid_parameters_raise():
    """Bad inputs must raise ValueError with a clear message."""
    print(f"\n{'═'*60}")
    print(f"  TEST 8 – Edge Cases / Invalid Parameters")
    print(f"{'═'*60}")

    # ru out of range
    try:
        verify_slope_da1(SLOPE, SOIL_MED, ru=1.0, **GRID)
        assert False, "FAIL: should raise ValueError for ru=1.0"
    except ValueError as e:
        print(f"  ✅ ru=1.0 raised: {e}")

    # gamma_phi < 1.0 in _factored_soil
    try:
        _factored_soil(SOIL_MED, gamma_phi=0.8, gamma_c=1.0)
        assert False, "FAIL: should raise ValueError for gamma_phi=0.8"
    except ValueError as e:
        print(f"  ✅ gamma_phi<1.0 raised: {e}")

    # gamma_c < 1.0 in _factored_soil
    try:
        _factored_soil(SOIL_MED, gamma_phi=1.0, gamma_c=0.5)
        assert False, "FAIL: should raise ValueError for gamma_c=0.5"
    except ValueError as e:
        print(f"  ✅ gamma_c<1.0 raised: {e}")

    print(f"\n  ✅  test_invalid_parameters_raise passed")


# ─────────────────────────────────────────────────────────────────────────────
#  Runner
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_factored_soil_arithmetic()
    test_verify_returns_valid_result()
    test_comb2_fos_le_comb1_fos()
    test_pore_pressure_reduces_fos_d()
    test_stronger_soil_increases_fos_d()
    test_ec7_pass_fail_logic()
    test_fos_char_equals_c1_fos_d()
    test_invalid_parameters_raise()

    print(f"\n{'═'*60}")
    print(f"  ✅  All factors_of_safety tests passed.")
    print(f"{'═'*60}\n")
