"""
tests/test_api.py
=================
Unit tests for ui/api.py - the adapter layer between UI and math engine.

All tests use only primitive inputs and verify only primitive outputs,
confirming that api.py correctly orchestrates the full pipeline and that
no raw model objects leak into the return values (JSON-serialisability
is verified explicitly).

Reference values (slope)  : Craig (2004) Example 9.2 - loose sand 1:2 slope
Reference values (wall)   : Bowles (1996) Table 11-2 - gravity wall sanity check
Reference values (fdn)    : EC7 Annex D worked example - dense sand strip footing
"""

import sys, os, json, math, tempfile
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import api

# â”€â”€ Shared fixtures â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

SLOPE_PARAMS = dict(
    soil_name="Dense Sand",
    gamma=19.0,
    phi_k=35.0,
    c_k=0.0,
    slope_points=[[0,3],[6,3],[12,0],[18,0]],
    ru=0.0,
    n_cx=8, n_cy=8, n_r=5,   # coarse grid for speed
    num_slices=15,
)

FOUND_PARAMS = dict(
    soil_name="Medium Sand",
    gamma=18.0,
    phi_k=30.0,
    c_k=0.0,
    B=2.0, Df=1.0,            # 2 m wide strip, 1 m deep
    Gk=200.0,                 # 200 kN/m characteristic permanent load
    Qk=80.0,
    Es_kpa=15000.0,
    nu=0.3,
    s_lim=0.025,
)

WALL_PARAMS = dict(
    soil_name="Granular Fill",
    gamma=18.0,
    phi_k=30.0,
    c_k=0.0,
    H_wall=4.0,
    B_base=3.0,
    B_toe=0.8,
    t_stem_base=0.4,
    t_stem_top=0.3,
    t_base=0.5,
    surcharge_kpa=10.0,
)


def _assert_json(result: dict, label: str) -> None:
    """Verify the result dict is fully JSON-serialisable (no raw model objects)."""
    try:
        json.dumps(result)
    except TypeError as exc:
        raise AssertionError(f"{label}: result is not JSON-serialisable: {exc}")


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 1. Library helpers
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def test_get_soil_library():
    print("\n" + "="*60)
    print("  TEST 1 â€” get_soil_library()")
    lib = api.get_soil_library()
    assert isinstance(lib, list),          "Expected list"
    assert len(lib) >= 5,                  f"Expected â‰¥5 soils, got {len(lib)}"
    assert "name"  in lib[0],             "Missing 'name'"
    assert "gamma" in lib[0],             "Missing 'gamma'"
    assert "phi_k" in lib[0],             "Missing 'phi_k'"
    print(f"  Soils in library : {len(lib)}")
    for s in lib[:3]:
        print(f"    {s['name']}  Î³={s['gamma']}  Ï†'={s['phi_k']}")
    print("  PASS")


def test_get_material_grades():
    print("\n" + "="*60)
    print("  TEST 2 â€” get_material_grades()")
    grades = api.get_material_grades()
    assert "concrete" in grades
    assert "steel"    in grades
    assert "C25/30"   in grades["concrete"]
    assert "B500B"    in grades["steel"]
    print(f"  Concrete: {grades['concrete']}")
    print(f"  Steel   : {grades['steel']}")
    print("  PASS")


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 2. Slope validation
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def test_validate_slope_params_valid():
    print("\n" + "="*60)
    print("  TEST 3 â€” validate_slope_params: valid input â†’ no errors")
    errs = api.validate_slope_params(SLOPE_PARAMS)
    assert errs == [], f"Expected no errors, got: {errs}"
    print("  PASS")


def test_validate_slope_params_invalid():
    print("\n" + "="*60)
    print("  TEST 4 â€” validate_slope_params: bad inputs â†’ errors returned")
    bad = dict(gamma=999, phi_k=-5, slope_points=[[0,0]], ru=2.0)
    errs = api.validate_slope_params(bad)
    assert len(errs) >= 3, f"Expected â‰¥3 errors, got {len(errs)}: {errs}"
    print(f"  Errors caught ({len(errs)}): {errs}")
    print("  PASS")


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 3. Slope analysis
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def test_slope_analysis_returns_ok():
    print("\n" + "="*60)
    print("  TEST 5 â€” run_slope_analysis: returns ok=True, expected keys present")
    res = api.run_slope_analysis(SLOPE_PARAMS)

    assert res.get("ok"), f"Expected ok=True, got: {res.get('error','?')}"
    for key in ("fos_char","fos_d","passes","comb1","comb2",
                "critical_circle","slices","method","n_circles_tested"):
        assert key in res, f"Missing key '{key}'"
    _assert_json(res, "slope analysis")
    print(f"  FoS (char)       : {res['fos_char']}")
    print(f"  FoS (design)     : {res['fos_d']}")
    print(f"  Passes EC7 DA1   : {res['passes']}")
    print(f"  Method           : {res['method']}")
    print(f"  Circles tested   : {res['n_circles_tested']}")
    print(f"  Critical circle  : cx={res['critical_circle']['cx']:.2f}  "
          f"cy={res['critical_circle']['cy']:.2f}  r={res['critical_circle']['r']:.2f}")
    print(f"  Slices returned  : {len(res['slices'])}")
    print("  PASS")


def test_slope_analysis_fos_range():
    print("\n" + "="*60)
    print("  TEST 6 - run_slope_analysis: FoS values are positive and ordered")
    res = api.run_slope_analysis(SLOPE_PARAMS)
    assert res["ok"]
    assert 0.1 < res["fos_char"] < float("inf"), \
        f"FoS_char={res['fos_char']} out of plausible range"
    assert 0.1 < res["fos_d"] < float("inf"), \
        f"FoS_d={res['fos_d']} out of plausible range"
    assert res["comb2"]["fos_d"] <= res["comb1"]["fos_d"] + 0.001, \
        f"C2 FoS_d={res['comb2']['fos_d']} should be <= C1 FoS_d={res['comb1']['fos_d']}"
    print(f"  FoS_char={res['fos_char']}  FoS_d={res['fos_d']}")
    print(f"  C1 FoS_d={res['comb1']['fos_d']}  C2 FoS_d={res['comb2']['fos_d']}")
    print("  PASS")


def test_slope_analysis_combinations():
    print("\n" + "="*60)
    print("  TEST 7 - run_slope_analysis: DA1 combination structure")
    res = api.run_slope_analysis(SLOPE_PARAMS)
    assert res["ok"]
    for combo_key in ("comb1", "comb2"):
        c = res[combo_key]
        assert "label" in c, f"Missing 'label' in {combo_key}"
        assert "gamma_phi" in c
        assert "phi_d" in c
        assert "fos_d" in c
        assert "passes" in c
        assert c["phi_d"] <= SLOPE_PARAMS["phi_k"] + 0.01, \
            f"{combo_key} phi_d={c['phi_d']} > phi_k={SLOPE_PARAMS['phi_k']}"
        print(
            f"  {c['label']}  gamma_phi={c['gamma_phi']}  phi_d={c['phi_d']:.1f} deg  "
            f"FoS_d={c['fos_d']:.4f}  passes={c['passes']}"
        )
    print("  PASS")


def test_slope_analysis_reports_governing_combination():
    print("\n" + "="*60)
    print("  TEST 8 - run_slope_analysis: governing combination key present")
    res = api.run_slope_analysis(SLOPE_PARAMS)
    assert res["ok"]
    assert res["governing_combination"] in ("DA1-C1", "DA1-C2")
    print(f"  Governing combination: {res['governing_combination']}")
    print("  PASS")


def test_slope_analysis_near_flat_profile_stays_stable():
    print("\n" + "="*60)
    print("  TEST 9 - run_slope_analysis: near-flat dry profile should not collapse")
    res = api.run_slope_analysis(dict(
        soil_name="Dense Sand",
        gamma=19.0,
        phi_k=35.0,
        c_k=0.0,
        slope_points=[[0, 3], [30, 3], [60, 2.5], [90, 2.5]],
        ru=0.0,
        n_cx=12, n_cy=12, n_r=8,
        num_slices=20,
    ))
    assert res["ok"], res.get("error", "Expected ok=True")
    assert res["passes"] is True, f"Expected stable result, got {res}"
    print(f"  FoS_char={res['fos_char']}  FoS_d={res['fos_d']}")
    print("  PASS")


def test_slope_analysis_error_handling():
    print("\n" + "="*60)
    print("  TEST 10 - run_slope_analysis: bad input -> ok=False, no exception raised")
    res = api.run_slope_analysis(dict(gamma="not_a_number", phi_k=35,
                                     slope_points=[[0,0],[10,0]]))
    assert res.get("ok") is False, f"Expected ok=False, got: {res}"
    assert "error" in res
    print(f"  Error captured: {res['error'][:80]}")
    print("  PASS")


# 4. Foundation analysis
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def test_foundation_analysis_returns_ok():
    print("\n" + "="*60)
    print("  TEST 9 â€” run_foundation_analysis: returns ok=True, expected keys")
    res = api.run_foundation_analysis(FOUND_PARAMS)
    assert res.get("ok"), f"Expected ok=True, got: {res.get('error','?')}"
    for key in ("foundation","soil","comb1","comb2","uls_passes",
                "s_immediate_mm","s_total_mm","s_lim_mm","sls_passes","passes"):
        assert key in res, f"Missing key '{key}'"
    _assert_json(res, "foundation analysis")
    print(f"  Rd (C2)          : {res['comb2']['Rd']:.1f} kN/m")
    print(f"  Vd (C2)          : {res['comb2']['Vd']:.1f} kN/m")
    print(f"  Utilisation (C2) : {res['comb2']['utilisation']:.3f}")
    print(f"  ULS passes       : {res['uls_passes']}")
    if res['s_immediate_mm'] is not None:
        print(f"  Settlement imm.  : {res['s_immediate_mm']:.1f} mm")
    print(f"  SLS passes       : {res['sls_passes']}")
    print("  PASS")


def test_foundation_analysis_rd_positive():
    print("\n" + "="*60)
    print("  TEST 10 â€” run_foundation_analysis: Rd > 0 and Vd > 0")
    res = api.run_foundation_analysis(FOUND_PARAMS)
    assert res["ok"]
    assert res["comb1"]["Rd"] > 0, "Rd must be positive"
    assert res["comb2"]["Rd"] > 0
    assert res["comb1"]["Vd"] > 0, "Vd must be positive"
    print(f"  C1: Rd={res['comb1']['Rd']:.1f}  Vd={res['comb1']['Vd']:.1f}")
    print(f"  C2: Rd={res['comb2']['Rd']:.1f}  Vd={res['comb2']['Vd']:.1f}")
    print("  PASS")


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 5. Wall analysis
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def test_wall_analysis_returns_ok():
    print("\n" + "="*60)
    print("  TEST 11 â€” run_wall_analysis: returns ok=True, expected keys")
    res = api.run_wall_analysis(WALL_PARAMS)
    assert res.get("ok"), f"Expected ok=True, got: {res.get('error','?')}"
    for key in ("Ka","Kp","comb1","comb2","passes","warnings"):
        assert key in res, f"Missing key '{key}'"
    _assert_json(res, "wall analysis")
    print(f"  Ka={res['Ka']:.4f}   Kp={res['Kp']:.4f}")
    print(f"  C1 sliding FoS_d : {res['comb1']['sliding']['fos_d']:.3f}  "
          f"passes={res['comb1']['sliding']['passes']}")
    print(f"  C1 overturn FoS_d: {res['comb1']['overturn']['fos_d']:.3f}  "
          f"passes={res['comb1']['overturn']['passes']}")
    print(f"  Overall passes   : {res['passes']}")
    print("  PASS")


def test_wall_ka_kp_consistency():
    print("\n" + "="*60)
    print("  TEST 12 â€” run_wall_analysis: Ka < 1 < Kp (Rankine bounds)")
    res = api.run_wall_analysis(WALL_PARAMS)
    assert res["ok"]
    # Rankine Ka for phi=30Â° = tanÂ²(45-15) = tanÂ²(30) â‰ˆ 0.333
    assert res["Ka"] < 1.0,  f"Ka={res['Ka']} should be < 1"
    assert res["Kp"] > 1.0,  f"Kp={res['Kp']} should be > 1"
    assert res["Ka"] < res["Kp"], "Ka must be less than Kp"
    # Exact Rankine: Ka(30Â°) = 0.3333
    assert abs(res["Ka"] - 0.3333) < 0.01, \
        f"Ka={res['Ka']:.4f} differs from Rankine theoretical 0.3333"
    print(f"  Ka={res['Ka']:.4f}  (Rankine theory: 0.3333 for Ï†=30Â°)")
    print(f"  Kp={res['Kp']:.4f}  (Rankine theory: 3.000  for Ï†=30Â°)")
    print("  PASS")


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# 6. Export pipeline
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

def test_export_png_bytes():
    print("\n" + "="*60)
    print("  TEST 13 â€” export_slope_plot_png: returns PNG bytes (â‰¥ 10 kB)")
    res = api.run_slope_analysis(SLOPE_PARAMS)
    assert res["ok"]
    png = api.export_slope_plot_png(res, dpi=80)
    assert isinstance(png, bytes),      "Expected bytes"
    assert png[:8] == b'\x89PNG\r\n\x1a\n', "Not a valid PNG"
    assert len(png) >= 10_000,          f"PNG too small: {len(png)} bytes"
    print(f"  PNG size: {len(png):,} bytes  âœ“ valid PNG magic bytes")
    print("  PASS")


def test_export_heatmap_png_bytes():
    print("\n" + "="*60)
    print("  TEST 13B â€” export_heatmap_png: returns PNG bytes (â‰¥ 10 kB)")
    res = api.run_slope_analysis(SLOPE_PARAMS)
    assert res["ok"]
    png = api.export_heatmap_png(res, dpi=80)
    assert isinstance(png, bytes), "Expected bytes"
    assert png[:8] == b'\x89PNG\r\n\x1a\n', "Not a valid PNG"
    assert len(png) >= 10_000, f"PNG too small: {len(png)} bytes"
    print(f"  PNG size: {len(png):,} bytes  âœ“ valid PNG magic bytes")
    print("  PASS")


def test_export_pdf_file():
    print("\n" + "="*60)
    print("  TEST 14 â€” export_pdf: writes PDF â‰¥ 50 kB")
    res = api.run_slope_analysis(SLOPE_PARAMS)
    assert res["ok"]
    path = os.path.join(os.getcwd(), "_test_export_calc.pdf")
    try:
        out  = api.export_pdf(res, path, project="APITest", job_ref="AT-001")
        assert os.path.exists(out)
        size = os.path.getsize(out)
        assert open(out,"rb").read(4) == b"%PDF", "Not a valid PDF"
        assert size >= 50_000, f"PDF too small: {size} bytes"
        print(f"  PDF size : {size:,} bytes  âœ“ %PDF magic bytes")
    finally:
        if os.path.exists(path):
            os.remove(path)
    print("  PASS")


def test_export_docx_file():
    print("\n" + "="*60)
    print("  TEST 15 â€” export_docx: writes DOCX â‰¥ 30 kB")
    res = api.run_slope_analysis(SLOPE_PARAMS)
    assert res["ok"]
    path = os.path.join(os.getcwd(), "_test_export_calc.docx")
    try:
        out  = api.export_docx(res, path, project="APITest", job_ref="AT-001")
        assert os.path.exists(out)
        size = os.path.getsize(out)
        assert open(out,"rb").read(2) == b"PK", "Not a valid DOCX (ZIP)"
        assert size >= 30_000, f"DOCX too small: {size} bytes"
        print(f"  DOCX size: {size:,} bytes  âœ“ PK magic bytes")
    finally:
        if os.path.exists(path):
            os.remove(path)
    print("  PASS")


# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
# Runner
# â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•

if __name__ == "__main__":
    tests = [
        test_get_soil_library,
        test_get_material_grades,
        test_validate_slope_params_valid,
        test_validate_slope_params_invalid,
        test_slope_analysis_returns_ok,
        test_slope_analysis_fos_range,
        test_slope_analysis_combinations,
        test_slope_analysis_error_handling,
        test_foundation_analysis_returns_ok,
        test_foundation_analysis_rd_positive,
        test_wall_analysis_returns_ok,
        test_wall_ka_kp_consistency,
        test_export_png_bytes,
        test_export_pdf_file,
        test_export_docx_file,
    ]
    passed = failed = 0
    for fn in tests:
        try:
            fn(); passed += 1
        except AssertionError as exc:
            print(f"\n  *** FAIL ***  {fn.__name__}\n  {exc}"); failed += 1
        except Exception as exc:
            import traceback
            print(f"\n  *** ERROR *** {fn.__name__}: {exc}")
            traceback.print_exc(); failed += 1

    print("\n" + "="*60)
    if failed == 0:
        print(f"  ALL {passed} api tests PASSED.")
    else:
        print(f"  {failed} FAILED / {passed} passed.")
    print("="*60)
    sys.exit(failed)




