"""
tests/test_stratigraphy.py

Validates models/stratigraphy.py against known layered profile queries
and physical consistency checks.

Textbook fixture (hand-verifiable):
    3-layer profile:
        0.0 – 2.0 m : Fill      (gamma=17, phi=22, c=0)
        2.0 – 7.0 m : Sand      (gamma=19, phi=32, c=0)
        7.0 – inf   : Clay      (gamma=20, phi=25, c=15)

    Query checks:
        get_soil_at_depth(0.0)  -> Fill   (z=0 is within first layer: 0 <= 0 <= 2.0)
        get_soil_at_depth(1.0)  -> Fill
        get_soil_at_depth(2.0)  -> Fill   (boundary belongs to upper layer: z <= depth_bottom)
        get_soil_at_depth(2.01) -> Sand
        get_soil_at_depth(5.0)  -> Sand
        get_soil_at_depth(7.0)  -> Sand   (z=7.0 still within Sand: z <= 7.0)
        get_soil_at_depth(7.01) -> Clay
        get_soil_at_depth(100)  -> Clay   (infinite depth)

    layer_boundaries() must return [0.0, 2.0, 7.0]  (top of each layer, excl. inf)

Reference:
    Craig's Soil Mechanics, 9th ed., Chapter 9 and 11 (layered profiles).
    Eurocode 7 – EN 1997-1:2004, Section 3 (Geotechnical data, layered ground).

Run from the DesignApp root:
    python -m pytest tests/
  or:
    python tests/test_stratigraphy.py
"""
import sys, os, math

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from models.soil         import Soil
from models.stratigraphy import Stratigraphy, SoilLayer


# ---------------------------------------------------------------------------
#  Shared fixtures
# ---------------------------------------------------------------------------

FILL = Soil("Fill",  unit_weight=17.0, friction_angle=22, cohesion=0.0)
SAND = Soil("Sand",  unit_weight=19.0, friction_angle=32, cohesion=0.0)
CLAY = Soil("Clay",  unit_weight=20.0, friction_angle=25, cohesion=15.0)

LAYERS_3 = [
    SoilLayer(FILL, depth_bottom=2.0),
    SoilLayer(SAND, depth_bottom=7.0),
    SoilLayer(CLAY, depth_bottom=float("inf")),
]

STRAT_3 = Stratigraphy(LAYERS_3)

# Single-layer convenience
STRAT_1 = Stratigraphy.single_layer(SAND)


# ---------------------------------------------------------------------------
#  Test 1 – Construction and n_layers
# ---------------------------------------------------------------------------

def test_construction_and_layer_count():
    """Stratigraphy must store exactly the layers provided."""
    print("\n" + "="*60)
    print("  TEST 1 – Construction and Layer Count")
    print("="*60)

    assert STRAT_3.n_layers == 3, f"FAIL: expected 3 layers, got {STRAT_3.n_layers}"
    assert STRAT_1.n_layers == 1, f"FAIL: expected 1 layer, got {STRAT_1.n_layers}"
    print(f"  3-layer strat: n_layers = {STRAT_3.n_layers}  OK")
    print(f"  1-layer strat: n_layers = {STRAT_1.n_layers}  OK")
    print(repr(STRAT_3))
    print("\n  PASS  test_construction_and_layer_count")


# ---------------------------------------------------------------------------
#  Test 2 – Depth query: correct soil returned at each depth
# ---------------------------------------------------------------------------

def test_depth_queries_correct_soil():
    """
    get_soil_at_depth() must return the correct Soil at each reference depth.

    Hand-verified against 3-layer fixture:
        z=0.0  -> Fill  (within first layer)
        z=1.0  -> Fill
        z=2.0  -> Fill  (boundary depth belongs to the layer above)
        z=2.01 -> Sand  (just past boundary -> Sand)
        z=5.0  -> Sand
        z=7.0  -> Sand  (boundary belongs to Sand layer)
        z=7.01 -> Clay
        z=100  -> Clay  (infinite depth)
    """
    cases = [
        (0.00,  FILL,  "at surface"),
        (1.00,  FILL,  "mid Fill"),
        (2.00,  FILL,  "at Fill/Sand boundary (inclusive)"),
        (2.01,  SAND,  "just into Sand"),
        (5.00,  SAND,  "mid Sand"),
        (7.00,  SAND,  "at Sand/Clay boundary (inclusive)"),
        (7.01,  CLAY,  "just into Clay"),
        (100.0, CLAY,  "deep Clay (infinite layer)"),
    ]

    print("\n" + "="*60)
    print("  TEST 2 – Depth Query: Correct Soil Returned")
    print("="*60)
    print(f"  {'z (m)':>6}  {'Expected':>10}  {'Got':>10}  Result")
    print("  " + "-"*50)

    for z, expected_soil, note in cases:
        got = STRAT_3.get_soil_at_depth(z)
        ok  = got is expected_soil
        flag = "PASS" if ok else "FAIL"
        print(f"  {z:6.2f}  {expected_soil.name:>10}  {got.name:>10}  {flag}  ({note})")
        assert ok, (
            f"FAIL at z={z}: expected soil '{expected_soil.name}', "
            f"got '{got.name}'"
        )

    print("\n  PASS  test_depth_queries_correct_soil")


# ---------------------------------------------------------------------------
#  Test 3 – layer_boundaries returns correct boundary depths
# ---------------------------------------------------------------------------

def test_layer_boundaries():
    """
    layer_boundaries() must return [0.0, 2.0, 7.0] for the 3-layer fixture
    (top of profile plus each inter-layer boundary, excluding the infinite base).
    """
    expected = [0.0, 2.0, 7.0]
    got = STRAT_3.layer_boundaries()

    print("\n" + "="*60)
    print("  TEST 3 – Layer Boundaries")
    print("="*60)
    print(f"  Expected : {expected}")
    print(f"  Got      : {got}")

    assert got == expected, f"FAIL: layer_boundaries() = {got}, expected {expected}"

    # Single-layer stratigraphy: only [0.0]
    assert STRAT_1.layer_boundaries() == [0.0], \
        f"FAIL: single-layer boundaries should be [0.0], got {STRAT_1.layer_boundaries()}"
    print(f"  Single-layer boundaries: {STRAT_1.layer_boundaries()}  OK")

    print("\n  PASS  test_layer_boundaries")


# ---------------------------------------------------------------------------
#  Test 4 – single_layer convenience constructor
# ---------------------------------------------------------------------------

def test_single_layer_constructor():
    """Stratigraphy.single_layer() must cover all depths with the given soil."""
    strat = Stratigraphy.single_layer(CLAY)

    print("\n" + "="*60)
    print("  TEST 4 – single_layer() Constructor")
    print("="*60)

    for z in [0.0, 1.0, 10.0, 100.0, 1000.0]:
        soil = strat.get_soil_at_depth(z)
        assert soil is CLAY, f"FAIL: expected CLAY at z={z}, got {soil.name}"
        print(f"  z={z:7.1f}  -> {soil.name}  OK")

    assert strat.n_layers == 1, "FAIL: should be 1 layer"
    print("\n  PASS  test_single_layer_constructor")


# ---------------------------------------------------------------------------
#  Test 5 – Unit weight profile increases monotonically with depth
#            (this specific fixture has heavier soils deeper)
# ---------------------------------------------------------------------------

def test_unit_weight_increases_with_depth():
    """
    For the 3-layer fixture, unit weights are 17, 19, 20 (increasing downward).
    Querying at the mid-depth of each layer must return increasing gamma values.
    """
    print("\n" + "="*60)
    print("  TEST 5 – Unit Weight Profile (Monotonically Increasing)")
    print("="*60)

    mid_depths = [1.0, 4.5, 50.0]   # mid of Fill, Sand, Clay
    gammas = [STRAT_3.get_soil_at_depth(z).gamma for z in mid_depths]

    print(f"  {'z (m)':>6}  {'Soil':>10}  {'gamma':>8}")
    for z, g in zip(mid_depths, gammas):
        soil = STRAT_3.get_soil_at_depth(z)
        print(f"  {z:6.1f}  {soil.name:>10}  {g:8.1f}")

    for i in range(len(gammas) - 1):
        assert gammas[i] < gammas[i + 1], (
            f"FAIL: gamma at z={mid_depths[i]} ({gammas[i]}) should be < "
            f"gamma at z={mid_depths[i+1]} ({gammas[i+1]})"
        )
    print("\n  PASS  test_unit_weight_increases_with_depth")


# ---------------------------------------------------------------------------
#  Test 6 – Effective stress integration through the 3-layer profile
# ---------------------------------------------------------------------------

def test_effective_stress_layered_profile():
    """
    Computes total vertical stress at layer boundaries by accumulating
    gamma * h for each layer.  This mirrors how slicer.py will use
    Stratigraphy in multi-layer slope analysis.

    Hand-check (dry profile):
        sigma_v at z=2.0 : 17.0 * 2.0                = 34.0 kPa
        sigma_v at z=7.0 : 34.0 + 19.0 * 5.0         = 129.0 kPa
        sigma_v at z=12.0: 129.0 + 20.0 * 5.0        = 229.0 kPa
    """
    print("\n" + "="*60)
    print("  TEST 6 – Effective Stress Integration (Layered)")
    print("="*60)

    def total_stress(strat, z_target):
        """Simple Euler integration of gamma*dz through the profile."""
        dz    = 0.01   # 1 cm steps
        steps = int(z_target / dz)
        sigma = 0.0
        for i in range(steps):
            z_mid = (i + 0.5) * dz
            soil  = strat.get_soil_at_depth(z_mid)
            sigma += soil.gamma * dz
        return sigma

    checks = [
        (2.0,  34.0,  "base of Fill"),
        (7.0,  129.0, "base of Sand"),
        (12.0, 229.0, "5m into Clay"),
    ]

    print(f"  {'z (m)':>6}  {'Expected sigma_v (kPa)':>24}  {'Computed':>10}  {'Err%':>7}  Note")
    for z, expected, note in checks:
        computed = total_stress(STRAT_3, z)
        err_pct  = 100.0 * abs(computed - expected) / expected
        flag = "PASS" if err_pct < 1.0 else "FAIL"
        print(f"  {z:6.1f}  {expected:>24.1f}  {computed:>10.2f}  {err_pct:>6.3f}%  {note}  {flag}")
        assert err_pct < 1.0, f"FAIL: sigma_v({z}) = {computed:.2f}, expected {expected:.1f}"

    print("\n  PASS  test_effective_stress_layered_profile")


# ---------------------------------------------------------------------------
#  Test 7 – Invalid construction raises ValueError
# ---------------------------------------------------------------------------

def test_invalid_construction_raises():
    """Malformed layer stacks must raise ValueError with a clear message."""
    print("\n" + "="*60)
    print("  TEST 7 – Invalid Construction Raises ValueError")
    print("="*60)

    # Empty layer list
    try:
        Stratigraphy([])
        assert False, "FAIL: should raise for empty list"
    except ValueError as e:
        print(f"  PASS  empty list: {e}")

    # Last layer does not extend to infinity
    try:
        Stratigraphy([
            SoilLayer(FILL, 2.0),
            SoilLayer(SAND, 5.0),   # finite — missing infinite base
        ])
        assert False, "FAIL: should raise when last layer is not infinite"
    except ValueError as e:
        print(f"  PASS  no infinite base: {e}")

    # Layers not in ascending order
    try:
        Stratigraphy([
            SoilLayer(FILL, 5.0),
            SoilLayer(SAND, 3.0),   # depth_bottom < previous
            SoilLayer(CLAY, float("inf")),
        ])
        assert False, "FAIL: should raise for non-ascending boundaries"
    except ValueError as e:
        print(f"  PASS  non-ascending: {e}")

    # SoilLayer with depth_bottom = 0
    try:
        SoilLayer(FILL, depth_bottom=0.0)
        assert False, "FAIL: should raise for depth_bottom=0"
    except ValueError as e:
        print(f"  PASS  depth_bottom=0: {e}")

    # Negative depth query
    try:
        STRAT_3.get_soil_at_depth(-1.0)
        assert False, "FAIL: should raise for z < 0"
    except ValueError as e:
        print(f"  PASS  z<0: {e}")

    print("\n  PASS  test_invalid_construction_raises")


# ---------------------------------------------------------------------------
#  Test 8 – layers property returns a copy (mutation safety)
# ---------------------------------------------------------------------------

def test_layers_property_is_copy():
    """Modifying the returned layers list must not affect the Stratigraphy."""
    layers_copy = STRAT_3.layers
    original_count = STRAT_3.n_layers

    layers_copy.clear()   # mutate the copy

    assert STRAT_3.n_layers == original_count, (
        f"FAIL: internal state mutated — n_layers changed from "
        f"{original_count} to {STRAT_3.n_layers}"
    )

    print("\n" + "="*60)
    print("  TEST 8 – layers Property Returns a Safe Copy")
    print("="*60)
    print(f"  Original n_layers = {original_count}, after mutating copy = {STRAT_3.n_layers}")
    print("\n  PASS  test_layers_property_is_copy")


# ---------------------------------------------------------------------------
#  Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_construction_and_layer_count()
    test_depth_queries_correct_soil()
    test_layer_boundaries()
    test_single_layer_constructor()
    test_unit_weight_increases_with_depth()
    test_effective_stress_layered_profile()
    test_invalid_construction_raises()
    test_layers_property_is_copy()

    print("\n" + "="*60)
    print("  ALL stratigraphy tests passed.")
    print("="*60 + "\n")
