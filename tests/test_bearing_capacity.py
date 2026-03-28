"""
tests/test_bearing_capacity.py

Validates core/bearing_capacity.py against EC7 Annex D hand-calculated
reference values and physical monotonicity expectations.

Hand-calculated reference values (see individual test docstrings):
    phi=30 factors : Nq=18.37, Nc=30.09, Ngamma=20.07  (EC7 Annex D.3)
    phi=25 factors : Nq=10.66, Nc=20.72, Ngamma=9.01
    phi=0  factors : Nq=1.00,  Nc=5.14,  Ngamma=0.00   (Prandtl)

    Strip c=0, phi=30, B=1m, Df=1m, gamma=18:
        q_ult = 18*18.37 + 0.5*18*1*20.07 = 330.7 + 180.6 = 511.3 kPa

    Square c=0, phi=30, B=L=1.5m, Df=1m, gamma=18:
        sq=1.5, sgamma=0.7
        q_ult = 18*18.37*1.5 + 0.5*18*1.5*20.07*0.7 = 495.9 + 190.0 = 685.9 kPa

    Undrained phi=0, cu=50, strip, Df=1m, gamma=18:
        q_ult = 50*5.14 + 18*1 = 257.0 + 18.0 = 275.0 kPa

    c-phi strip, phi=25, c=10, B=1.5m, Df=1.2m, gamma=18:
        q_ult = 10*20.72 + 21.6*10.66 + 0.5*18*1.5*9.01
              = 207.2 + 230.3 + 121.6 = 559.1 kPa

Reference:
    Eurocode 7 -- EN 1997-1:2004, Annex D.
    Craig's Soil Mechanics, 9th ed., Chapter 8.

Run from the DesignApp root:
    python -m pytest tests/  or  python tests/test_bearing_capacity.py
"""
import sys, os, math

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from models.foundation    import Foundation
from core.bearing_capacity import (
    bearing_factors_ec7, bearing_resistance_ec7,
    BearingFactors, BearingResult,
)

TOL = 0.5   # percent tolerance (0.5%) for textbook comparisons


def _pct(a, b):
    return 100.0 * abs(a - b) / max(abs(b), 1e-9)


# ---------------------------------------------------------------------------
#  Test 1 -- EC7 Annex D.3 bearing factors vs hand-calculated values
# ---------------------------------------------------------------------------

def test_bearing_factors_phi30():
    """
    EC7 Annex D.3 factors for phi=30deg:
        Nq = exp(pi*tan30)*tan^2(60) = 6.123*3.000 = 18.37
        Nc = (18.37-1)*cot30 = 17.37*1.732 = 30.09
        Ngamma = 2*(18.37-1)*tan30 = 2*17.37*0.5774 = 20.07
    Published Craig Table B.1: Nq=18.40, Nc=30.14, Ngamma=20.09 (agree within 0.2%)
    """
    bf = bearing_factors_ec7(30.0)
    print(f"\n{'='*60}")
    print(f"  TEST 1 -- Bearing factors phi=30 deg")
    print(f"{'='*60}")
    print(f"  {bf}")

    cases = [("Nq", 18.37, bf.Nq), ("Nc", 30.09, bf.Nc), ("Ngamma", 20.07, bf.Ngamma)]
    for label, expected, got in cases:
        err = _pct(got, expected)
        print(f"  {label}: expected={expected:.3f}  got={got:.3f}  err={err:.3f}%")
        assert err < TOL, f"FAIL: {label} err={err:.3f}% > {TOL}%"

    print(f"\n  PASS  test_bearing_factors_phi30")


def test_bearing_factors_phi25():
    """
    EC7 Annex D.3 factors for phi=25deg:
        Nq = exp(pi*tan25)*tan^2(57.5) = 4.324*2.465 = 10.66
        Nc = 9.66*cot25 = 9.66*2.145 = 20.72
        Ngamma = 2*9.66*0.4663 = 9.01
    """
    bf = bearing_factors_ec7(25.0)
    print(f"\n{'='*60}")
    print(f"  TEST 2 -- Bearing factors phi=25 deg")
    print(f"{'='*60}")
    print(f"  {bf}")

    cases = [("Nq", 10.66, bf.Nq), ("Nc", 20.72, bf.Nc), ("Ngamma", 9.01, bf.Ngamma)]
    for label, expected, got in cases:
        err = _pct(got, expected)
        print(f"  {label}: expected={expected:.3f}  got={got:.3f}  err={err:.3f}%")
        assert err < TOL, f"FAIL: {label} err={err:.3f}% > {TOL}%"

    print(f"\n  PASS  test_bearing_factors_phi25")


def test_bearing_factors_phi0():
    """
    Undrained (phi=0): Nq=1, Nc=pi+2=5.142, Ngamma=0 (Prandtl limit).
    """
    bf = bearing_factors_ec7(0.0)
    print(f"\n{'='*60}")
    print(f"  TEST 3 -- Bearing factors phi=0 (undrained, Prandtl limit)")
    print(f"{'='*60}")
    print(f"  {bf}")

    assert abs(bf.Nq - 1.0) < 1e-6,       f"FAIL: Nq={bf.Nq:.6f} != 1.0"
    assert abs(bf.Nc - (math.pi+2)) < 0.01, f"FAIL: Nc={bf.Nc:.4f} != pi+2={math.pi+2:.4f}"
    assert abs(bf.Ngamma) < 1e-9,          f"FAIL: Ngamma={bf.Ngamma} != 0"
    print(f"\n  PASS  test_bearing_factors_phi0")


# ---------------------------------------------------------------------------
#  Test 4 -- Strip footing, c=0, phi=30, textbook value
# ---------------------------------------------------------------------------

def test_strip_cohesionless_phi30():
    """
    Strip c=0, phi=30, B=1m, Df=1m, gamma=18.
    Hand: q_ult = 18*18.37 + 0.5*18*1*20.07 = 330.7 + 180.6 = 511.3 kPa
    Shape factors = 1.0 (strip).
    """
    f  = Foundation.strip(B=1.0, Df=1.0)
    br = bearing_resistance_ec7(f, phi_d=30.0, c_d=0.0, gamma_soil=18.0)

    print(f"\n{'='*60}")
    print(f"  TEST 4 -- Strip footing, c=0, phi=30, B=1m")
    print(f"{'='*60}")
    print(br.summary())

    expected = 511.3
    err = _pct(br.q_ult, expected)
    print(f"\n  q_ult expected={expected:.1f}  got={br.q_ult:.2f}  err={err:.3f}%")
    assert err < TOL, f"FAIL: q_ult err={err:.2f}% > {TOL}%"

    # Shape factors must all be 1.0 for strip
    assert abs(br.sc - 1.0) < 1e-9, f"FAIL: sc={br.sc} != 1.0 for strip"
    assert abs(br.sq - 1.0) < 1e-9, f"FAIL: sq={br.sq} != 1.0 for strip"
    assert abs(br.sg - 1.0) < 1e-9, f"FAIL: sg={br.sg} != 1.0 for strip"

    print(f"\n  PASS  test_strip_cohesionless_phi30")


# ---------------------------------------------------------------------------
#  Test 5 -- Square footing, c=0, phi=30
# ---------------------------------------------------------------------------

def test_square_cohesionless_phi30():
    """
    Square c=0, phi=30, B=L=1.5m, Df=1m, gamma=18.
    Shape: sq=1+sin30=1.5, sgamma=1-0.3=0.7
    Hand: q_ult = 18*18.37*1.5 + 0.5*18*1.5*20.07*0.7 = 495.9+190.0 = 685.9 kPa
    """
    f  = Foundation.square(B=1.5, Df=1.0)
    br = bearing_resistance_ec7(f, phi_d=30.0, c_d=0.0, gamma_soil=18.0)

    print(f"\n{'='*60}")
    print(f"  TEST 5 -- Square footing, c=0, phi=30, B=L=1.5m")
    print(f"{'='*60}")
    print(br.summary())

    expected = 685.9
    err = _pct(br.q_ult, expected)
    print(f"\n  q_ult expected={expected:.1f}  got={br.q_ult:.2f}  err={err:.3f}%")
    assert err < TOL, f"FAIL: q_ult err={err:.2f}% > {TOL}%"

    # Shape factors for square
    assert abs(br.sq - 1.5) < 0.001, f"FAIL: sq={br.sq:.4f} != 1.5"
    assert abs(br.sg - 0.7) < 0.001, f"FAIL: sg={br.sg:.4f} != 0.7"

    print(f"\n  PASS  test_square_cohesionless_phi30")


# ---------------------------------------------------------------------------
#  Test 6 -- Undrained strip footing (phi=0, cu=50 kPa)
# ---------------------------------------------------------------------------

def test_strip_undrained():
    """
    phi=0 (undrained), cu=50 kPa, strip, Df=1m, gamma=18.
    q_ult = 50*5.14 + 18*1 = 257.0 + 18.0 = 275.0 kPa
    """
    f  = Foundation.strip(B=1.5, Df=1.0)
    br = bearing_resistance_ec7(f, phi_d=0.0, c_d=50.0, gamma_soil=18.0)

    print(f"\n{'='*60}")
    print(f"  TEST 6 -- Strip undrained, phi=0, cu=50 kPa")
    print(f"{'='*60}")
    print(br.summary())

    expected = 275.0
    err = _pct(br.q_ult, expected)
    print(f"\n  q_ult expected={expected:.1f}  got={br.q_ult:.2f}  err={err:.3f}%")
    assert err < TOL, f"FAIL: q_ult err={err:.2f}% > {TOL}%"

    print(f"\n  PASS  test_strip_undrained")


# ---------------------------------------------------------------------------
#  Test 7 -- c-phi soil, strip, phi=25, c=10
# ---------------------------------------------------------------------------

def test_strip_c_phi_soil():
    """
    Strip phi=25, c=10 kPa, B=1.5m, Df=1.2m, gamma=18.
    q = 18*1.2 = 21.6 kPa, Nq=10.66, Nc=20.72, Ngamma=9.01
    Hand: q_ult = 10*20.72 + 21.6*10.66 + 0.5*18*1.5*9.01
               = 207.2 + 230.3 + 121.6 = 559.1 kPa
    """
    f  = Foundation.strip(B=1.5, Df=1.2)
    br = bearing_resistance_ec7(f, phi_d=25.0, c_d=10.0, gamma_soil=18.0)

    print(f"\n{'='*60}")
    print(f"  TEST 7 -- Strip c-phi soil, phi=25, c=10, B=1.5m")
    print(f"{'='*60}")
    print(br.summary())

    expected = 559.1
    err = _pct(br.q_ult, expected)
    print(f"\n  q_ult expected={expected:.1f}  got={br.q_ult:.2f}  err={err:.3f}%")
    assert err < TOL, f"FAIL: q_ult err={err:.2f}% > {TOL}%"
    print(f"\n  PASS  test_strip_c_phi_soil")


# ---------------------------------------------------------------------------
#  Test 8 -- Monotonicity: higher phi -> higher q_ult
# ---------------------------------------------------------------------------

def test_monotonicity_phi_increases_capacity():
    """Higher friction angle must give higher bearing capacity."""
    f = Foundation.square(B=1.5, Df=1.0)
    q_ults = [
        bearing_resistance_ec7(f, phi_d=float(p), c_d=0.0, gamma_soil=18.0).q_ult
        for p in [20, 25, 30, 35, 40]
    ]
    print(f"\n{'='*60}")
    print(f"  TEST 8 -- Monotonicity: phi increases q_ult")
    print(f"{'='*60}")
    for p, q in zip([20,25,30,35,40], q_ults):
        print(f"  phi={p}  q_ult={q:.2f} kPa")

    for i in range(len(q_ults)-1):
        assert q_ults[i] < q_ults[i+1], f"FAIL: q_ult non-monotone at phi={20+5*i}"

    print(f"\n  PASS  test_monotonicity_phi_increases_capacity")


# ---------------------------------------------------------------------------
#  Test 9 -- Monotonicity: wider foundation increases R_ult
# ---------------------------------------------------------------------------

def test_wider_foundation_increases_resistance():
    """Wider foundation has larger A_eff and larger Ngamma term -> higher R_ult."""
    phi, c, gamma = 30.0, 0.0, 18.0
    widths  = [1.0, 1.5, 2.0, 2.5]
    r_ults  = [
        bearing_resistance_ec7(Foundation.square(B=b, Df=1.0), phi, c, gamma).R_ult
        for b in widths
    ]
    print(f"\n{'='*60}")
    print(f"  TEST 9 -- Monotonicity: wider foundation -> larger R_ult")
    print(f"{'='*60}")
    for b, r in zip(widths, r_ults):
        print(f"  B={b}m  R_ult={r:.1f} kN")

    for i in range(len(r_ults)-1):
        assert r_ults[i] < r_ults[i+1], f"FAIL: R_ult non-monotone at B={widths[i]}"

    print(f"\n  PASS  test_wider_foundation_increases_resistance")


# ---------------------------------------------------------------------------
#  Test 10 -- Monotonicity: deeper embedment increases q_ult (surcharge term)
# ---------------------------------------------------------------------------

def test_deeper_embedment_increases_capacity():
    """Deeper Df -> larger overburden q -> larger Nq term -> higher q_ult."""
    f_shallow = Foundation.square(B=1.5, Df=0.5)
    f_deep    = Foundation.square(B=1.5, Df=2.0)
    r_s = bearing_resistance_ec7(f_shallow, 30.0, 0.0, 18.0)
    r_d = bearing_resistance_ec7(f_deep,    30.0, 0.0, 18.0)

    print(f"\n{'='*60}")
    print(f"  TEST 10 -- Deeper embedment -> higher bearing capacity")
    print(f"{'='*60}")
    print(f"  Df=0.5m: q_ult={r_s.q_ult:.2f} kPa")
    print(f"  Df=2.0m: q_ult={r_d.q_ult:.2f} kPa")

    assert r_d.q_ult > r_s.q_ult, "FAIL: deeper foundation should have higher q_ult"
    print(f"\n  PASS  test_deeper_embedment_increases_capacity")


# ---------------------------------------------------------------------------
#  Test 11 -- Inclination factors: H>0 reduces capacity
# ---------------------------------------------------------------------------

def test_inclined_load_reduces_capacity():
    """Horizontal load component reduces bearing capacity via inclination factors."""
    f = Foundation.square(B=2.0, Df=1.0)
    Vd = 500.0   # kN

    r_vertical  = bearing_resistance_ec7(f, 30.0, 0.0, 18.0, V=Vd, H=0.0)
    r_inclined  = bearing_resistance_ec7(f, 30.0, 0.0, 18.0, V=Vd, H=50.0)

    print(f"\n{'='*60}")
    print(f"  TEST 11 -- Inclined load reduces bearing capacity")
    print(f"{'='*60}")
    print(f"  H=0  kN: q_ult={r_vertical.q_ult:.2f} kPa  iq={r_vertical.iq:.4f}")
    print(f"  H=50 kN: q_ult={r_inclined.q_ult:.2f} kPa  iq={r_inclined.iq:.4f}")

    assert r_inclined.q_ult < r_vertical.q_ult, \
        "FAIL: inclined load must reduce bearing capacity"
    assert r_inclined.iq < 1.0, \
        f"FAIL: iq should be < 1.0 for H>0, got {r_inclined.iq:.4f}"
    print(f"\n  PASS  test_inclined_load_reduces_capacity")


# ---------------------------------------------------------------------------
#  Test 12 -- Edge cases raise ValueError
# ---------------------------------------------------------------------------

def test_edge_cases_raise():
    """Invalid inputs must raise ValueError."""
    print(f"\n{'='*60}")
    print(f"  TEST 12 -- Edge Cases")
    print(f"{'='*60}")

    f = Foundation.strip(B=1.0, Df=1.0)

    # phi_d out of range
    try:
        bearing_factors_ec7(50.0)
        assert False, "should raise"
    except ValueError as e:
        print(f"  PASS  phi=50 raised: {e}")

    # Foundation B <= 0
    try:
        Foundation(B=0.0, Df=1.0)
        assert False, "should raise"
    except ValueError as e:
        print(f"  PASS  B=0 raised: {e}")

    # L < B
    try:
        Foundation(B=2.0, Df=1.0, L=1.0)
        assert False, "should raise"
    except ValueError as e:
        print(f"  PASS  L<B raised: {e}")

    # Eccentricity >= B/2
    try:
        Foundation(B=2.0, Df=1.0, e_B=1.0)
        assert False, "should raise"
    except ValueError as e:
        print(f"  PASS  e_B>=B/2 raised: {e}")

    # H>0 without V
    try:
        bearing_resistance_ec7(f, 30.0, 0.0, 18.0, H=50.0)
        assert False, "should raise"
    except ValueError as e:
        print(f"  PASS  H>0 no V raised: {e}")

    print(f"\n  PASS  test_edge_cases_raise")


# ---------------------------------------------------------------------------
#  Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_bearing_factors_phi30()
    test_bearing_factors_phi25()
    test_bearing_factors_phi0()
    test_strip_cohesionless_phi30()
    test_square_cohesionless_phi30()
    test_strip_undrained()
    test_strip_c_phi_soil()
    test_monotonicity_phi_increases_capacity()
    test_wider_foundation_increases_resistance()
    test_deeper_embedment_increases_capacity()
    test_inclined_load_reduces_capacity()
    test_edge_cases_raise()

    print(f"\n{'='*60}")
    print(f"  ALL bearing_capacity tests passed.")
    print(f"{'='*60}\n")
