"""
tests/test_foundation_check.py

Validates core/foundation_check.py against hand-calculated DA1 reference values
and physical monotonicity expectations.

Hand-calculated reference values:
    Foundation : Square, B=L=2.0m, Df=1.5m
    Soil       : phi_k=30, c_k=0, gamma=18 kN/m3
    Loading    : Gk=400 kN (permanent), Qk=200 kN (variable)

    DA1-C1 (A1+M1+R1): gG=1.35, gQ=1.50, g_phi=1.00
        Vd    = 1.35*400 + 1.50*200 = 540 + 300 = 840 kN
        phi_d = 30 deg  (g_phi=1.00)
        Nq=18.37, Ngamma=20.07, sq=1.5, sgamma=0.7
        q = 18*1.5 = 27 kPa
        qu = 27*18.37*1.5 + 0.5*18*2.0*20.07*0.7 = 745.0 + 126.4 = 871.4 kPa
        Rd = 871.4 * 4.0 = 3485.6 kN
        eta_C1 = 840 / 3485.6 = 0.241  PASS

    DA1-C2 (A2+M2+R1): gG=1.00, gQ=1.30, g_phi=1.25
        Vd    = 1.00*400 + 1.30*200 = 660 kN
        phi_d = arctan(tan30/1.25) = 24.79 deg
        Nq ~ 10.53, sq ~ 1.419, qu ~ 515 kPa
        Rd ~ 2060 kN, eta_C2 ~ 0.320  PASS
        C2 governs (higher eta).  Overall PASS.

    Failing case: B=L=1.0m, same loads
        Rd_C1 ~ 400 kN < Vd=840 kN -> FAIL

Reference:
    Eurocode 7 -- EN 1997-1:2004, Section 6, Tables A.3/A.4/A.5.
    Craig's Soil Mechanics, 9th ed., Chapter 8.

Run from DesignApp root:
    python -m pytest tests/  or  python tests/test_foundation_check.py
"""
import sys, os, math

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from models.soil         import Soil
from models.foundation   import Foundation
from core.settlement     import consolidation_settlement, immediate_settlement
from core.foundation_check import (
    check_foundation_da1, FoundationCheckResult, BearingCombResult,
)


TOL = 2.0   # percent tolerance (2%) -- C2 involves arctan factoring


def _pct(a, b):
    return 100.0 * abs(a - b) / max(abs(b), 1e-9)


# ---------------------------------------------------------------------------
#  Shared fixtures
# ---------------------------------------------------------------------------

SOIL_SAND  = Soil("Dense Sand", unit_weight=18.0, friction_angle=30, cohesion=0.0)
SOIL_WEAK  = Soil("Loose Sand", unit_weight=17.0, friction_angle=22, cohesion=0.0)
SOIL_CLAY  = Soil("Stiff Clay", unit_weight=19.0, friction_angle=25, cohesion=15.0)

FOUND_2M   = Foundation.square(B=2.0, Df=1.5)   # adequate
FOUND_1M   = Foundation.square(B=1.0, Df=1.5)   # undersized (should fail)
FOUND_STRIP = Foundation.strip(B=1.5, Df=1.0)

GK = 400.0   # kN (permanent)
QK = 200.0   # kN (variable)


# ---------------------------------------------------------------------------
#  Test 1 -- Smoke test: fully populated result
# ---------------------------------------------------------------------------

def test_smoke_test():
    """check_foundation_da1 must return a fully populated FoundationCheckResult."""
    res = check_foundation_da1(FOUND_2M, SOIL_SAND, Gk=GK, Qk=QK)

    print(f"\n{'='*70}")
    print(f"  TEST 1 -- Smoke Test")
    print(f"{'='*70}")
    print(res.summary())

    assert isinstance(res, FoundationCheckResult)
    assert isinstance(res.comb1, BearingCombResult)
    assert isinstance(res.comb2, BearingCombResult)
    assert res.comb1.label == "DA1-C1"
    assert res.comb2.label == "DA1-C2"
    assert res.governing in (res.comb1, res.comb2)
    assert res.comb1.Vd > 0
    assert res.comb2.Rd > 0
    assert res.comb1.utilisation > 0

    print(f"\n  PASS  test_smoke_test")


# ---------------------------------------------------------------------------
#  Test 2 -- Textbook reference values: Vd, Rd, utilisation ±2%
# ---------------------------------------------------------------------------

def test_textbook_reference_values():
    """
    Validates C1 and C2 Vd, Rd, utilisation against hand-calculated values.
    See module docstring for full working.
    Tolerance: +-2% (C2 involves arctan factoring of phi).
    """
    res = check_foundation_da1(FOUND_2M, SOIL_SAND, Gk=GK, Qk=QK)
    c1, c2 = res.comb1, res.comb2

    print(f"\n{'='*70}")
    print(f"  TEST 2 -- Textbook Reference Validation")
    print(f"{'='*70}")
    print(f"  {'Quantity':<28}  {'Expected':>10}  {'Computed':>10}  {'Err%':>7}")
    print(f"  {'-'*60}")

    checks = [
        ("Vd C1 (kN)",        840.0,  c1.Vd,          0.1),
        ("Vd C2 (kN)",        660.0,  c2.Vd,          0.1),
        ("Rd C1 (kN)",       3993.7,  c1.Rd,          TOL),
        ("eta C1",             0.2103, c1.utilisation,  TOL),
        ("eta C2",             0.3239, c2.utilisation,  TOL),
    ]
    for label, expected, computed, tol in checks:
        err = _pct(computed, expected)
        ok  = "PASS" if err <= tol else "FAIL"
        print(f"  {ok}  {label:<28}  {expected:>10.3f}  {computed:>10.3f}  {err:>6.2f}%")
        assert err <= tol, f"FAIL: {label} err={err:.2f}%"

    assert res.governing.label == "DA1-C2", "FAIL: C2 must govern (higher utilisation)"
    assert res.uls_passes,    "FAIL: 2m square on dense sand should pass ULS"
    assert res.passes,        "FAIL: overall should pass"
    print(f"\n  PASS  test_textbook_reference_values")


# ---------------------------------------------------------------------------
#  Test 3 -- Undersized footing fails ULS
# ---------------------------------------------------------------------------

def test_undersized_footing_fails():
    """
    B=1m, same loads: Vd=840 kN >> Rd (too small footing) -> FAIL.
    """
    res = check_foundation_da1(FOUND_1M, SOIL_SAND, Gk=GK, Qk=QK)
    print(f"\n{'='*70}")
    print(f"  TEST 3 -- Undersized Footing (B=1m) Fails ULS")
    print(f"{'='*70}")
    print(res.summary())

    assert not res.uls_passes, "FAIL: 1m footing with 840 kN load should fail ULS"
    assert not res.passes, "FAIL: overall should fail"
    # C2 governs (factored strength reduces Rd dramatically), total check fails
    assert res.governing.utilisation > 1.0, f"FAIL: governing eta={res.governing.utilisation:.3f} should be > 1"

    print(f"\n  PASS  test_undersized_footing_fails")


# ---------------------------------------------------------------------------
#  Test 4 -- Monotonicity: larger footing -> lower utilisation
# ---------------------------------------------------------------------------

def test_larger_footing_reduces_utilisation():
    """Doubling footing area must halve utilisation ratio (approximately)."""
    r_small = check_foundation_da1(Foundation.square(B=1.5, Df=1.5), SOIL_SAND, Gk=GK, Qk=QK)
    r_large = check_foundation_da1(Foundation.square(B=3.0, Df=1.5), SOIL_SAND, Gk=GK, Qk=QK)

    print(f"\n{'='*70}")
    print(f"  TEST 4 -- Monotonicity: Larger Footing Reduces Utilisation")
    print(f"{'='*70}")
    print(f"  B=1.5m: eta_C1={r_small.comb1.utilisation:.3f}  eta_C2={r_small.comb2.utilisation:.3f}")
    print(f"  B=3.0m: eta_C1={r_large.comb1.utilisation:.3f}  eta_C2={r_large.comb2.utilisation:.3f}")

    assert r_large.comb1.utilisation < r_small.comb1.utilisation, "FAIL: C1 monotonicity"
    assert r_large.comb2.utilisation < r_small.comb2.utilisation, "FAIL: C2 monotonicity"
    print(f"\n  PASS  test_larger_footing_reduces_utilisation")


# ---------------------------------------------------------------------------
#  Test 5 -- Monotonicity: stronger soil -> lower utilisation
# ---------------------------------------------------------------------------

def test_stronger_soil_reduces_utilisation():
    """Stronger soil (higher phi) gives higher Rd -> lower utilisation ratio."""
    r_weak   = check_foundation_da1(FOUND_2M, SOIL_WEAK,  Gk=GK, Qk=QK)
    r_strong = check_foundation_da1(FOUND_2M, SOIL_SAND,  Gk=GK, Qk=QK)

    print(f"\n{'='*70}")
    print(f"  TEST 5 -- Stronger Soil Reduces Utilisation")
    print(f"{'='*70}")
    print(f"  Loose sand phi=22: eta_C1={r_weak.comb1.utilisation:.3f}  eta_C2={r_weak.comb2.utilisation:.3f}")
    print(f"  Dense sand phi=30: eta_C1={r_strong.comb1.utilisation:.3f}  eta_C2={r_strong.comb2.utilisation:.3f}")

    assert r_strong.comb1.utilisation < r_weak.comb1.utilisation, "FAIL: C1 stronger soil"
    assert r_strong.comb2.utilisation < r_weak.comb2.utilisation, "FAIL: C2 stronger soil"
    print(f"\n  PASS  test_stronger_soil_reduces_utilisation")


# ---------------------------------------------------------------------------
#  Test 6 -- EC7 pass/fail logic consistency
# ---------------------------------------------------------------------------

def test_ec7_pass_fail_logic():
    """overall .passes iff uls_passes (and sls_passes if checked)."""
    r_ok   = check_foundation_da1(FOUND_2M, SOIL_SAND, Gk=GK, Qk=QK)
    r_fail = check_foundation_da1(FOUND_1M, SOIL_SAND, Gk=GK, Qk=QK)

    print(f"\n{'='*70}")
    print(f"  TEST 6 -- EC7 Pass/Fail Logic Consistency")
    print(f"{'='*70}")

    for lbl, res in [("Adequate", r_ok), ("Undersized", r_fail)]:
        c1_ok = res.comb1.passes
        c2_ok = res.comb2.passes
        uls_expected = c1_ok and c2_ok
        assert res.uls_passes == uls_expected, f"FAIL [{lbl}]: uls_passes mismatch"
        assert res.passes     == uls_expected, f"FAIL [{lbl}]: passes mismatch (no SLS)"
        verdict = "PASS" if res.passes else "FAIL"
        print(f"  {lbl:12s}: C1={'PASS' if c1_ok else 'FAIL'}  C2={'PASS' if c2_ok else 'FAIL'}  Overall={verdict}")

    print(f"\n  PASS  test_ec7_pass_fail_logic")


# ---------------------------------------------------------------------------
#  Test 7 -- SLS settlement check: pass and fail cases
# ---------------------------------------------------------------------------

def test_sls_settlement_check():
    """
    With settlement provided, sls_passes must reflect s_total <= s_lim.
    Small s_total -> SLS PASS.  Large s_total -> SLS FAIL.
    """
    # Small settlement (5 mm): should pass s_lim=25 mm
    s_small = consolidation_settlement(H=2.0, Cc=0.10, e0=1.0, sigma_v0=60.0, delta_sigma=10.0)
    r_pass  = check_foundation_da1(FOUND_2M, SOIL_SAND, Gk=GK, Qk=QK, consolidation=s_small)

    # Large settlement (NC clay with large Cc): should exceed s_lim
    s_large = consolidation_settlement(H=5.0, Cc=0.60, e0=1.2, sigma_v0=30.0, delta_sigma=40.0)
    r_fail  = check_foundation_da1(FOUND_2M, SOIL_SAND, Gk=GK, Qk=QK, consolidation=s_large)

    print(f"\n{'='*70}")
    print(f"  TEST 7 -- SLS Settlement Check")
    print(f"{'='*70}")
    print(f"  Small s_c={s_small.s_c*1000:.1f} mm: sls_passes={r_pass.sls_passes}")
    print(f"  Large s_c={s_large.s_c*1000:.1f} mm: sls_passes={r_fail.sls_passes}")

    assert r_pass.sls_passes is True,  f"FAIL: s_c={s_small.s_c*1000:.1f}mm should pass SLS"
    assert r_fail.sls_passes is False, f"FAIL: s_c={s_large.s_c*1000:.1f}mm should fail SLS"
    assert r_fail.s_total is not None, "FAIL: s_total should be set"
    assert r_fail.s_total == r_fail.settlement.s_c, "FAIL: s_total should equal s_c when no s_i"

    print(f"\n  PASS  test_sls_settlement_check")


# ---------------------------------------------------------------------------
#  Test 8 -- C2 governs for GEO (weaker strength -> higher utilisation)
# ---------------------------------------------------------------------------

def test_c2_governs_geo():
    """
    DA1-C2 (M2 factors) reduces phi -> lower Rd, yet Vd also drops (gG=1.00).
    For typical GEO (sand, no surcharge), C2 should govern (higher utilisation).
    """
    res = check_foundation_da1(FOUND_2M, SOIL_SAND, Gk=GK, Qk=0.0)

    print(f"\n{'='*70}")
    print(f"  TEST 8 -- C2 Governs GEO (No Variable Load)")
    print(f"{'='*70}")
    print(f"  C1: Vd={res.comb1.Vd:.1f}  Rd={res.comb1.Rd:.1f}  eta={res.comb1.utilisation:.3f}")
    print(f"  C2: Vd={res.comb2.Vd:.1f}  Rd={res.comb2.Rd:.1f}  eta={res.comb2.utilisation:.3f}")
    print(f"  Governing: {res.governing.label}")

    assert res.governing.label == "DA1-C2", (
        f"FAIL: C2 should govern for GEO (permanent load only), "
        f"got {res.governing.label}"
    )
    print(f"\n  PASS  test_c2_governs_geo")


# ---------------------------------------------------------------------------
#  Test 9 -- Strip footing integration (per unit run)
# ---------------------------------------------------------------------------

def test_strip_footing_integration():
    """Strip footing (L=None) returns forces per unit run consistently."""
    res = check_foundation_da1(FOUND_STRIP, SOIL_SAND, Gk=100.0, Qk=50.0)

    print(f"\n{'='*70}")
    print(f"  TEST 9 -- Strip Footing Integration (per unit run)")
    print(f"{'='*70}")
    print(res.summary())

    assert res.comb1.Vd > 0
    assert res.comb1.Rd > 0
    # Vd C1 = 1.35*100 + 1.5*50 = 135 + 75 = 210 kN/m
    assert abs(res.comb1.Vd - 210.0) < 0.01, f"FAIL: Vd_C1={res.comb1.Vd:.2f} kN/m"

    print(f"\n  PASS  test_strip_footing_integration")


# ---------------------------------------------------------------------------
#  Test 10 -- Edge cases raise ValueError
# ---------------------------------------------------------------------------

def test_edge_cases_raise():
    """Invalid inputs must raise ValueError."""
    print(f"\n{'='*70}")
    print(f"  TEST 10 -- Edge Cases")
    print(f"{'='*70}")

    try:
        check_foundation_da1(FOUND_2M, SOIL_SAND, Gk=0.0)
        assert False
    except ValueError as e:
        print(f"  PASS  Gk=0: {e}")

    try:
        check_foundation_da1(FOUND_2M, SOIL_SAND, Gk=100.0, Qk=-10.0)
        assert False
    except ValueError as e:
        print(f"  PASS  Qk<0: {e}")

    print(f"\n  PASS  test_edge_cases_raise")


# ---------------------------------------------------------------------------
#  Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_smoke_test()
    test_textbook_reference_values()
    test_undersized_footing_fails()
    test_larger_footing_reduces_utilisation()
    test_stronger_soil_reduces_utilisation()
    test_ec7_pass_fail_logic()
    test_sls_settlement_check()
    test_c2_governs_geo()
    test_strip_footing_integration()
    test_edge_cases_raise()

    print(f"\n{'='*70}")
    print(f"  ALL foundation_check tests passed.")
    print(f"{'='*70}\n")
