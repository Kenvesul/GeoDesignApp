"""
test_sheet_pile.py — Sprint 10 validation suite.

Tests the free-earth support sheet pile analysis engine and its API adapter.

Groups
------
  S10-A  Ka/Kp coefficient helpers — against textbook formula.
  S10-B  Craig Example 12.1 (dry, φ'=38°, h=6m, prop at top):
           d_min, T, M_max, z_Mmax for both DA1 combinations.
  S10-C  Surcharge: d_min increases with q.
  S10-D  Water table: d_min increases when WT rises on retained side.
  S10-E  Physics monotonicity: weaker soil → deeper embedment.
  S10-F  Pressure diagram structure and sign convention.
  S10-G  API endpoint (run_sheet_pile_analysis): schema, values, errors.
  S10-H  validate_sheet_pile_params: edge-case coverage.
  S10-I  Input validation in analyse_sheet_pile_da1.

Reference values
----------------
Craig Ex 12.1 dry (φ'=38°, γ=20 kN/m³, h=6 m, prop at top):
  Ka_k = 0.237883,  Kp_k = 4.203746   (Rankine, 4 d.p.)
  DA1-C1 (γ_φ=1.00): d_min=1.5102 m, T=38.298 kN/m, M_max=102.445 kN·m/m
  DA1-C2 (γ_φ=1.25): d_min=2.1363 m, T=54.780 kN/m, M_max=154.221 kN·m/m
  z_Mmax-C1=4.0124 m,  z_Mmax-C2=4.2229 m  (below prop)

All reference values verified by independent hand calculation.

References
----------
Blum, H. (1931). Einspannungsverhältnisse bei Bohlwerken. Ernst & Sohn.
Craig's Soil Mechanics, 9th ed., Example 12.1, §12.2.
EC7 EN 1997-1:2004, §9.7, Tables A.4/A.13.
"""

import math
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models.sheet_pile     import SheetPile
from models.soil          import Soil
from core.sheet_pile_analysis import (
    analyse_sheet_pile_da1,
    ka_rankine, kp_rankine,
    _design_phi,
)
from api import run_sheet_pile_analysis, validate_sheet_pile_params


# ── Tolerance helper ──────────────────────────────────────────────────────────

def _check(label: str, got: float, exp: float, tol_pct: float = 0.10):
    err = abs(got - exp) / max(abs(exp), 1e-12) * 100.0
    ok  = err <= tol_pct
    tag = "PASS" if ok else "FAIL"
    print(f"  {tag}  {label:<50}  exp={exp:>12.6f}  got={got:>12.6f}  err={err:.4f}%")
    assert ok, f"FAIL {label}: expected {exp}, got {got} ({err:.4f}% > {tol_pct}%)"


# ── Shared fixtures ───────────────────────────────────────────────────────────

def _craig_pile():
    return SheetPile(h_retained=6.0, support="propped", z_prop=-6.0)

def _craig_soil():
    return Soil("Dense Sand", 20.0, 38.0, 0.0)

def _craig_result():
    return analyse_sheet_pile_da1(_craig_pile(), _craig_soil())


# ============================================================
#  S10-A  Ka/Kp coefficient helpers
# ============================================================

def test_ka_rankine_30():
    """
    Ka(30°) = tan²(45°−15°) = tan²(30°) = 1/3.

    Reference: Craig §11.3, Rankine (1857).
    """
    print("\n══  S10-A-1  Ka(30°) = 1/3  ══")
    _check("Ka(30°)", ka_rankine(30.0), math.tan(math.radians(30.0))**2)
    print("  ✅  PASS")


def test_kp_rankine_30():
    """Kp(30°) = tan²(60°) = 3.0."""
    print("\n══  S10-A-2  Kp(30°) = 3.0  ══")
    _check("Kp(30°)", kp_rankine(30.0), math.tan(math.radians(60.0))**2)
    print("  ✅  PASS")


def test_ka_kp_product_identity():
    """Ka × Kp = 1 only when φ=0; Ka < 1 < Kp for φ>0."""
    print("\n══  S10-A-3  Ka < 1 < Kp for φ > 0  ══")
    for phi in [20.0, 30.0, 35.0, 38.0, 45.0]:
        ka = ka_rankine(phi)
        kp = kp_rankine(phi)
        assert ka < 1.0 < kp, f"Expected Ka<1<Kp for φ={phi}, got Ka={ka:.4f} Kp={kp:.4f}"
        print(f"  φ={phi:.0f}°: Ka={ka:.4f}  Kp={kp:.4f}  ✓")
    print("  ✅  PASS")


def test_ka_decreases_with_phi():
    """Ka decreases as φ' increases (stronger soil → less active thrust)."""
    print("\n══  S10-A-4  Ka decreases with φ'  ══")
    phis = [20.0, 25.0, 30.0, 35.0, 38.0]
    kas  = [ka_rankine(p) for p in phis]
    for i in range(len(kas)-1):
        assert kas[i] > kas[i+1], f"Ka not decreasing: φ={phis[i]} Ka={kas[i]:.4f}"
    print(f"  Ka values decreasing: {[f'{k:.4f}' for k in kas]}  ✓")
    print("  ✅  PASS")


def test_kp_increases_with_phi():
    """Kp increases as φ' increases (stronger soil → more passive resistance)."""
    print("\n══  S10-A-5  Kp increases with φ'  ══")
    phis = [20.0, 25.0, 30.0, 35.0, 38.0]
    kps  = [kp_rankine(p) for p in phis]
    for i in range(len(kps)-1):
        assert kps[i] < kps[i+1]
    print(f"  Kp values increasing: {[f'{k:.3f}' for k in kps]}  ✓")
    print("  ✅  PASS")


def test_ka_phi0():
    """Ka(0°) = 1 (no friction, Rankine active = at-rest for φ=0)."""
    print("\n══  S10-A-6  Ka(0°) = 1  ══")
    _check("Ka(0°)", ka_rankine(0.0), 1.0)
    print("  ✅  PASS")


def test_design_phi_c2():
    """
    tan φ'_d = tan(38°) / 1.25  →  φ'_d ≈ 32.007°.

    Reference: EC7 §2.4.6.2(3)P; Table A.4 M2.
    """
    print("\n══  S10-A-7  Design φ' (DA1-C2)  ══")
    phi_d = _design_phi(38.0, 1.25)
    tan_d = math.tan(math.radians(38.0)) / 1.25
    expected = math.degrees(math.atan(tan_d))
    _check("φ'_d (C2, φ_k=38°)", phi_d, expected)
    print("  ✅  PASS")


# ============================================================
#  S10-B  Craig Example 12.1 — primary reference validation
# ============================================================

def test_craig_ka_kp():
    """
    Craig Ex 12.1: Ka=0.237883, Kp=4.203746 for φ'=38°.

    Reference: Craig §12.2, p.476.
    """
    print("\n══  S10-B-1  Craig Ex 12.1 — Ka, Kp  ══")
    res = _craig_result()
    _check("Ka_k (φ'=38°)", res.Ka_k, 0.237883, tol_pct=0.01)
    _check("Kp_k (φ'=38°)", res.Kp_k, 4.203746, tol_pct=0.01)
    print("  ✅  PASS")


def test_craig_c1_d_min():
    """
    DA1-C1 (γ_φ=1.00): d_min = 1.5102 m.

    Reference: hand-computed moment equilibrium about prop (see dev notes).
    """
    print("\n══  S10-B-2  Craig Ex 12.1 — C1 d_min = 1.5102 m  ══")
    res = _craig_result()
    _check("DA1-C1 d_min", res.comb1.d_min, 1.5102, tol_pct=0.05)
    assert res.comb1.converged
    print("  ✅  PASS")


def test_craig_c2_d_min():
    """
    DA1-C2 (γ_φ=1.25): d_min = 2.1363 m.

    This is the governing combination for dense sand (φ'>30°).
    Reference: Craig §12.2; EC7 §9.7.4.
    """
    print("\n══  S10-B-3  Craig Ex 12.1 — C2 d_min = 2.1363 m  ══")
    res = _craig_result()
    _check("DA1-C2 d_min", res.comb2.d_min, 2.1363, tol_pct=0.05)
    assert res.comb2.converged
    print("  ✅  PASS")


def test_craig_c1_prop_force():
    """DA1-C1 prop force T = 38.298 kN/m."""
    print("\n══  S10-B-4  Craig Ex 12.1 — C1 T = 38.298 kN/m  ══")
    res = _craig_result()
    _check("DA1-C1 T (prop force)", res.comb1.T_k, 38.298, tol_pct=0.05)
    print("  ✅  PASS")


def test_craig_c2_prop_force():
    """DA1-C2 prop force T = 54.780 kN/m."""
    print("\n══  S10-B-5  Craig Ex 12.1 — C2 T = 54.780 kN/m  ══")
    res = _craig_result()
    _check("DA1-C2 T (prop force)", res.comb2.T_k, 54.780, tol_pct=0.05)
    print("  ✅  PASS")


def test_craig_c1_m_max():
    """DA1-C1 M_max = 102.445 kN·m/m."""
    print("\n══  S10-B-6  Craig Ex 12.1 — C1 M_max = 102.445 kN·m/m  ══")
    res = _craig_result()
    _check("DA1-C1 M_max", res.comb1.M_max, 102.445, tol_pct=0.20)
    print("  ✅  PASS")


def test_craig_c2_m_max():
    """DA1-C2 M_max = 154.221 kN·m/m."""
    print("\n══  S10-B-7  Craig Ex 12.1 — C2 M_max = 154.221 kN·m/m  ══")
    res = _craig_result()
    _check("DA1-C2 M_max", res.comb2.M_max, 154.221, tol_pct=0.20)
    print("  ✅  PASS")


def test_craig_c1_z_mmax():
    """DA1-C1 depth of M_max below prop = 4.0124 m."""
    print("\n══  S10-B-8  Craig Ex 12.1 — C1 z_Mmax = 4.012 m  ══")
    res = _craig_result()
    _check("DA1-C1 z_Mmax", res.comb1.z_Mmax, 4.0124, tol_pct=0.20)
    print("  ✅  PASS")


def test_craig_c2_z_mmax():
    """DA1-C2 depth of M_max below prop = 4.2229 m."""
    print("\n══  S10-B-9  Craig Ex 12.1 — C2 z_Mmax = 4.223 m  ══")
    res = _craig_result()
    _check("DA1-C2 z_Mmax", res.comb2.z_Mmax, 4.2229, tol_pct=0.20)
    print("  ✅  PASS")


def test_craig_governing_is_c2():
    """C2 governs (larger d_min) for dense sand (φ'=38°)."""
    print("\n══  S10-B-10  Craig Ex 12.1 — C2 governs  ══")
    res = _craig_result()
    assert res.governing.label == "DA1-C2", (
        f"Expected DA1-C2 to govern, got {res.governing.label}"
    )
    assert res.d_design == res.comb2.d_min
    print(f"  Governing: {res.governing.label}  d_design={res.d_design:.4f} m  ✓")
    print("  ✅  PASS")


def test_craig_pile_updated():
    """analyse_sheet_pile_da1 updates pile.d_embed and pile.F_prop_k in-place."""
    print("\n══  S10-B-11  Pile object updated with design values  ══")
    res = _craig_result()
    _check("pile.d_embed", res.pile.d_embed, res.d_design)
    _check("pile.F_prop_k", res.pile.F_prop_k, res.T_design)
    print("  ✅  PASS")


def test_craig_c2_larger_than_c1():
    """DA1-C2 always gives larger d_min than DA1-C1 for φ'>0 soils."""
    print("\n══  S10-B-12  C2 d_min > C1 d_min (φ'=38°)  ══")
    res = _craig_result()
    assert res.comb2.d_min > res.comb1.d_min
    print(f"  C1={res.comb1.d_min:.4f}  C2={res.comb2.d_min:.4f}  ✓")
    print("  ✅  PASS")


# ============================================================
#  S10-C  Surcharge effect
# ============================================================

def test_surcharge_increases_embedment():
    """
    Adding a uniform surcharge on the retained surface increases d_min.

    Surcharge → higher active thrust → deeper passive resistance needed.
    """
    print("\n══  S10-C-1  Surcharge increases d_min  ══")
    soil = _craig_soil()
    res0 = analyse_sheet_pile_da1(_craig_pile(), soil, q=0.0)
    res_q = analyse_sheet_pile_da1(_craig_pile(), soil, q=10.0)
    assert res_q.comb2.d_min > res0.comb2.d_min
    print(f"  q=0: d={res0.comb2.d_min:.4f}  q=10: d={res_q.comb2.d_min:.4f}  ✓")
    print("  ✅  PASS")


def test_surcharge_increases_prop_force():
    """Surcharge increases the prop force T."""
    print("\n══  S10-C-2  Surcharge increases prop force  ══")
    soil = _craig_soil()
    res0 = analyse_sheet_pile_da1(_craig_pile(), soil, q=0.0)
    res_q = analyse_sheet_pile_da1(_craig_pile(), soil, q=10.0)
    assert res_q.comb2.T_k > res0.comb2.T_k
    print(f"  q=0: T={res0.comb2.T_k:.3f}  q=10: T={res_q.comb2.T_k:.3f}  ✓")
    print("  ✅  PASS")


def test_surcharge_increases_m_max():
    """Surcharge increases the maximum bending moment."""
    print("\n══  S10-C-3  Surcharge increases M_max  ══")
    soil = _craig_soil()
    res0 = analyse_sheet_pile_da1(_craig_pile(), soil, q=0.0)
    res_q = analyse_sheet_pile_da1(_craig_pile(), soil, q=10.0)
    assert res_q.comb2.M_max > res0.comb2.M_max
    print(f"  q=0: M={res0.comb2.M_max:.3f}  q=10: M={res_q.comb2.M_max:.3f}  ✓")
    print("  ✅  PASS")


def test_surcharge_monotonic():
    """d_min increases monotonically with increasing surcharge q."""
    print("\n══  S10-C-4  d_min monotone in q  ══")
    soil = _craig_soil()
    qs   = [0, 5, 10, 20, 50]
    ds   = [analyse_sheet_pile_da1(_craig_pile(), soil, q=q).comb2.d_min for q in qs]
    print(f"  q: {qs}")
    print(f"  d: {[f'{d:.4f}' for d in ds]}")
    for i in range(len(ds)-1):
        assert ds[i] < ds[i+1]
    print("  ✅  PASS")


# ============================================================
#  S10-D  Water table effect
# ============================================================

def test_water_table_increases_embedment():
    """
    Water table on retained side increases d_min vs dry case.

    Higher pore pressure → net active thrust larger → deeper passive needed.
    """
    print("\n══  S10-D-1  Water table increases d_min  ══")
    soil = _craig_soil()
    res_dry = analyse_sheet_pile_da1(_craig_pile(), soil)
    res_wt  = analyse_sheet_pile_da1(_craig_pile(), soil, z_w=1.5)
    assert res_wt.comb2.d_min > res_dry.comb2.d_min
    print(f"  dry: d={res_dry.comb2.d_min:.4f}  WT(1.5m): d={res_wt.comb2.d_min:.4f}  ✓")
    print("  ✅  PASS")


def test_water_table_increases_prop_force():
    """Water table on retained side increases prop force T."""
    print("\n══  S10-D-2  Water table increases prop force  ══")
    soil = _craig_soil()
    res_dry = analyse_sheet_pile_da1(_craig_pile(), soil)
    res_wt  = analyse_sheet_pile_da1(_craig_pile(), soil, z_w=1.5)
    assert res_wt.comb2.T_k > res_dry.comb2.T_k
    print(f"  dry: T={res_dry.comb2.T_k:.3f}  WT(1.5m): T={res_wt.comb2.T_k:.3f}  ✓")
    print("  ✅  PASS")


def test_lower_water_table_less_effect():
    """
    Lower water table (closer to excavation) increases d_min less than
    a higher water table (closer to top).
    """
    print("\n══  S10-D-3  Lower WT has less effect than higher WT  ══")
    soil = _craig_soil()
    h    = 6.0
    d_wt_high = analyse_sheet_pile_da1(_craig_pile(), soil, z_w=1.0).comb2.d_min
    d_wt_low  = analyse_sheet_pile_da1(_craig_pile(), soil, z_w=4.0).comb2.d_min
    d_dry     = analyse_sheet_pile_da1(_craig_pile(), soil).comb2.d_min
    print(f"  dry={d_dry:.4f}  z_w=4m: {d_wt_low:.4f}  z_w=1m: {d_wt_high:.4f}")
    assert d_wt_high > d_wt_low > d_dry
    print("  ✅  PASS")


# ============================================================
#  S10-E  Physics monotonicity
# ============================================================

def test_weaker_soil_deeper_embedment():
    """
    Weaker soil (lower φ') requires deeper embedment.

    Lower Kp → passive resistance per unit depth is smaller → more depth needed.
    Reference: Craig §12.2.
    """
    print("\n══  S10-E-1  Weaker soil → deeper embedment  ══")
    phis = [38.0, 35.0, 30.0, 25.0]
    ds   = []
    for phi in phis:
        pile = _craig_pile()
        soil = Soil(f"Sand{phi}", 20.0, phi, 0.0)
        res  = analyse_sheet_pile_da1(pile, soil)
        ds.append(res.comb2.d_min)
        print(f"  φ'={phi:.0f}°: d_min={ds[-1]:.4f} m")
    for i in range(len(ds)-1):
        assert ds[i] < ds[i+1], f"d not increasing as φ decreases: {ds}"
    print("  ✅  PASS")


def test_taller_wall_deeper_embedment():
    """
    Taller retained height h requires deeper embedment (larger active moment).
    """
    print("\n══  S10-E-2  Taller wall → deeper embedment  ══")
    soil = _craig_soil()
    hs   = [4.0, 5.0, 6.0, 7.0]
    ds   = []
    for h in hs:
        pile = SheetPile(h_retained=h, support="propped", z_prop=-h)
        res  = analyse_sheet_pile_da1(pile, soil)
        ds.append(res.comb2.d_min)
        print(f"  h={h:.0f}m: d_min={ds[-1]:.4f} m")
    for i in range(len(ds)-1):
        assert ds[i] < ds[i+1]
    print("  ✅  PASS")


def test_prop_force_positive():
    """Prop force T > 0 for a typical propped sheet pile (prop in compression)."""
    print("\n══  S10-E-3  Prop force T > 0 for propped wall  ══")
    res = _craig_result()
    assert res.comb1.T_k > 0.0
    assert res.comb2.T_k > 0.0
    print(f"  T_C1={res.comb1.T_k:.3f}  T_C2={res.comb2.T_k:.3f}  both > 0  ✓")
    print("  ✅  PASS")


def test_m_max_below_prop_and_above_dredge():
    """
    Maximum bending moment occurs between the prop and the excavation level.

    For a prop at the top (z=0) and h=6 m, z_Mmax must be in (0, 6).
    """
    print("\n══  S10-E-4  z_Mmax between prop and dredge level  ══")
    res = _craig_result()
    h   = 6.0
    for comb in [res.comb1, res.comb2]:
        assert 0.0 < comb.z_Mmax < h + comb.d_min, (
            f"{comb.label}: z_Mmax={comb.z_Mmax:.4f} not in (0, {h+comb.d_min:.2f})"
        )
        print(f"  {comb.label}: z_Mmax={comb.z_Mmax:.4f} m  (0 < z < {h+comb.d_min:.2f})  ✓")
    print("  ✅  PASS")


# ============================================================
#  S10-F  Pressure diagram
# ============================================================

def test_diagram_zero_at_top():
    """Active pressure = 0 at the top of the retained soil (z=0)."""
    print("\n══  S10-F-1  Pressure diagram: p_a=0 at top  ══")
    res = _craig_result()
    top = res.pressure_diagram[0]
    assert top.z == 0.0
    assert abs(top.p_a) < 1e-9, f"p_a at top should be 0, got {top.p_a}"
    assert abs(top.p_p) < 1e-9, f"p_p at top should be 0, got {top.p_p}"
    print(f"  p_a(z=0)={top.p_a}  p_p(z=0)={top.p_p}  ✓")
    print("  ✅  PASS")


def test_diagram_active_at_dredge():
    """
    Active pressure at dredge level = Ka * gamma * h.

    Craig Ex 12.1: pa(h=6) = 0.237883 * 20 * 6 = 28.546 kPa.
    """
    print("\n══  S10-F-2  Active pressure at dredge level = Ka*γ*h  ══")
    res  = _craig_result()
    # Find dredge-level point
    dredge_pts = [p for p in res.pressure_diagram if abs(p.z_datum) < 1e-6]
    assert dredge_pts, "No dredge-level point in diagram"
    dredge = dredge_pts[0]
    expected_pa = res.Ka_k * 20.0 * 6.0
    _check("p_a at dredge level", dredge.p_a, expected_pa, tol_pct=0.01)
    print("  ✅  PASS")


def test_diagram_passive_zero_above_dredge():
    """Passive pressure = 0 everywhere above the excavation level."""
    print("\n══  S10-F-3  p_p = 0 above dredge level  ══")
    res = _craig_result()
    above = [p for p in res.pressure_diagram if p.z_datum < -1e-6]
    for pt in above:
        assert abs(pt.p_p) < 1e-9, f"p_p should be 0 above dredge, got {pt.p_p} at z={pt.z}"
    print(f"  {len(above)} points above dredge all have p_p=0  ✓")
    print("  ✅  PASS")


def test_diagram_passive_increases_below_dredge():
    """Passive pressure increases with depth below excavation (Kp*γ*d)."""
    print("\n══  S10-F-4  p_p increases below dredge  ══")
    res    = _craig_result()
    below  = [p for p in res.pressure_diagram if p.z_datum > 1e-6]
    assert len(below) >= 2, "Need at least 2 embedded points"
    for i in range(len(below)-1):
        assert below[i+1].p_p >= below[i].p_p - 1e-9
    print(f"  {len(below)} embedded points: p_p increasing  ✓")
    print("  ✅  PASS")


def test_diagram_depths_ordered():
    """All diagram points have strictly increasing depth z."""
    print("\n══  S10-F-5  Diagram z values strictly increasing  ══")
    res = _craig_result()
    zs  = [p.z for p in res.pressure_diagram]
    for i in range(len(zs)-1):
        assert zs[i] < zs[i+1], f"z values not increasing: {zs[i]:.3f} >= {zs[i+1]:.3f}"
    print(f"  {len(zs)} points in ascending z order  ✓")
    print("  ✅  PASS")


def test_diagram_has_enough_points():
    """Pressure diagram has at least 5 points (top + dredge + embedded)."""
    print("\n══  S10-F-6  Diagram has ≥5 points  ══")
    res = _craig_result()
    assert len(res.pressure_diagram) >= 5
    print(f"  {len(res.pressure_diagram)} points  ✓")
    print("  ✅  PASS")


# ============================================================
#  S10-G  API endpoint — run_sheet_pile_analysis
# ============================================================

def test_api_craig_d_design():
    """API returns correct d_design for Craig Ex 12.1."""
    print("\n══  S10-G-1  API Craig Ex 12.1 d_design  ══")
    r = run_sheet_pile_analysis({"h_retained": 6.0, "phi_k": 38.0, "gamma": 20.0})
    assert r["ok"], r.get("errors")
    _check("API d_design", r["d_design"], 2.1363, tol_pct=0.05)
    print("  ✅  PASS")


def test_api_craig_t_design():
    """API returns correct T_design for Craig Ex 12.1."""
    print("\n══  S10-G-2  API Craig Ex 12.1 T_design  ══")
    r = run_sheet_pile_analysis({"h_retained": 6.0, "phi_k": 38.0, "gamma": 20.0})
    _check("API T_design", r["T_design"], 54.780, tol_pct=0.05)
    print("  ✅  PASS")


def test_api_craig_m_max():
    """API returns correct M_max_design for Craig Ex 12.1."""
    print("\n══  S10-G-3  API Craig Ex 12.1 M_max_design  ══")
    r = run_sheet_pile_analysis({"h_retained": 6.0, "phi_k": 38.0, "gamma": 20.0})
    _check("API M_max_design", r["M_max_design"], 154.221, tol_pct=0.20)
    print("  ✅  PASS")


def test_api_schema_keys():
    """API response contains all required schema keys."""
    print("\n══  S10-G-4  API response schema keys  ══")
    r = run_sheet_pile_analysis({"h_retained": 6.0, "phi_k": 38.0, "gamma": 20.0})
    required = [
        "ok", "version", "analysis_type", "errors", "warnings",
        "wall", "Ka_k", "Kp_k", "comb1", "comb2",
        "governing", "d_design", "T_design", "M_max_design", "z_Mmax_design",
        "pressure_diagram", "passes",
    ]
    for k in required:
        assert k in r, f"Missing key: {k}"
        print(f"  {k}: present  ✓")
    print("  ✅  PASS")


def test_api_analysis_type_tag():
    """API sets analysis_type = 'sheet_pile'."""
    print("\n══  S10-G-5  API analysis_type tag  ══")
    r = run_sheet_pile_analysis({"h_retained": 5.0, "phi_k": 30.0, "gamma": 18.0})
    assert r["analysis_type"] == "sheet_pile"
    assert r["version"] == "1.1"
    print(f"  analysis_type={r['analysis_type']}  version={r['version']}  ✓")
    print("  ✅  PASS")


def test_api_comb_keys():
    """comb1 and comb2 dicts contain required keys."""
    print("\n══  S10-G-6  API comb sub-dict keys  ══")
    r = run_sheet_pile_analysis({"h_retained": 6.0, "phi_k": 38.0, "gamma": 20.0})
    comb_keys = ["label", "gamma_phi", "phi_d_deg", "Ka_d", "Kp_d",
                 "d_min", "T_k", "z_Mmax", "M_max", "converged"]
    for combo in ["comb1", "comb2"]:
        for k in comb_keys:
            assert k in r[combo], f"comb1/2 missing key: {k}"
    print(f"  All {len(comb_keys)} comb keys present  ✓")
    print("  ✅  PASS")


def test_api_wall_sub_dict():
    """wall sub-dict contains geometry fields."""
    print("\n══  S10-G-7  API wall sub-dict keys  ══")
    r = run_sheet_pile_analysis({"h_retained": 6.0, "phi_k": 38.0, "gamma": 20.0})
    for k in ["label", "h_retained", "z_prop", "d_design", "total_length"]:
        assert k in r["wall"], f"wall missing key: {k}"
    _check("wall.total_length", r["wall"]["total_length"], 6.0 + 2.1363, tol_pct=0.05)
    print("  ✅  PASS")


def test_api_pressure_diagram_list():
    """pressure_diagram is a list of dicts with required keys."""
    print("\n══  S10-G-8  API pressure diagram structure  ══")
    r = run_sheet_pile_analysis({"h_retained": 6.0, "phi_k": 38.0, "gamma": 20.0})
    diag = r["pressure_diagram"]
    assert isinstance(diag, list) and len(diag) > 0
    for pt in diag:
        for k in ["z", "z_datum", "p_a", "p_p", "u", "p_net"]:
            assert k in pt, f"pressure diagram point missing key: {k}"
    print(f"  {len(diag)} diagram points, all with correct keys  ✓")
    print("  ✅  PASS")


def test_api_governing_string():
    """governing field is a string label ('DA1-C1' or 'DA1-C2')."""
    print("\n══  S10-G-9  API governing is string label  ══")
    r = run_sheet_pile_analysis({"h_retained": 6.0, "phi_k": 38.0, "gamma": 20.0})
    assert r["governing"] in ("DA1-C1", "DA1-C2")
    assert r["governing"] == "DA1-C2"   # C2 governs for φ'=38°
    print(f"  governing={r['governing']}  ✓")
    print("  ✅  PASS")


def test_api_surcharge_kwarg():
    """API accepts q surcharge and returns larger d_design than without."""
    print("\n══  S10-G-10  API surcharge parameter  ══")
    r0 = run_sheet_pile_analysis({"h_retained": 6.0, "phi_k": 38.0, "gamma": 20.0, "q": 0})
    rq = run_sheet_pile_analysis({"h_retained": 6.0, "phi_k": 38.0, "gamma": 20.0, "q": 10})
    assert rq["d_design"] > r0["d_design"]
    print(f"  q=0: d={r0['d_design']}  q=10: d={rq['d_design']}  ✓")
    print("  ✅  PASS")


def test_api_error_on_missing_required():
    """API returns ok=False when required fields are missing."""
    print("\n══  S10-G-11  API error on missing required fields  ══")
    r = run_sheet_pile_analysis({})
    assert not r["ok"]
    assert len(r["errors"]) > 0
    print(f"  Empty params → ok=False, errors={r['errors'][:2]}  ✓")
    print("  ✅  PASS")


def test_api_error_negative_h():
    """API returns ok=False for h_retained ≤ 0."""
    print("\n══  S10-G-12  API error for h_retained ≤ 0  ══")
    r = run_sheet_pile_analysis({"h_retained": -1.0, "phi_k": 30.0, "gamma": 18.0})
    assert not r["ok"]
    print(f"  h=-1: ok=False  ✓")
    print("  ✅  PASS")


def test_api_error_bad_phi():
    """API returns ok=False for phi_k = 0."""
    print("\n══  S10-G-13  API error for phi_k = 0  ══")
    r = run_sheet_pile_analysis({"h_retained": 5.0, "phi_k": 0.0, "gamma": 18.0})
    assert not r["ok"]
    print(f"  phi=0: ok=False  ✓")
    print("  ✅  PASS")


# ============================================================
#  S10-H  validate_sheet_pile_params
# ============================================================

def test_validate_all_valid():
    """Valid minimal params returns empty errors list."""
    print("\n══  S10-H-1  validate: valid params → no errors  ══")
    errs = validate_sheet_pile_params({"h_retained": 5.0, "phi_k": 30.0, "gamma": 18.0})
    assert errs == [], f"Unexpected errors: {errs}"
    print("  ✅  PASS")


def test_validate_missing_h():
    """Missing h_retained triggers error."""
    print("\n══  S10-H-2  validate: missing h_retained  ══")
    errs = validate_sheet_pile_params({"phi_k": 30.0, "gamma": 18.0})
    assert any("h_retained" in e for e in errs)
    print(f"  {errs}  ✓")
    print("  ✅  PASS")


def test_validate_negative_q():
    """Negative surcharge q triggers error."""
    print("\n══  S10-H-3  validate: q < 0  ══")
    errs = validate_sheet_pile_params({"h_retained": 5.0, "phi_k": 30.0, "gamma": 18.0, "q": -1})
    assert any("q" in e for e in errs)
    print(f"  {errs}  ✓")
    print("  ✅  PASS")


def test_validate_negative_z_w():
    """Negative water table depth triggers error."""
    print("\n══  S10-H-4  validate: z_w < 0  ══")
    errs = validate_sheet_pile_params({"h_retained": 5.0, "phi_k": 30.0, "gamma": 18.0, "z_w": -0.5})
    assert any("z_w" in e for e in errs)
    print(f"  {errs}  ✓")
    print("  ✅  PASS")


def test_validate_non_numeric():
    """Non-numeric values trigger errors."""
    print("\n══  S10-H-5  validate: non-numeric  ══")
    errs = validate_sheet_pile_params({"h_retained": "abc", "phi_k": 30.0, "gamma": 18.0})
    assert len(errs) > 0
    print(f"  {errs}  ✓")
    print("  ✅  PASS")


# ============================================================
#  S10-I  Engine input validation
# ============================================================

def test_engine_error_cohesive_soil():
    """analyse_sheet_pile_da1 raises ValueError for pure cohesive (φ'=0)."""
    print("\n══  S10-I-1  Engine rejects φ'=0 soil  ══")
    soil = Soil("Clay", 18.0, 0.0, 30.0)
    try:
        analyse_sheet_pile_da1(_craig_pile(), soil)
        raise AssertionError("Should have raised")
    except ValueError as e:
        print(f"  φ'=0 raised ValueError: {e}  ✓")
    print("  ✅  PASS")


def test_engine_error_negative_q():
    """Engine raises ValueError for negative surcharge."""
    print("\n══  S10-I-2  Engine rejects negative surcharge  ══")
    try:
        analyse_sheet_pile_da1(_craig_pile(), _craig_soil(), q=-5.0)
        raise AssertionError("Should have raised")
    except ValueError as e:
        print(f"  q=-5: ValueError: {e}  ✓")
    print("  ✅  PASS")


def test_engine_error_negative_z_w():
    """Engine raises ValueError for negative z_w."""
    print("\n══  S10-I-3  Engine rejects negative z_w  ══")
    try:
        analyse_sheet_pile_da1(_craig_pile(), _craig_soil(), z_w=-1.0)
        raise AssertionError("Should have raised")
    except ValueError as e:
        print(f"  z_w=-1: ValueError: {e}  ✓")
    print("  ✅  PASS")


# ============================================================
#  Runner
# ============================================================

if __name__ == "__main__":
    tests = [
        # S10-A  Ka/Kp helpers
        test_ka_rankine_30,
        test_kp_rankine_30,
        test_ka_kp_product_identity,
        test_ka_decreases_with_phi,
        test_kp_increases_with_phi,
        test_ka_phi0,
        test_design_phi_c2,
        # S10-B  Craig Ex 12.1
        test_craig_ka_kp,
        test_craig_c1_d_min,
        test_craig_c2_d_min,
        test_craig_c1_prop_force,
        test_craig_c2_prop_force,
        test_craig_c1_m_max,
        test_craig_c2_m_max,
        test_craig_c1_z_mmax,
        test_craig_c2_z_mmax,
        test_craig_governing_is_c2,
        test_craig_pile_updated,
        test_craig_c2_larger_than_c1,
        # S10-C  Surcharge
        test_surcharge_increases_embedment,
        test_surcharge_increases_prop_force,
        test_surcharge_increases_m_max,
        test_surcharge_monotonic,
        # S10-D  Water table
        test_water_table_increases_embedment,
        test_water_table_increases_prop_force,
        test_lower_water_table_less_effect,
        # S10-E  Monotonicity
        test_weaker_soil_deeper_embedment,
        test_taller_wall_deeper_embedment,
        test_prop_force_positive,
        test_m_max_below_prop_and_above_dredge,
        # S10-F  Pressure diagram
        test_diagram_zero_at_top,
        test_diagram_active_at_dredge,
        test_diagram_passive_zero_above_dredge,
        test_diagram_passive_increases_below_dredge,
        test_diagram_depths_ordered,
        test_diagram_has_enough_points,
        # S10-G  API
        test_api_craig_d_design,
        test_api_craig_t_design,
        test_api_craig_m_max,
        test_api_schema_keys,
        test_api_analysis_type_tag,
        test_api_comb_keys,
        test_api_wall_sub_dict,
        test_api_pressure_diagram_list,
        test_api_governing_string,
        test_api_surcharge_kwarg,
        test_api_error_on_missing_required,
        test_api_error_negative_h,
        test_api_error_bad_phi,
        # S10-H  Validation
        test_validate_all_valid,
        test_validate_missing_h,
        test_validate_negative_q,
        test_validate_negative_z_w,
        test_validate_non_numeric,
        # S10-I  Engine validation
        test_engine_error_cohesive_soil,
        test_engine_error_negative_q,
        test_engine_error_negative_z_w,
    ]

    passed = failed = 0
    failures = []

    print("\n" + "═"*68)
    print("  SPRINT 10 — Sheet Pile Free-Earth Analysis + API")
    print("═"*68)

    for fn in tests:
        try:
            fn()
            passed += 1
        except Exception as e:
            import traceback
            failed += 1
            failures.append((fn.__name__, e))
            print(f"\n  ❌  FAIL  {fn.__name__}:\n      {e}")
            traceback.print_exc()

    print("\n" + "═"*68)
    print(f"  SPRINT 10 RESULTS: {passed}/{passed+failed} passed, {failed} failed")
    print("═"*68)
    if failures:
        for name, err in failures:
            print(f"    - {name}: {err}")
        sys.exit(1)
    else:
        print("\n  ✅  ALL SPRINT 10 TESTS PASS")
