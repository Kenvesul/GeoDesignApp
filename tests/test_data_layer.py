"""
tests/test_data_layer.py

Validates data/materials.py, data/standards/ec7.json, and data/soil_library.json.

Checks:
    - EC7 JSON: correct partial factor values from EN 1997-1:2004 Annex A Tables A.3/A.4/A.5.
    - Soil library JSON: valid Soil objects can be constructed from every preset.
    - materials.py: EC2 concrete grade properties and design value formulae.

Reference:
    EN 1997-1:2004 Annex A Tables A.3, A.4, A.5.
    EN 1992-1-1:2004 Table 3.1 (Concrete properties).

Run from the DesignApp root:
    python -m pytest tests/
  or:
    python tests/test_data_layer.py
"""
import sys, os, json, math

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.materials import (
    Concrete, ReinforcingSteel,
    CONCRETE_GRADES, STEEL_GRADES,
    get_concrete, get_steel,
    C25_30, B500B,
)
from models.soil import Soil

DATA_DIR = os.path.join(ROOT, "data")


# ---------------------------------------------------------------------------
#  Test 1 – EC7 JSON loads and contains correct DA1 partial factors
# ---------------------------------------------------------------------------

def test_ec7_json_partial_factors():
    """
    EC7 JSON must be valid and contain correct DA1 partial factor values from
    EN 1997-1:2004 Annex A Tables A.3 / A.4 / A.5.

    Key values checked:
        A1: gamma_G_unfav=1.35, gamma_Q_unfav=1.50
        A2: gamma_G_unfav=1.00, gamma_Q_unfav=1.30
        M1: gamma_phi=1.00, gamma_c=1.00
        M2: gamma_phi=1.25, gamma_c=1.25
        R1: bearing=1.00, sliding=1.00
    """
    path = os.path.join(DATA_DIR, "standards", "ec7.json")
    assert os.path.exists(path), f"FAIL: {path} does not exist"

    with open(path) as f:
        ec7 = json.load(f)

    print("\n" + "="*60)
    print("  TEST 1 – EC7 JSON Partial Factors")
    print("="*60)

    checks = [
        ("actions.A1.gamma_G_unfav", ec7["actions"]["A1"]["gamma_G_unfav"], 1.35),
        ("actions.A1.gamma_Q_unfav", ec7["actions"]["A1"]["gamma_Q_unfav"], 1.50),
        ("actions.A2.gamma_G_unfav", ec7["actions"]["A2"]["gamma_G_unfav"], 1.00),
        ("actions.A2.gamma_Q_unfav", ec7["actions"]["A2"]["gamma_Q_unfav"], 1.30),
        ("materials.M1.gamma_phi",   ec7["materials"]["M1"]["gamma_phi"],   1.00),
        ("materials.M1.gamma_c",     ec7["materials"]["M1"]["gamma_c"],     1.00),
        ("materials.M2.gamma_phi",   ec7["materials"]["M2"]["gamma_phi"],   1.25),
        ("materials.M2.gamma_c",     ec7["materials"]["M2"]["gamma_c"],     1.25),
        ("resistance.R1.bearing",    ec7["resistance"]["R1"]["bearing"],    1.00),
        ("resistance.R1.sliding",    ec7["resistance"]["R1"]["sliding"],    1.00),
    ]

    for label, got, expected in checks:
        ok = abs(got - expected) < 1e-9
        flag = "PASS" if ok else "FAIL"
        print(f"  {flag}  {label:<35} = {got}")
        assert ok, f"FAIL: {label} = {got}, expected {expected}"

    # DA1 structure check
    da1 = ec7["design_approaches"]["DA1"]
    assert da1["combination_1"]["actions"]   == "A1"
    assert da1["combination_1"]["materials"] == "M1"
    assert da1["combination_2"]["actions"]   == "A2"
    assert da1["combination_2"]["materials"] == "M2"
    print("  PASS  DA1 combination structure")

    print("\n  PASS  test_ec7_json_partial_factors")


# ---------------------------------------------------------------------------
#  Test 2 – Soil library JSON: all presets produce valid Soil objects
# ---------------------------------------------------------------------------

def test_soil_library_valid_soils():
    """
    Every entry in soil_library.json must produce a valid Soil object
    (non-negative phi_k, c_k, positive gamma).
    """
    path = os.path.join(DATA_DIR, "soil_library.json")
    assert os.path.exists(path), f"FAIL: {path} does not exist"

    with open(path) as f:
        library = json.load(f)

    print("\n" + "="*60)
    print("  TEST 2 – Soil Library: All Presets Valid")
    print("="*60)
    print(f"  {'ID':<25} {'Name':<22} {'gamma':>6} {'phi':>5} {'c':>6}")
    print("  " + "-"*68)

    soils = library["soils"]
    assert len(soils) > 0, "FAIL: soil library is empty"

    for entry in soils:
        soil = Soil(
            name=entry["name"],
            unit_weight=entry["gamma"],
            friction_angle=entry["phi_k"],
            cohesion=entry["c_k"],
        )
        assert soil.gamma > 0,   f"FAIL [{entry['id']}]: gamma <= 0"
        assert soil.phi_k >= 0,  f"FAIL [{entry['id']}]: phi_k < 0"
        assert soil.c_k >= 0,    f"FAIL [{entry['id']}]: c_k < 0"
        print(f"  PASS  {entry['id']:<25} {entry['name']:<22} "
              f"{entry['gamma']:>6.1f} {entry['phi_k']:>5.1f} {entry['c_k']:>6.1f}")

    print(f"\n  {len(soils)} soil presets validated")
    print("\n  PASS  test_soil_library_valid_soils")


# ---------------------------------------------------------------------------
#  Test 3 – Concrete grades: EC2 Table 3.1 reference values
# ---------------------------------------------------------------------------

def test_concrete_grades_ec2_values():
    """
    Validates pre-defined concrete grades against EC2 Table 3.1.

    Key checks:
        C25/30: fck=25, fck_cube=30, fctm=2.56 MPa, Ecm=30.5 GPa  (EC2 Table 3.1)
        C30/37: fck=30, fck_cube=37, fctm=2.90 MPa, Ecm=32.0 GPa
        Design strength: fcd = fck / gamma_c = 25 / 1.5 = 16.67 MPa for C25/30
    """
    print("\n" + "="*60)
    print("  TEST 3 – Concrete Grades (EC2 Table 3.1)")
    print("="*60)

    # All 5 grades must be present
    for grade in ["C20/25", "C25/30", "C30/37", "C35/45", "C40/50"]:
        c = get_concrete(grade)
        assert c.fck > 0 and c.Ecm > 0, f"FAIL: {grade} has invalid properties"
        print(f"  {grade}: fck={c.fck} MPa  fctm={c.fctm} MPa  Ecm={c.Ecm} GPa  "
              f"fcd={c.fcd():.2f} MPa")

    # Spot-check C25/30 against EC2 Table 3.1
    c25 = get_concrete("C25/30")
    assert abs(c25.fck      - 25.0) < 0.01, "FAIL: C25/30 fck"
    assert abs(c25.fck_cube - 30.0) < 0.01, "FAIL: C25/30 fck_cube"
    assert abs(c25.fctm     -  2.56) < 0.02, f"FAIL: C25/30 fctm={c25.fctm}"
    assert abs(c25.Ecm      - 30.5) < 0.2,  f"FAIL: C25/30 Ecm={c25.Ecm}"

    # Design strength check
    fcd_expected = 25.0 / 1.5
    assert abs(c25.fcd() - fcd_expected) < 0.001, \
        f"FAIL: C25/30 fcd = {c25.fcd():.4f}, expected {fcd_expected:.4f}"
    print(f"\n  C25/30 fcd = {c25.fcd():.3f} MPa (= 25/1.5)  PASS")

    # Monotonicity: Ecm increases with fck
    grades_ordered = ["C20/25", "C25/30", "C30/37", "C35/45", "C40/50"]
    ecms = [get_concrete(g).Ecm for g in grades_ordered]
    for i in range(len(ecms) - 1):
        assert ecms[i] < ecms[i+1], \
            f"FAIL: Ecm not increasing: {grades_ordered[i]} -> {grades_ordered[i+1]}"
    print("  Ecm increases monotonically with fck  PASS")

    print("\n  PASS  test_concrete_grades_ec2_values")


# ---------------------------------------------------------------------------
#  Test 4 – Steel grades: yield strength and design value
# ---------------------------------------------------------------------------

def test_steel_grades():
    """
    B500B: fyk=500 MPa, fyd = 500/1.15 = 434.78 MPa, Es=200 GPa.
    All three ductility classes (A, B, C) must be present.
    """
    print("\n" + "="*60)
    print("  TEST 4 – Steel Grades (EN 10080)")
    print("="*60)

    for grade in ["B500A", "B500B", "B500C"]:
        s = get_steel(grade)
        assert s.fyk == 500.0, f"FAIL: {grade} fyk != 500"
        print(f"  {grade}: fyk={s.fyk} MPa  fyd={s.fyd():.2f} MPa  "
              f"Es={s.Es} GPa  class={s.ductility}")

    b500b = get_steel("B500B")
    fyd_expected = 500.0 / 1.15
    assert abs(b500b.fyd() - fyd_expected) < 0.01, \
        f"FAIL: B500B fyd = {b500b.fyd():.4f}, expected {fyd_expected:.4f}"
    print(f"\n  B500B fyd = {b500b.fyd():.2f} MPa (= 500/1.15)  PASS")

    print("\n  PASS  test_steel_grades")


# ---------------------------------------------------------------------------
#  Test 5 – Unknown grade raises KeyError
# ---------------------------------------------------------------------------

def test_unknown_grade_raises():
    """get_concrete and get_steel must raise KeyError for unknown grades."""
    print("\n" + "="*60)
    print("  TEST 5 – Unknown Grade Raises KeyError")
    print("="*60)

    try:
        get_concrete("C99/999")
        assert False, "FAIL: should raise KeyError"
    except KeyError as e:
        print(f"  PASS  unknown concrete: {e}")

    try:
        get_steel("S355")
        assert False, "FAIL: should raise KeyError"
    except KeyError as e:
        print(f"  PASS  unknown steel: {e}")

    print("\n  PASS  test_unknown_grade_raises")


# ---------------------------------------------------------------------------
#  Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    test_ec7_json_partial_factors()
    test_soil_library_valid_soils()
    test_concrete_grades_ec2_values()
    test_steel_grades()
    test_unknown_grade_raises()

    print("\n" + "="*60)
    print("  ALL data layer tests passed.")
    print("="*60 + "\n")
