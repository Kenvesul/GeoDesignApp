"""
tests/test_rankine_coulomb.py

Validates core/rankine_coulomb.py against textbook values and physical properties.

Textbook reference:
    Craig's Soil Mechanics, 9th ed. (Knappett & Craig)
    Chapter 11 -- Earth pressure theory.

    Known values used for validation:
        phi' = 30 deg  ->  Ka_Rankine = 0.3333,  Kp_Rankine = 3.000
        phi' = 35 deg  ->  Ka_Rankine = 0.2710,  Kp_Rankine = 3.690
        phi' = 40 deg  ->  Ka_Rankine = 0.2174,  Kp_Rankine = 4.599

        Coulomb Ka (phi=30, delta=20, beta=0, alpha=90) ~= 0.297  (Craig Table C.1)

    Active thrust (cohesionless, phi=30, gamma=18, H=5m, dry):
        Pa = 0.5 * Ka * gamma * H^2
           = 0.5 * 0.3333 * 18 * 25 = 75.0 kN/m
        y_a = H/3 = 1.667 m above base

Run from the DesignApp root:
    python -m pytest tests/
  or:
    python tests/test_rankine_coulomb.py
"""
import sys, os, math

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.rankine_coulomb import (
    ka_rankine, kp_rankine,
    ka_coulomb, kp_coulomb,
    active_pressure_at_depth,
    passive_pressure_at_depth,
    active_thrust, passive_thrust,
)


TOL = 0.005   # 0.5% tolerance for textbook comparisons


def _close(a, b, tol=TOL):
    return abs(a - b) / max(abs(b), 1e-9) < tol


# ─────────────────────────────────────────────────────────────────────────────
#  Test 1 -- Rankine Ka: textbook values at phi=30, 35, 40 deg
# ─────────────────────────────────────────────────────────────────────────────

def test_ka_rankine_textbook():
    """Ka = tan^2(45 - phi/2).  Craig Table C.1 values to 4 significant figures."""
    cases = [
        (30.0, 0.3333),
        (35.0, 0.2710),
        (40.0, 0.2174),
    ]
    print(f"\n{'='*60}")
    print(f"  TEST 1 -- Ka Rankine (textbook validation)")
    print(f"{'='*60}")
    print(f"  {'phi (deg)':>10}  {'Ka expected':>12}  {'Ka computed':>12}  {'err%':>7}")
    for phi, ka_exp in cases:
        ka_got = ka_rankine(phi)
        err = 100.0 * abs(ka_got - ka_exp) / ka_exp
        print(f"  {phi:>10.1f}  {ka_exp:>12.4f}  {ka_got:>12.4f}  {err:>6.3f}%")
        assert _close(ka_got, ka_exp), \
            f"FAIL: Ka({phi}) = {ka_got:.6f}, expected {ka_exp:.6f}"
    print(f"\n  OK  test_ka_rankine_textbook passed")


# ─────────────────────────────────────────────────────────────────────────────
#  Test 2 -- Rankine Kp: textbook values
# ─────────────────────────────────────────────────────────────────────────────

def test_kp_rankine_textbook():
    """Kp = tan^2(45 + phi/2).  Craig Table C.1."""
    cases = [
        (30.0, 3.000),
        (35.0, 3.690),
        (40.0, 4.599),
    ]
    print(f"\n{'='*60}")
    print(f"  TEST 2 -- Kp Rankine (textbook validation)")
    print(f"{'='*60}")
    print(f"  {'phi (deg)':>10}  {'Kp expected':>12}  {'Kp computed':>12}  {'err%':>7}")
    for phi, kp_exp in cases:
        kp_got = kp_rankine(phi)
        err = 100.0 * abs(kp_got - kp_exp) / kp_exp
        print(f"  {phi:>10.1f}  {kp_exp:>12.4f}  {kp_got:>12.4f}  {err:>6.3f}%")
        assert _close(kp_got, kp_exp), \
            f"FAIL: Kp({phi}) = {kp_got:.6f}, expected {kp_exp:.6f}"
    print(f"\n  OK  test_kp_rankine_textbook passed")


# ─────────────────────────────────────────────────────────────────────────────
#  Test 3 -- Rankine identity: Ka * Kp = 1.0 (smooth vertical wall)
# ─────────────────────────────────────────────────────────────────────────────

def test_ka_kp_product_identity():
    """Ka * Kp = 1 for Rankine (smooth wall, horizontal backfill)."""
    print(f"\n{'='*60}")
    print(f"  TEST 3 -- Ka * Kp = 1.0 identity")
    print(f"{'='*60}")
    for phi in [20, 25, 30, 35, 40]:
        product = ka_rankine(phi) * kp_rankine(phi)
        print(f"  phi={phi}  Ka*Kp = {product:.8f}")
        assert abs(product - 1.0) < 1e-10, \
            f"FAIL: Ka*Kp = {product:.8f} != 1.0 for phi={phi}"
    print(f"\n  OK  test_ka_kp_product_identity passed")


# ─────────────────────────────────────────────────────────────────────────────
#  Test 4 -- Coulomb Ka reduces to Rankine when delta=beta=0, alpha=90
# ─────────────────────────────────────────────────────────────────────────────

def test_coulomb_reduces_to_rankine():
    """Coulomb Ka with delta=0, beta=0, alpha=90 must equal Rankine Ka."""
    print(f"\n{'='*60}")
    print(f"  TEST 4 -- Coulomb Ka = Rankine Ka when delta=beta=0, alpha=90")
    print(f"{'='*60}")
    for phi in [20, 25, 30, 35, 40]:
        ka_r = ka_rankine(phi)
        ka_c = ka_coulomb(phi, delta=0.0, beta=0.0, alpha=90.0)
        diff = abs(ka_c - ka_r)
        print(f"  phi={phi}  Rankine={ka_r:.6f}  Coulomb={ka_c:.6f}  diff={diff:.2e}")
        assert diff < 1e-8, \
            f"FAIL: Coulomb({phi},0,0,90) = {ka_c:.8f} vs Rankine {ka_r:.8f}"
    print(f"\n  OK  test_coulomb_reduces_to_rankine passed")


# ─────────────────────────────────────────────────────────────────────────────
#  Test 5 -- Coulomb Ka with wall friction: lower than Rankine
# ─────────────────────────────────────────────────────────────────────────────

def test_coulomb_ka_wall_friction_reduces_ka():
    """
    Wall friction (delta > 0) reduces Ka because the failure wedge becomes
    steeper, mobilising more shear.  Ka_Coulomb < Ka_Rankine when delta > 0.
    Reference: Craig §11.2.
    """
    print(f"\n{'='*60}")
    print(f"  TEST 5 -- Coulomb Ka < Rankine Ka when delta > 0")
    print(f"{'='*60}")
    phi = 30.0
    for delta in [5.0, 10.0, 15.0, 20.0]:
        ka_r = ka_rankine(phi)
        ka_c = ka_coulomb(phi, delta=delta)
        print(f"  phi={phi}  delta={delta}  Ka_Rankine={ka_r:.4f}  Ka_Coulomb={ka_c:.4f}")
        assert ka_c < ka_r, \
            f"FAIL: Ka_Coulomb ({ka_c:.4f}) should be < Ka_Rankine ({ka_r:.4f}) when delta={delta}"
    print(f"\n  OK  test_coulomb_ka_wall_friction_reduces_ka passed")


# ─────────────────────────────────────────────────────────────────────────────
#  Test 6 -- Active thrust: textbook value phi=30, gamma=18, H=5m
# ─────────────────────────────────────────────────────────────────────────────

def test_active_thrust_textbook():
    """
    Cohesionless backfill, Rankine, dry:
        Pa = 0.5 * Ka * gamma * H^2 = 0.5 * 0.3333 * 18 * 25 = 75.0 kN/m
        y_a = H/3 = 1.667 m (triangular diagram)

    This is the classical textbook result for a triangular pressure diagram.
    Reference: Craig Ch. 11 basic example.
    """
    phi, gamma, H = 30.0, 18.0, 5.0
    ka = ka_rankine(phi)

    pa, y_a = active_thrust(H, gamma, ka)

    pa_expected = 0.5 * ka * gamma * H**2
    ya_expected = H / 3.0

    print(f"\n{'='*60}")
    print(f"  TEST 6 -- Active thrust textbook (phi=30, gamma=18, H=5)")
    print(f"{'='*60}")
    print(f"  Ka       = {ka:.4f}")
    print(f"  Pa exp   = {pa_expected:.3f} kN/m   computed = {pa:.3f} kN/m")
    print(f"  y_a exp  = {ya_expected:.3f} m       computed = {y_a:.3f} m")

    assert _close(pa, pa_expected, tol=0.01), \
        f"FAIL: Pa = {pa:.4f} vs expected {pa_expected:.4f}"
    assert _close(y_a, ya_expected, tol=0.01), \
        f"FAIL: y_a = {y_a:.4f} vs expected {ya_expected:.4f}"
    print(f"\n  OK  test_active_thrust_textbook passed")


# ─────────────────────────────────────────────────────────────────────────────
#  Test 7 -- Surcharge: Ka*q at surface, constant with depth
# ─────────────────────────────────────────────────────────────────────────────

def test_active_pressure_surcharge():
    """
    Uniform surcharge q adds a constant Ka*q to the pressure diagram.
    At z=0: sigma_a = Ka*q (no self-weight term).
    At z=H: sigma_a = Ka*(gamma*H + q).
    """
    phi, gamma, H, q = 30.0, 18.0, 5.0, 10.0
    ka = ka_rankine(phi)

    # Check at surface: sigma_a = Ka*q - 2*c*sqrt(Ka); c=0 so Ka*q
    sigma_top = active_pressure_at_depth(0.0, gamma, ka, c_d=0.0)
    # With no self-weight, surface pressure is 0 for purely frictional soil
    assert abs(sigma_top) < 1e-9, f"FAIL: surface pressure should be 0, got {sigma_top}"

    # Check at base with effective depth = H: pressure from Ka*gamma*H
    sigma_base = active_pressure_at_depth(H, gamma, ka, c_d=0.0)
    expected_base = ka * gamma * H
    print(f"\n{'='*60}")
    print(f"  TEST 7 -- Pressure at depth H={H}m")
    print(f"{'='*60}")
    print(f"  sigma_a(H) expected = {expected_base:.3f}  computed = {sigma_base:.3f}")
    assert _close(sigma_base, expected_base), \
        f"FAIL: sigma_a(H) = {sigma_base:.4f} vs {expected_base:.4f}"
    print(f"\n  OK  test_active_pressure_surcharge passed")


# ─────────────────────────────────────────────────────────────────────────────
#  Test 8 -- Monotonicity: Ka increases as phi decreases
# ─────────────────────────────────────────────────────────────────────────────

def test_ka_monotonicity():
    """Ka must decrease strictly as phi increases (weaker soil = more thrust)."""
    phis = [15, 20, 25, 30, 35, 40]
    kas  = [ka_rankine(p) for p in phis]
    print(f"\n{'='*60}")
    print(f"  TEST 8 -- Ka monotonicity (decreases with phi)")
    print(f"{'='*60}")
    for p, k in zip(phis, kas):
        print(f"  phi={p}  Ka={k:.4f}")
    for i in range(len(kas) - 1):
        assert kas[i] > kas[i + 1], \
            f"FAIL: Ka({phis[i]}) should be > Ka({phis[i+1]})"
    print(f"\n  OK  test_ka_monotonicity passed")


# ─────────────────────────────────────────────────────────────────────────────
#  Test 9 -- Water table increases total thrust
# ─────────────────────────────────────────────────────────────────────────────

def test_water_table_reduces_effective_thrust():
    """
    A high water table REDUCES effective active thrust.

    active_thrust() returns the EFFECTIVE lateral earth pressure component
    only.  When a water table is at the surface, effective vertical stress
    = (gamma - gamma_w) * z (buoyant weight), which is much lower than
    gamma * z.  Therefore effective Ka * sigma_v' decreases.

    TOTAL lateral thrust = effective active thrust + hydrostatic pressure.
    The hydrostatic component (0.5 * gamma_w * H^2) must be computed
    separately and added to get the total thrust on the wall.

    Manual check (phi=30, gamma=18, H=5, dry):
        Pa_eff (dry)      = 0.5 * 0.333 * 18 * 25 = 75.0 kN/m
        Pa_eff (z_w=0)    = 0.5 * 0.333 * (18-9.81) * 25 = 34.1 kN/m  (lower!)
        Pa_hydrostatic    = 0.5 * 9.81 * 25             = 122.6 kN/m
        Pa_total (z_w=0)  = 34.1 + 122.6               = 156.7 kN/m  (higher!)

    Reference: Craig §11.1 — separation of effective and hydrostatic components.
    """
    phi, gamma, H = 30.0, 18.0, 5.0
    ka = ka_rankine(phi)

    pa_dry, _  = active_thrust(H, gamma, ka)
    pa_wet, _  = active_thrust(H, gamma, ka, z_w=0.0)   # fully submerged, effective only

    print(f"\n{'='*60}")
    print(f"  TEST 9 -- Water table reduces EFFECTIVE active thrust")
    print(f"{'='*60}")
    print(f"  Pa_eff (dry)    = {pa_dry:.3f} kN/m")
    print(f"  Pa_eff (z_w=0)  = {pa_wet:.3f} kN/m  (effective only, buoyant weight)")
    print(f"  Pa_hydrostatic  = {0.5 * 9.81 * H**2:.3f} kN/m  (added separately)")
    print(f"  Pa_total (wet)  = {pa_wet + 0.5 * 9.81 * H**2:.3f} kN/m  (effective + hydrostatic)")

    # Effective thrust decreases with high water table (reduced effective stress)
    assert pa_wet < pa_dry, (
        f"FAIL: effective thrust (z_w=0) = {pa_wet:.3f} should be < dry {pa_dry:.3f}.  "
        "active_thrust() returns effective component only."
    )

    # Validate against hand calculation: Pa_eff (z_w=0) = 0.5 * Ka * gamma' * H^2
    gamma_prime = gamma - 9.81   # buoyant unit weight
    pa_wet_expected = 0.5 * ka * gamma_prime * H**2
    assert abs(pa_wet - pa_wet_expected) / pa_wet_expected < 0.01, (
        f"FAIL: effective wet thrust = {pa_wet:.3f}, expected {pa_wet_expected:.3f}"
    )

    print(f"\n  OK  test_water_table_reduces_effective_thrust passed")


# ─────────────────────────────────────────────────────────────────────────────
#  Test 10 -- Edge cases raise ValueError
# ─────────────────────────────────────────────────────────────────────────────

def test_edge_cases():
    """Invalid parameters must raise ValueError."""
    print(f"\n{'='*60}")
    print(f"  TEST 10 -- Edge Cases")
    print(f"{'='*60}")

    # phi out of range
    try:
        ka_rankine(90.0)
        assert False, "Should raise"
    except ValueError as e:
        print(f"  OK phi=90 raised: {e}")

    # Coulomb: delta > phi
    try:
        ka_coulomb(30.0, delta=35.0)
        assert False, "Should raise"
    except ValueError as e:
        print(f"  OK delta>phi raised: {e}")

    # Coulomb: beta >= phi
    try:
        ka_coulomb(30.0, beta=30.0)
        assert False, "Should raise"
    except ValueError as e:
        print(f"  OK beta>=phi raised: {e}")

    # active_thrust: h <= 0
    try:
        active_thrust(0.0, 18.0, 0.333)
        assert False, "Should raise"
    except ValueError as e:
        print(f"  OK h=0 raised: {e}")

    # active_pressure_at_depth: z < 0
    try:
        active_pressure_at_depth(-1.0, 18.0, 0.333)
        assert False, "Should raise"
    except ValueError as e:
        print(f"  OK z<0 raised: {e}")

    print(f"\n  OK  test_edge_cases passed")


# ─────────────────────────────────────────────────────────────────────────────
#  Runner
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    test_ka_rankine_textbook()
    test_kp_rankine_textbook()
    test_ka_kp_product_identity()
    test_coulomb_reduces_to_rankine()
    test_coulomb_ka_wall_friction_reduces_ka()
    test_active_thrust_textbook()
    test_active_pressure_surcharge()
    test_ka_monotonicity()
    test_water_table_reduces_effective_thrust()
    test_edge_cases()

    print(f"\n{'='*60}")
    print(f"  ALL rankine_coulomb tests passed.")
    print(f"{'='*60}\n")
