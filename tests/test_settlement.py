"""
tests/test_settlement.py

Validates core/settlement.py against hand-calculated reference values.

Hand-calculated reference values:

  NC consolidation (Das §11.7):
    H=3m, Cc=0.35, e0=1.0, sigma_v0=50 kPa, delta_sigma=20 kPa
    s_c = (0.35*3)/(1+1.0) * log10(70/50) = 0.525 * 0.14613 = 0.076718 m = 76.7 mm

  OC consolidation, stays OC (sigma_vf=55 < sigma_pc=80):
    H=3m, Cs=0.05, e0=0.9, sigma_v0=40, delta_sigma=15, sigma_pc=80
    s_c = (0.05*3)/(1+0.9) * log10(55/40) = 0.07895 * 0.13827 = 0.010920 m = 10.9 mm

  OC consolidation, crosses yield (sigma_vf=90 > sigma_pc=70):
    H=3m, Cc=0.35, Cs=0.05, e0=1.0, sigma_v0=50, delta_sigma=40, sigma_pc=70
    s_c = 0.05*3/2*log10(70/50) + 0.35*3/2*log10(90/70)
        = 0.075*0.14613 + 0.525*0.10940
        = 0.010960 + 0.057435 = 0.068395 m = 68.4 mm

  Time to 90% consolidation (Das §11.8):
    U=0.90: Tv = 1.781 - 0.933*log10(100*(1-0.9)) = 1.781 - 0.933*log10(10) = 0.848
    Hdr=1.5m (double drainage), cv=0.5 m^2/yr
    t = 0.848*1.5^2/0.5 = 0.848*4.5 = 3.816 yr

  Time to 50% consolidation:
    Tv = pi/4 * 0.5^2 = 0.1963
    t = 0.1963*1.5^2/0.5 = 0.1963*4.5 = 0.8836 yr

Reference:
    Terzaghi, K. (1943). Theoretical Soil Mechanics.
    Das, B.M. (2019). Principles of Geotechnical Engineering, Chapters 7 and 11.
    Craig's Soil Mechanics, 9th ed., Chapter 7.

Run from DesignApp root:
    python -m pytest tests/  or  python tests/test_settlement.py
"""
import sys, os, math

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.settlement import (
    consolidation_settlement, immediate_settlement, time_to_consolidation,
    time_factor, S_LIM_ISOLATED,
)

TOL = 0.5   # percent tolerance


def _pct(a, b):
    return 100.0 * abs(a - b) / max(abs(b), 1e-9)


# ---------------------------------------------------------------------------
#  Test 1 -- NC clay consolidation: textbook value
# ---------------------------------------------------------------------------

def test_nc_clay_consolidation():
    """
    NC clay: H=3m, Cc=0.35, e0=1.0, sigma_v0=50 kPa, delta_sigma=20 kPa.
    s_c = (0.35*3/2.0) * log10(70/50) = 0.525 * 0.14613 = 76.7 mm.
    """
    res = consolidation_settlement(H=3.0, Cc=0.35, e0=1.0, sigma_v0=50.0, delta_sigma=20.0)

    print(f"\n{'='*60}")
    print(f"  TEST 1 -- NC Clay Consolidation (textbook)")
    print(f"{'='*60}")
    print(f"  s_c = {res.s_c*1000:.2f} mm   (expected 76.7 mm)")
    print(f"  is_nc = {res.is_nc}  s_c_oc = {res.s_c_oc*1000:.2f} mm")

    expected = 0.076718
    err = _pct(res.s_c, expected)
    assert err < TOL, f"FAIL: s_c={res.s_c*1000:.3f} mm, expected 76.7 mm (err {err:.2f}%)"
    assert res.is_nc is True,     "FAIL: should be NC"
    assert res.s_c_oc == 0.0,     "FAIL: OC portion should be 0"
    assert res.s_c_nc == res.s_c, "FAIL: NC portion should equal total"

    print(f"\n  PASS  test_nc_clay_consolidation")


# ---------------------------------------------------------------------------
#  Test 2 -- OC clay, stays overconsolidated
# ---------------------------------------------------------------------------

def test_oc_clay_stays_oc():
    """
    OC clay with sigma_vf < sigma_pc: only Cs branch active.
    H=3m, Cs=0.05, e0=0.9, sigma_v0=40, delta_sigma=15, sigma_pc=80.
    s_c = (0.05*3)/(1.9) * log10(55/40) = 0.07895 * 0.13827 = 10.9 mm.
    """
    res = consolidation_settlement(
        H=3.0, Cc=0.35, e0=0.9, sigma_v0=40.0, delta_sigma=15.0,
        Cs=0.05, sigma_pc=80.0
    )

    print(f"\n{'='*60}")
    print(f"  TEST 2 -- OC Clay (stays OC, Cs branch only)")
    print(f"{'='*60}")
    print(f"  s_c = {res.s_c*1000:.2f} mm   (expected 10.9 mm)")
    print(f"  sigma_vf={res.sigma_vf}  sigma_pc={res.sigma_pc}  is_nc={res.is_nc}")

    expected = 0.01092
    err = _pct(res.s_c, expected)
    assert err < TOL, f"FAIL: s_c={res.s_c*1000:.3f} mm, expected 10.9 mm (err {err:.2f}%)"
    assert res.is_nc is False, "FAIL: should be OC"
    assert res.s_c_nc == 0.0, "FAIL: NC portion should be 0 (OC clay stays OC)"

    print(f"\n  PASS  test_oc_clay_stays_oc")


# ---------------------------------------------------------------------------
#  Test 3 -- OC clay crosses preconsolidation pressure
# ---------------------------------------------------------------------------

def test_oc_clay_crosses_yield():
    """
    OC clay, sigma_vf > sigma_pc: both Cs and Cc branches.
    H=3m, Cc=0.35, Cs=0.05, e0=1.0, sigma_v0=50, delta_sigma=40, sigma_pc=70.
    s_c_oc = 0.05*3/2*log10(70/50) = 0.075*0.14613 = 10.96 mm
    s_c_nc = 0.35*3/2*log10(90/70) = 0.525*0.10940 = 57.43 mm
    s_c    = 68.39 mm
    """
    res = consolidation_settlement(
        H=3.0, Cc=0.35, e0=1.0, sigma_v0=50.0, delta_sigma=40.0,
        Cs=0.05, sigma_pc=70.0
    )

    print(f"\n{'='*60}")
    print(f"  TEST 3 -- OC Clay Crosses Preconsolidation Pressure")
    print(f"{'='*60}")
    print(f"  s_c_oc = {res.s_c_oc*1000:.2f} mm  (expected 10.96 mm)")
    print(f"  s_c_nc = {res.s_c_nc*1000:.2f} mm  (expected 57.43 mm)")
    print(f"  s_c    = {res.s_c*1000:.2f} mm  (expected 68.39 mm)")

    for label, expected, got in [
        ("s_c_oc", 0.01096, res.s_c_oc),
        ("s_c_nc", 0.05743, res.s_c_nc),
        ("s_c",    0.06839, res.s_c),
    ]:
        err = _pct(got, expected)
        print(f"  {label}: expected={expected*1000:.2f}mm  got={got*1000:.2f}mm  err={err:.3f}%")
        assert err < TOL, f"FAIL: {label} err={err:.2f}% > {TOL}%"

    assert res.is_nc is False, "FAIL: OC crossing yield should still report is_nc=False"
    assert res.s_c_oc > 0 and res.s_c_nc > 0, "FAIL: both branches should contribute"

    print(f"\n  PASS  test_oc_clay_crosses_yield")


# ---------------------------------------------------------------------------
#  Test 4 -- Terzaghi time factor: known values
# ---------------------------------------------------------------------------

def test_time_factor_known_values():
    """
    Standard Terzaghi time factor values (Das Table 11.8):
        U=0.10: Tv = pi/4*0.01 = 0.00785
        U=0.50: Tv = pi/4*0.25 = 0.19635
        U=0.90: Tv = 1.781-0.933*log10(10) = 1.781-0.933 = 0.848
        U=0.95: Tv = 1.781-0.933*log10(5) = 1.781-0.651 = 1.130 (approx.)
    """
    cases = [
        (0.10, (math.pi/4)*0.01),
        (0.50, (math.pi/4)*0.25),
        (0.90, 0.848),
    ]
    print(f"\n{'='*60}")
    print(f"  TEST 4 -- Terzaghi Time Factor Tv(U)")
    print(f"{'='*60}")
    for U, expected in cases:
        got = time_factor(U)
        err = _pct(got, expected)
        print(f"  U={U:.2f}: Tv expected={expected:.5f}  got={got:.5f}  err={err:.3f}%")
        assert err < 0.2, f"FAIL: Tv(U={U}) err={err:.3f}%"

    print(f"\n  PASS  test_time_factor_known_values")


# ---------------------------------------------------------------------------
#  Test 5 -- Time to 90% consolidation: textbook
# ---------------------------------------------------------------------------

def test_time_to_90pct_consolidation():
    """
    Tv(0.90) = 0.848, Hdr=1.5m (double drainage), cv=0.5 m^2/yr.
    t = 0.848*1.5^2/0.5 = 3.816 yr.
    """
    res = time_to_consolidation(U=0.90, H_dr=1.5, cv=0.5)

    print(f"\n{'='*60}")
    print(f"  TEST 5 -- Time to 90% Consolidation (textbook)")
    print(f"{'='*60}")
    print(f"  Tv={res.Tv:.4f}  t={res.t:.3f} yr  (expected Tv=0.848, t=3.816 yr)")

    assert _pct(res.Tv, 0.848) < 0.2, f"FAIL: Tv={res.Tv:.4f}"
    assert _pct(res.t,  3.816) < 0.5, f"FAIL: t={res.t:.3f} yr"

    print(f"\n  PASS  test_time_to_90pct_consolidation")


# ---------------------------------------------------------------------------
#  Test 6 -- Time to 50% consolidation
# ---------------------------------------------------------------------------

def test_time_to_50pct_consolidation():
    """
    Tv(0.50) = pi/4*0.25 = 0.19635, Hdr=1.5m, cv=0.5.
    t = 0.19635*1.5^2/0.5 = 0.884 yr.
    """
    Tv_exp = (math.pi / 4) * 0.25
    t_exp  = Tv_exp * 1.5**2 / 0.5
    res    = time_to_consolidation(U=0.50, H_dr=1.5, cv=0.5)

    print(f"\n{'='*60}")
    print(f"  TEST 6 -- Time to 50% Consolidation")
    print(f"{'='*60}")
    print(f"  Tv={res.Tv:.5f}  t={res.t:.4f} yr  expected Tv={Tv_exp:.5f}, t={t_exp:.4f} yr")

    assert _pct(res.Tv, Tv_exp) < 0.01, "FAIL: Tv(50%)"
    assert _pct(res.t,  t_exp)  < 0.01, "FAIL: t(50%)"

    print(f"\n  PASS  test_time_to_50pct_consolidation")


# ---------------------------------------------------------------------------
#  Test 7 -- Monotonicity: larger Cc -> larger settlement
# ---------------------------------------------------------------------------

def test_monotonicity_cc_increases_settlement():
    """Higher Cc must give larger consolidation settlement (NC clay)."""
    base = dict(H=3.0, e0=1.0, sigma_v0=50.0, delta_sigma=20.0)
    r_low  = consolidation_settlement(Cc=0.20, **base)
    r_high = consolidation_settlement(Cc=0.50, **base)

    print(f"\n{'='*60}")
    print(f"  TEST 7 -- Monotonicity: Cc increases settlement")
    print(f"{'='*60}")
    print(f"  Cc=0.20: s_c={r_low.s_c*1000:.1f} mm")
    print(f"  Cc=0.50: s_c={r_high.s_c*1000:.1f} mm")

    assert r_high.s_c > r_low.s_c, "FAIL: higher Cc should give larger s_c"
    print(f"\n  PASS  test_monotonicity_cc_increases_settlement")


# ---------------------------------------------------------------------------
#  Test 8 -- Immediate settlement formula
# ---------------------------------------------------------------------------

def test_immediate_settlement_formula():
    """
    s_i = q_net * B * (1-nu^2) / E_s * I_s * rigid_factor
    q=100 kPa, B=1.5m, E_s=20000 kPa, nu=0.3, I_s=0.82, rigid=True
    s_i = 100*1.5*(1-0.09)/20000 * 0.82 * 0.8
        = 100*1.5*0.91/20000 * 0.82 * 0.8
        = 0.006825 * 0.82 * 0.8
        = 0.004477 m = 4.48 mm
    """
    res = immediate_settlement(q_net=100.0, B=1.5, E_s=20000.0, nu=0.3, I_s=0.82, rigid=True)

    expected = 100.0 * 1.5 * (1 - 0.3**2) / 20000.0 * 0.82 * 0.8
    print(f"\n{'='*60}")
    print(f"  TEST 8 -- Immediate Settlement (elastic)")
    print(f"{'='*60}")
    print(f"  s_i = {res.s_i*1000:.3f} mm  expected={expected*1000:.3f} mm")

    err = _pct(res.s_i, expected)
    assert err < 0.01, f"FAIL: s_i={res.s_i*1000:.3f} mm, expected {expected*1000:.3f} mm"
    assert res.rigid_factor == 0.8, "FAIL: rigid_factor should be 0.8"

    print(f"\n  PASS  test_immediate_settlement_formula")


# ---------------------------------------------------------------------------
#  Test 9 -- Zero loading gives zero settlement
# ---------------------------------------------------------------------------

def test_zero_load_zero_settlement():
    """delta_sigma=0 must produce zero settlement."""
    res = consolidation_settlement(H=3.0, Cc=0.35, e0=1.0, sigma_v0=50.0, delta_sigma=0.0)
    assert res.s_c == 0.0, f"FAIL: s_c should be 0 for delta_sigma=0, got {res.s_c}"

    res_i = immediate_settlement(q_net=0.0, B=1.5, E_s=20000.0)
    assert res_i.s_i == 0.0, f"FAIL: s_i should be 0 for q=0, got {res_i.s_i}"

    print(f"\n  PASS  test_zero_load_zero_settlement")


# ---------------------------------------------------------------------------
#  Test 10 -- Edge cases raise ValueError
# ---------------------------------------------------------------------------

def test_edge_cases_raise():
    """Invalid inputs must raise ValueError."""
    print(f"\n{'='*60}")
    print(f"  TEST 10 -- Edge Cases")
    print(f"{'='*60}")

    try:
        consolidation_settlement(H=0.0, Cc=0.3, e0=1.0, sigma_v0=50.0, delta_sigma=10.0)
        assert False
    except ValueError as e:
        print(f"  PASS  H=0: {e}")

    try:
        consolidation_settlement(H=3.0, Cc=-0.1, e0=1.0, sigma_v0=50.0, delta_sigma=10.0)
        assert False
    except ValueError as e:
        print(f"  PASS  Cc<0: {e}")

    try:
        time_to_consolidation(U=1.0, H_dr=1.5, cv=0.5)
        assert False
    except ValueError as e:
        print(f"  PASS  U=1: {e}")

    try:
        immediate_settlement(q_net=100.0, B=1.5, E_s=-100.0)
        assert False
    except ValueError as e:
        print(f"  PASS  E_s<0: {e}")

    print(f"\n  PASS  test_edge_cases_raise")


# ---------------------------------------------------------------------------
#  Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_nc_clay_consolidation()
    test_oc_clay_stays_oc()
    test_oc_clay_crosses_yield()
    test_time_factor_known_values()
    test_time_to_90pct_consolidation()
    test_time_to_50pct_consolidation()
    test_monotonicity_cc_increases_settlement()
    test_immediate_settlement_formula()
    test_zero_load_zero_settlement()
    test_edge_cases_raise()

    print(f"\n{'='*60}")
    print(f"  ALL settlement tests passed.")
    print(f"{'='*60}\n")
