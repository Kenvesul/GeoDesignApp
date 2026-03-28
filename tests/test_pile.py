"""
test_pile.py – Sprint 7 validation suite.

Covers:
    P7-A  pile.py  — Pile + PileSoilLayer geometry, validation, derived properties.
    P7-B  pile_capacity.py — EC7 factor constants; alpha (Tomlinson 1970) and
          Nq (Meyerhof 1976) helper functions.
    P7-C  pile_capacity.py — Clay pile characteristic capacity (alpha method +
          Skempton Nc=9 base).  Textbook reference values.
    P7-D  pile_capacity.py — Sand pile characteristic capacity (beta method +
          Meyerhof Nq base).  Textbook reference values.
    P7-E  pile_capacity.py — Multi-layer pile (clay over sand).
    P7-F  pile_capacity.py — Bored pile: base reduction factor 0.5.
    P7-G  pile_capacity.py — DA1 ULS verification: Combination 1 & 2 factors,
          pass/fail logic, governing combination.
    P7-H  Monotonicity and physics checks.
    P7-I  Edge cases and invalid-input validation.

Reference values:
    All expected values computed from first-principles using the formulae
    documented in pile_capacity.py and independently verified against:
        EC7 EN 1997-1:2004, §7.6.2 (pile capacity), Tables A.6/A.7.
        Craig's Soil Mechanics, 9th ed., §11.
        Das, B.M. (2019). Principles of Foundation Engineering, §11.4.
        Meyerhof, G.G. (1976). Bearing Capacity and Settlement of Pile Foundations.
        Tomlinson, M.J. (1970). Adhesion of Piles Driven in Clay.
        Skempton, A.W. (1951). The Bearing Capacity of Clays.
"""

import math
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models.pile import Pile, PileSoilLayer, GAMMA_CONCRETE, _VALID_PILE_TYPES, _VALID_MATERIALS
from core.pile_capacity import (
    verify_pile_da1,
    characteristic_pile_capacity,
    _alpha_tomlinson,
    _nq_meyerhof,
    # EC7 DA1 factor constants
    C1_G_UNFAV, C1_Q, C1_PHI,
    C2_G_UNFAV, C2_Q, C2_PHI,
    R1_BASE, R1_SHAFT,
    R4_BASE, R4_SHAFT,
    K_S_DEFAULT,
    # Result types
    PileResult, PileCombinationResult, LayerCapacityResult,
)

TOL = 0.005   # 0.5% relative tolerance for textbook value comparisons


# ── Helper ───────────────────────────────────────────────────────────────────
def _pct(got, exp):
    return abs(got - exp) / max(abs(exp), 1e-12) * 100.0


def _check(label, got, exp, tol_pct=0.5):
    err = _pct(got, exp)
    ok  = err <= tol_pct
    tag = "PASS" if ok else "FAIL"
    print(f"  {tag}  {label:<38}  expected={exp:>10.4f}  got={got:>10.4f}  err={err:.3f}%")
    assert ok, f"FAIL {label}: expected {exp:.4f}, got {got:.4f} ({err:.3f}% > {tol_pct}%)"


# ============================================================
#  P7-A  pile.py – Model and geometry
# ============================================================

def test_pile_types_accepted():
    """All valid pile types and materials accepted without error."""
    print("\n══  P7-A-1  All valid pile types accepted  ══")
    for ptype in ('driven', 'bored', 'CFA'):
        for mat in ('concrete', 'steel'):
            p = Pile(ptype, 0.5, 10.0, material=mat)
            assert p.pile_type == ptype
            assert p.material  == mat
            print(f"  {ptype}/{mat}  ✓")
    print("  ✅  PASS")


def test_pile_derived_geometry():
    """
    Derived properties: perimeter, area_base, area_shaft, self_weight.

    For D=0.5m, L=15m, γ_c=24 kN/m³:
        perimeter   = π × 0.5 = 1.5708 m
        area_base   = π/4 × 0.25 = 0.19635 m²
        shaft_area  = 1.5708 × 15 = 23.562 m²
        self_weight = 0.19635 × 15 × 24 = 70.69 kN

    Reference: EC7 §7.5.1 (pile self-weight in characteristic permanent action).
    """
    print("\n══  P7-A-2  Pile derived geometry  ══")
    D, L = 0.5, 15.0
    p = Pile('driven', D, L)
    _check("perimeter (m)",         p.perimeter,   math.pi * D)
    _check("area_base (m²)",        p.area_base,   math.pi / 4.0 * D**2)
    _check("shaft_area (m²)",       p.shaft_area,  math.pi * D * L)
    _check("self_weight (kN)",      p.self_weight,
           GAMMA_CONCRETE * math.pi / 4 * D**2 * L)
    print("  ✅  PASS")


def test_pile_slenderness():
    """Slenderness L/D computed correctly; check L/D < 4 still accepted (warning in engine)."""
    print("\n══  P7-A-3  Pile slenderness  ══")
    p = Pile('driven', 0.4, 12.0)
    assert abs(p.slenderness - 30.0) < 1e-9
    p_squat = Pile('bored', 0.6, 1.5)   # L/D = 2.5 — valid model, engine warns
    assert abs(p_squat.slenderness - 2.5) < 1e-9
    print(f"  L/D=30: {p.slenderness}  ✓")
    print(f"  L/D=2.5 (squat): {p_squat.slenderness}  ✓ (engine warns)")
    print("  ✅  PASS")


def test_pile_invalid_params():
    """Invalid inputs raise ValueError with descriptive messages."""
    print("\n══  P7-A-4  Pile invalid parameter validation  ══")
    cases = [
        ("bad pile_type",   dict(pile_type='gravity',  diameter=0.4, length=10.0)),
        ("diameter <= 0",   dict(pile_type='driven',   diameter=0.0, length=10.0)),
        ("length <= 0",     dict(pile_type='driven',   diameter=0.4, length=0.0)),
        ("bad material",    dict(pile_type='driven',   diameter=0.4, length=10.0, material='timber')),
        ("gamma_c <= 0",    dict(pile_type='driven',   diameter=0.4, length=10.0, gamma_concrete=0.0)),
    ]
    for label, kw in cases:
        try:
            Pile(**kw)
            raise AssertionError(f"Should have raised ValueError for: {label}")
        except ValueError as e:
            print(f"  {label}: raised ValueError ✓")
    print("  ✅  PASS")


def test_pile_soil_layer_validation():
    """PileSoilLayer rejects invalid inputs."""
    print("\n══  P7-A-5  PileSoilLayer validation  ══")
    # Valid clay
    l = PileSoilLayer(5.0, 18.0, 0.0, 50.0, 'clay')
    assert l.thickness == 5.0
    print("  Valid clay layer ✓")
    # Valid sand
    l2 = PileSoilLayer(5.0, 19.0, 32.0, 0.0, 'sand')
    assert l2.soil_type == 'sand'
    print("  Valid sand layer ✓")
    # Invalid
    for label, kw in [
        ("thickness=0",   dict(thickness=0.0, gamma=18.0, phi_k=0.0, c_k=50.0, soil_type='clay')),
        ("gamma=0",       dict(thickness=5.0, gamma=0.0,  phi_k=0.0, c_k=50.0, soil_type='clay')),
        ("bad soil_type", dict(thickness=5.0, gamma=18.0, phi_k=0.0, c_k=50.0, soil_type='gravel')),
        ("sand phi=0",    dict(thickness=5.0, gamma=18.0, phi_k=0.0, c_k=0.0,  soil_type='sand')),
        ("clay c_k=0",    dict(thickness=5.0, gamma=18.0, phi_k=0.0, c_k=0.0,  soil_type='clay')),
    ]:
        try:
            PileSoilLayer(**kw)
            raise AssertionError(f"Should have raised ValueError for: {label}")
        except ValueError:
            print(f"  {label}: raised ValueError ✓")
    print("  ✅  PASS")


# ============================================================
#  P7-B  pile_capacity.py – Factors and helpers
# ============================================================

def test_da1_factor_constants():
    """
    EC7 DA1 factor constants match normative values.

    Reference:
        EN 1997-1:2004, Annex A:
            Table A.3: A1  γ_G=1.35, γ_Q=1.50
            Table A.4: A2  γ_G=1.00, γ_Q=1.30
            Table A.4: M2  γ_φ=1.25
            Table A.6: R1  γ_b=γ_s=1.00 (all pile types)
            Table A.6: R4  driven: γ_b=1.30, γ_s=1.30
                           bored:  γ_b=1.60, γ_s=1.30
                           CFA:    γ_b=1.45, γ_s=1.30
    """
    print("\n══  P7-B-1  EC7 DA1 factor constants  ══")
    assert C1_G_UNFAV == 1.35;  assert C1_Q == 1.50;  assert C1_PHI == 1.00
    assert C2_G_UNFAV == 1.00;  assert C2_Q == 1.30;  assert C2_PHI == 1.25
    assert R1_BASE    == 1.00;  assert R1_SHAFT == 1.00
    # R4 driven
    assert R4_BASE['driven']  == 1.30; assert R4_SHAFT['driven'] == 1.30
    # R4 bored
    assert R4_BASE['bored']   == 1.60; assert R4_SHAFT['bored']  == 1.30
    # R4 CFA
    assert R4_BASE['CFA']     == 1.45; assert R4_SHAFT['CFA']    == 1.30
    print("  A1: γ_G=1.35 γ_Q=1.50  ✓")
    print("  A2: γ_G=1.00 γ_Q=1.30  M2: γ_φ=1.25  ✓")
    print("  R1: γ_b=γ_s=1.00  ✓")
    print("  R4 driven: γ_b=1.30 γ_s=1.30  ✓")
    print("  R4 bored:  γ_b=1.60 γ_s=1.30  ✓")
    print("  R4 CFA:    γ_b=1.45 γ_s=1.30  ✓")
    print("  ✅  PASS")


def test_tomlinson_alpha_breakpoints():
    """
    Tomlinson alpha adhesion factor at key breakpoints.

    Piecewise linear (pile_capacity.py implementation):
        c_u ≤ 25 kPa : α = 1.00
        25 < c_u ≤ 70 : α = 1.00 − 0.50×(c_u−25)/45
        c_u > 70 kPa  : α = 0.50

    Reference: Tomlinson (1970); Das §11.4; Craig §11.1.
    """
    print("\n══  P7-B-2  Tomlinson alpha breakpoints  ══")
    cases = [
        (10.0,  1.0000),
        (25.0,  1.0000),
        (40.0,  1.0000 - 0.50*(40-25)/45),   # = 0.8333
        (60.0,  1.0000 - 0.50*(60-25)/45),   # = 0.6111
        (70.0,  0.5000),
        (80.0,  0.5000),
        (120.0, 0.5000),
    ]
    for cu, exp_alpha in cases:
        got = _alpha_tomlinson(cu)
        _check(f"alpha(cu={cu:.0f} kPa)", got, exp_alpha, tol_pct=0.01)
    print("  ✅  PASS")


def test_tomlinson_alpha_monotonicity():
    """Alpha is non-increasing with c_u (higher c_u → equal or lower alpha)."""
    print("\n══  P7-B-3  Tomlinson alpha monotonicity  ══")
    cus = [5, 15, 25, 40, 55, 70, 90, 150]
    alphas = [_alpha_tomlinson(c) for c in cus]
    for i in range(len(alphas)-1):
        assert alphas[i] >= alphas[i+1] - 1e-9, (
            f"alpha not monotone: alpha({cus[i]})={alphas[i]:.4f} < alpha({cus[i+1]})={alphas[i+1]:.4f}"
        )
    print("  alpha is non-increasing with c_u  ✓")
    print("  ✅  PASS")


def test_nq_meyerhof_known_values():
    """
    Nq Meyerhof (1976) at known phi values.

    Formula: N_q = e^(π·tan φ') × tan²(45 + φ'/2)

    Reference values computed from first principles:
        phi=30°: Nq = e^(π×0.5774) × tan²(60°) = 6.1349 × 3.0000 = 18.40
        phi=35°: Nq = e^(π×0.7002) × tan²(62.5°) = 9.0546 × 3.6902 = 33.42

    Reference: Meyerhof (1976); EC7 Annex D.
    """
    print("\n══  P7-B-4  Nq Meyerhof known values  ══")
    cases = [
        (20.0, math.exp(math.pi*math.tan(math.radians(20))) * math.tan(math.radians(55))**2),
        (25.0, math.exp(math.pi*math.tan(math.radians(25))) * math.tan(math.radians(57.5))**2),
        (30.0, math.exp(math.pi*math.tan(math.radians(30))) * math.tan(math.radians(60))**2),
        (35.0, math.exp(math.pi*math.tan(math.radians(35))) * math.tan(math.radians(62.5))**2),
    ]
    for phi, exp_nq in cases:
        _check(f"Nq(phi={phi}°)", _nq_meyerhof(phi), exp_nq, tol_pct=0.01)
    print("  ✅  PASS")


def test_nq_monotonicity():
    """N_q is strictly increasing with phi."""
    print("\n══  P7-B-5  Nq monotonicity with phi  ══")
    phis = [20, 25, 28, 30, 32, 35, 40]
    nqs  = [_nq_meyerhof(p) for p in phis]
    for i in range(len(nqs)-1):
        assert nqs[i] < nqs[i+1], f"Nq not monotone at phi={phis[i]}"
    print(f"  Nq values: {[round(n,2) for n in nqs]}  ✓")
    print("  ✅  PASS")


# ============================================================
#  P7-C  Clay pile – alpha method (textbook reference)
# ============================================================

def test_clay_pile_alpha_shaft():
    """
    Clay pile shaft resistance using alpha method (Tomlinson 1970).

    Input:
        Driven concrete pile: D=0.4m, L=12m
        Clay (uniform): c_u=60 kPa, γ=18 kN/m³

    Expected (from first principles):
        alpha(60) = 1.00 − 0.50×(60−25)/45 = 0.6111
        q_s,k     = 0.6111 × 60  = 36.67 kPa
        P         = π × 0.4      = 1.2566 m
        R_s,k     = 36.67 × 1.2566 × 12 = 552.92 kN

    Reference: Tomlinson (1970); Craig §11.1; Das §11.4.
    """
    print("\n══  P7-C-1  Clay pile shaft resistance (alpha method)  ══")
    pile   = Pile('driven', 0.4, 12.0)
    layers = [PileSoilLayer(12.0, 18.0, 0.0, 60.0, 'clay')]
    R_bk, R_sk, q_bk, lr = characteristic_pile_capacity(pile, layers)

    alpha_exp = 1.00 - 0.50*(60-25)/45
    q_s_exp   = alpha_exp * 60.0
    R_sk_exp  = q_s_exp * (math.pi * 0.4) * 12.0

    _check("alpha",       lr[0].alpha,   alpha_exp)
    _check("q_s,k (kPa)", lr[0].q_s_k,  q_s_exp)
    _check("R_s,k (kN)",  R_sk,          R_sk_exp)
    print("  ✅  PASS")


def test_clay_pile_base_nc():
    """
    Clay pile base resistance using Skempton Nc=9 (EC7 §7.6.2.3).

    Input (continued from P7-C-1):
        q_b,k = 9 × c_u = 9 × 60 = 540 kPa
        A_b   = π/4 × 0.4² = 0.12566 m²
        R_b,k = 540 × 0.12566 = 67.86 kN

    Reference: Skempton (1951); EC7 §7.6.2.3; Craig §11.1.
    """
    print("\n══  P7-C-2  Clay pile base resistance (Nc=9, Skempton 1951)  ══")
    pile   = Pile('driven', 0.4, 12.0)
    layers = [PileSoilLayer(12.0, 18.0, 0.0, 60.0, 'clay')]
    R_bk, R_sk, q_bk, lr = characteristic_pile_capacity(pile, layers)

    q_b_exp = 9.0 * 60.0
    R_bk_exp = q_b_exp * pile.area_base

    _check("q_b,k (kPa)",  q_bk, q_b_exp)
    _check("R_b,k (kN)",   R_bk, R_bk_exp)
    print("  ✅  PASS")


def test_clay_pile_total_capacity():
    """
    Total characteristic resistance R_c,k = R_s,k + R_b,k.

    Expected:
        R_s,k = 552.92 kN
        R_b,k =  67.86 kN
        R_c,k = 620.78 kN
    """
    print("\n══  P7-C-3  Clay pile total R_c,k  ══")
    pile   = Pile('driven', 0.4, 12.0)
    layers = [PileSoilLayer(12.0, 18.0, 0.0, 60.0, 'clay')]
    R_bk, R_sk, q_bk, _ = characteristic_pile_capacity(pile, layers)
    R_ck = R_bk + R_sk

    _check("R_s,k (kN)", R_sk,  552.9203, tol_pct=0.05)
    _check("R_b,k (kN)", R_bk,   67.8584, tol_pct=0.05)
    _check("R_c,k (kN)", R_ck,  620.7787, tol_pct=0.05)
    print("  ✅  PASS")


def test_clay_pile_da1_pass():
    """
    DA1 ULS verification for clay pile.

    Input (P7-C-3 pile): Gk=300 kN, Qk=100 kN
        C1: F_c,d = 1.35×300 + 1.50×100 = 555.0 kN
            R_c,d = 620.78 / 1.00 = 620.78 kN  → η = 0.8940  PASS
        C2: F_c,d = 1.00×300 + 1.30×100 = 430.0 kN
            R_c,d = 620.78 / 1.30 = 477.52 kN  → η = 0.9005  PASS
    """
    print("\n══  P7-C-4  Clay pile DA1 verification (PASS)  ══")
    pile   = Pile('driven', 0.4, 12.0)
    layers = [PileSoilLayer(12.0, 18.0, 0.0, 60.0, 'clay')]
    res = verify_pile_da1(pile, layers, Gk=300.0, Qk=100.0)

    _check("C1 F_c,d (kN)",  res.comb1.F_c_d,     555.0)
    _check("C1 R_c,d (kN)",  res.comb1.R_c_d,     620.78, tol_pct=0.05)
    _check("C1 utilisation", res.comb1.utilisation, 0.8940, tol_pct=0.1)
    _check("C2 F_c,d (kN)",  res.comb2.F_c_d,     430.0)
    _check("C2 R_c,d (kN)",  res.comb2.R_c_d,     477.52, tol_pct=0.05)
    _check("C2 utilisation", res.comb2.utilisation, 0.9005, tol_pct=0.1)
    assert res.comb1.passes and res.comb2.passes
    assert res.passes is True
    print(f"  Both combinations PASS  ✓")
    print("  ✅  PASS")


# ============================================================
#  P7-D  Sand pile – beta method (textbook reference)
# ============================================================

def test_sand_pile_beta_shaft():
    """
    Sand pile shaft resistance using beta method (Meyerhof 1976).

    Input:
        Driven concrete pile: D=0.4m, L=12m
        Sand (uniform): φ'_k=30°, γ=18 kN/m³

    Expected (K_S_DEFAULT['driven'] = 1.0):
        K_s       = 1.0  (driven, K_S_DEFAULT)
        δ         = 2/3 × 30° = 20°  (concrete interface, δ_factor=2/3)
        σ'_v,mid  = 18 × 6 = 108 kPa
        q_s,k     = 1.0 × 108 × tan(20°) = 108 × 0.36397 = 39.31 kPa
        R_s,k     = 39.31 × π×0.4 × 12  = 592.76 kN

    Reference: Meyerhof (1976); Craig §11.2; Das §11.4.
    """
    print("\n══  P7-D-1  Sand pile shaft resistance (beta method)  ══")
    pile   = Pile('driven', 0.4, 12.0)
    layers = [PileSoilLayer(12.0, 18.0, 30.0, 0.0, 'sand')]
    R_bk, R_sk, q_bk, lr = characteristic_pile_capacity(pile, layers)

    K_s     = K_S_DEFAULT['driven']
    delta_f = 2.0/3.0 * 30.0
    sv_mid  = 18.0 * 6.0
    q_s_exp = K_s * sv_mid * math.tan(math.radians(delta_f))
    R_sk_exp = q_s_exp * (math.pi * 0.4) * 12.0

    _check("sigma_v_mid (kPa)", lr[0].sigma_v_mid, sv_mid)
    _check("q_s,k (kPa)",       lr[0].q_s_k,       q_s_exp, tol_pct=0.05)
    _check("R_s,k (kN)",        R_sk,               R_sk_exp, tol_pct=0.05)
    print("  ✅  PASS")


def test_sand_pile_base_nq():
    """
    Sand pile base resistance using Nq method (Meyerhof 1976).

    Input (P7-D-1 pile):
        Nq(30°)  = e^(π·tan30°) × tan²(60°) = 6.1349 × 3.0 = 18.40
        σ'_v,tip = 18 × 12 = 216 kPa
        q_b,k    = min(216 × 18.40, q_b_lim) kPa
        q_b_lim  = 0.5 × 18.40 × tan(30°) × 1000 = 5312 kPa (no cap here)
        R_b,k    = q_b,k × π/4 × 0.4² = 499.47 kN

    Reference: Meyerhof (1976); EC7 §7.6.2.3; Das §11.4.
    """
    print("\n══  P7-D-2  Sand pile base resistance (Nq method)  ══")
    pile   = Pile('driven', 0.4, 12.0)
    layers = [PileSoilLayer(12.0, 18.0, 30.0, 0.0, 'sand')]
    R_bk, R_sk, q_bk, _ = characteristic_pile_capacity(pile, layers)

    Nq        = _nq_meyerhof(30.0)
    sv_tip    = 18.0 * 12.0
    q_b_raw   = sv_tip * Nq
    q_b_lim   = 0.5 * Nq * math.tan(math.radians(30.0)) * 1000.0
    q_b_exp   = min(q_b_raw, q_b_lim)
    R_bk_exp  = q_b_exp * pile.area_base

    _check("Nq(phi=30)",   Nq,     18.4011, tol_pct=0.01)
    _check("q_b,k (kPa)",  q_bk,  q_b_exp, tol_pct=0.05)
    _check("R_b,k (kN)",   R_bk,  R_bk_exp, tol_pct=0.05)
    print("  ✅  PASS")


def test_sand_pile_total_capacity():
    """
    Total R_c,k for sand pile.

    Expected:
        R_s,k =  592.76 kN
        R_b,k =  499.47 kN
        R_c,k = 1092.23 kN
    """
    print("\n══  P7-D-3  Sand pile total R_c,k  ══")
    pile   = Pile('driven', 0.4, 12.0)
    layers = [PileSoilLayer(12.0, 18.0, 30.0, 0.0, 'sand')]
    R_bk, R_sk, q_bk, _ = characteristic_pile_capacity(pile, layers)
    R_ck = R_bk + R_sk

    _check("R_s,k (kN)",  R_sk,   592.7625, tol_pct=0.05)
    _check("R_b,k (kN)",  R_bk,   499.4683, tol_pct=0.05)
    _check("R_c,k (kN)",  R_ck,  1092.2308, tol_pct=0.05)
    print("  ✅  PASS")


def test_sand_pile_da1_pass():
    """DA1 for sand pile: both combinations pass."""
    print("\n══  P7-D-4  Sand pile DA1 verification (PASS)  ══")
    pile   = Pile('driven', 0.4, 12.0)
    layers = [PileSoilLayer(12.0, 18.0, 30.0, 0.0, 'sand')]
    res = verify_pile_da1(pile, layers, Gk=300.0, Qk=150.0)

    _check("C1 F_c,d (kN)",   res.comb1.F_c_d,     630.0)
    _check("C1 R_c,d (kN)",   res.comb1.R_c_d,    1092.23, tol_pct=0.05)
    _check("C1 utilisation",  res.comb1.utilisation, 0.5768, tol_pct=0.2)
    _check("C2 F_c,d (kN)",   res.comb2.F_c_d,     495.0)
    _check("C2 R_c,d (kN)",   res.comb2.R_c_d,     840.18, tol_pct=0.05)
    assert res.passes
    print(f"  Both combinations PASS  ✓")
    print("  ✅  PASS")


# ============================================================
#  P7-E  Multi-layer pile
# ============================================================

def test_multilayer_pile_reference():
    """
    Multi-layer clay-over-sand pile.

    Profile:
        Layer 1: Clay  h=8m, γ=17 kN/m³, c_u=40 kPa
        Layer 2: Sand  h=7m, γ=19 kN/m³, φ'=28°
    Pile: driven D=0.4m, L=15m

    Expected (from first-principles calculation):
        Layer 1 (clay):
            alpha(40)  = 1.0 − 0.50×(40−25)/45 = 0.8333
            q_s1       = 0.8333 × 40 = 33.33 kPa
            R_s1       = 33.33 × π×0.4 × 8 = 335.10 kN

        Layer 2 (sand, K_s=1.0, δ=2/3×28=18.67°):
            σ'_v,mid2  = 17×8 + 19×3.5 = 136 + 66.5 = 202.5 kPa
            q_s2       = 1.0 × 202.5 × tan(18.67°) = 68.41 kPa
            R_s2       = 68.41 × π×0.4 × 7 = 601.78 kN

        Base (sand, φ'=28°, q_b_lim applies):
            Nq(28)     = 14.72
            σ'_v,tip   = 136 + 19×7 = 269 kPa
            q_b_raw    = 269 × 14.72 = 3960 kPa
            q_b_lim    = 0.5 × 14.72 × tan(28°) × 1000 = 3913 kPa
            q_b,k      = 3913 kPa
            R_b,k      = 3913 × π/4×0.16 = 491.77 kN

        R_c,k = 335.10 + 601.78 + 491.77 = 1428.65 kN
    """
    print("\n══  P7-E-1  Multi-layer pile (clay over sand)  ══")
    pile   = Pile('driven', 0.4, 15.0)
    layers = [
        PileSoilLayer(8.0, 17.0, 0.0,  40.0, 'clay', label='Clay'),
        PileSoilLayer(7.0, 19.0, 28.0,  0.0, 'sand', label='Sand'),
    ]
    R_bk, R_sk, q_bk, lr = characteristic_pile_capacity(pile, layers)
    R_ck = R_bk + R_sk

    _check("Clay R_s,k (kN)",   lr[0].R_s_k,  335.1032, tol_pct=0.05)
    _check("Sand σ'_v,mid (kPa)", lr[1].sigma_v_mid, 202.5)
    _check("Sand R_s,k (kN)",   lr[1].R_s_k,  601.7762, tol_pct=0.05)
    _check("R_b,k (kN)",        R_bk,          491.7660, tol_pct=0.05)
    _check("R_c,k (kN)",        R_ck,         1428.6455, tol_pct=0.05)

    # DA1 with Gk=400, Qk=150
    res = verify_pile_da1(pile, layers, Gk=400.0, Qk=150.0)
    assert res.comb1.passes and res.comb2.passes, "Multi-layer pile should PASS"
    print(f"  DA1 PASS (C1 η={res.comb1.utilisation:.3f}  C2 η={res.comb2.utilisation:.3f})  ✓")
    print("  ✅  PASS")


def test_multilayer_layer_depth_tracking():
    """Layer depths z_top and z_bot must be consistent with layer thicknesses."""
    print("\n══  P7-E-2  Layer depth tracking  ══")
    pile   = Pile('driven', 0.4, 15.0)
    layers = [
        PileSoilLayer(8.0, 17.0, 0.0, 40.0, 'clay'),
        PileSoilLayer(7.0, 19.0, 28.0, 0.0, 'sand'),
    ]
    _, _, _, lr = characteristic_pile_capacity(pile, layers)
    assert abs(lr[0].z_top - 0.0) < 1e-9
    assert abs(lr[0].z_bot - 8.0) < 1e-9
    assert abs(lr[1].z_top - 8.0) < 1e-9
    assert abs(lr[1].z_bot - 15.0) < 1e-9
    print(f"  Layer 1: z_top={lr[0].z_top}  z_bot={lr[0].z_bot}  ✓")
    print(f"  Layer 2: z_top={lr[1].z_top}  z_bot={lr[1].z_bot}  ✓")
    print("  ✅  PASS")


def test_layer_thickness_mismatch_raises():
    """Layers whose total thickness ≠ pile.length raises ValueError."""
    print("\n══  P7-E-3  Layer thickness mismatch raises  ══")
    pile   = Pile('driven', 0.4, 15.0)
    layers = [PileSoilLayer(8.0, 17.0, 0.0, 40.0, 'clay')]  # only 8m != 15m
    try:
        characteristic_pile_capacity(pile, layers)
        raise AssertionError("Should have raised ValueError")
    except ValueError as e:
        print(f"  Raised ValueError ✓  ({str(e)[:60]})")
    print("  ✅  PASS")


# ============================================================
#  P7-F  Bored pile – base reduction factor
# ============================================================

def test_bored_pile_base_reduction():
    """
    Bored pile: base resistance reduced by 0.50 (stress-relief factor).

    Reference: Craig §11.2 — for large-diameter bored piles, the
    base resistance is typically halved relative to driven piles due
    to stress relief and base disturbance during augering.

    Expected: R_b,k(bored) = 0.50 × R_b,k(driven)  (same geometry/soil)
    Shaft resistance is unchanged between driven and bored
    (K_s differs but the formula is the same).
    """
    print("\n══  P7-F-1  Bored pile base reduction factor (0.50)  ══")
    layers = [PileSoilLayer(10.0, 18.0, 30.0, 0.0, 'sand')]
    p_dr = Pile('driven', 0.4, 10.0)
    p_br = Pile('bored',  0.4, 10.0)
    R_bk_d, _, _, _ = characteristic_pile_capacity(p_dr, layers)
    R_bk_b, _, _, _ = characteristic_pile_capacity(p_br, layers)
    ratio = R_bk_b / R_bk_d
    _check("R_b,k(bored) / R_b,k(driven)", ratio, 0.50, tol_pct=0.01)
    print(f"  driven R_b,k={R_bk_d:.2f}  bored R_b,k={R_bk_b:.2f}  ratio={ratio:.3f}  ✓")
    print("  ✅  PASS")


def test_bored_pile_warning_issued():
    """verify_pile_da1 issues an advisory warning for bored piles."""
    print("\n══  P7-F-2  Bored pile advisory warning  ══")
    layers = [PileSoilLayer(10.0, 18.0, 30.0, 0.0, 'sand')]
    res = verify_pile_da1(Pile('bored', 0.4, 10.0), layers, Gk=100.0, Qk=50.0)
    assert any("bored" in w.lower() or "base" in w.lower() for w in res.warnings), (
        f"Expected bored pile warning, got: {res.warnings}"
    )
    print(f"  Warning issued: {res.warnings[0][:70]!r}  ✓")
    print("  ✅  PASS")


# ============================================================
#  P7-G  DA1 ULS verification logic
# ============================================================

def test_da1_factor_application():
    """
    C1 and C2 use the correct γ_G, γ_Q, γ_b, γ_s values.

    C1: γ_G=1.35  γ_Q=1.50  γ_b=1.00  γ_s=1.00
    C2: γ_G=1.00  γ_Q=1.30  γ_b=R4[pile_type]  γ_s=R4[pile_type]
    """
    print("\n══  P7-G-1  DA1 factor application  ══")
    layers = [PileSoilLayer(10.0, 18.0, 0.0, 50.0, 'clay')]
    res = verify_pile_da1(Pile('driven', 0.4, 10.0), layers, Gk=200.0, Qk=80.0)

    assert abs(res.comb1.gamma_G - 1.35) < 1e-9
    assert abs(res.comb1.gamma_Q - 1.50) < 1e-9
    assert abs(res.comb1.gamma_b - 1.00) < 1e-9
    assert abs(res.comb1.gamma_s - 1.00) < 1e-9
    assert abs(res.comb2.gamma_G - 1.00) < 1e-9
    assert abs(res.comb2.gamma_Q - 1.30) < 1e-9
    assert abs(res.comb2.gamma_b - 1.30) < 1e-9   # R4 driven
    assert abs(res.comb2.gamma_s - 1.30) < 1e-9   # R4 driven

    print(f"  C1: γ_G={res.comb1.gamma_G}  γ_Q={res.comb1.gamma_Q}  γ_b={res.comb1.gamma_b}  ✓")
    print(f"  C2: γ_G={res.comb2.gamma_G}  γ_Q={res.comb2.gamma_Q}  γ_b={res.comb2.gamma_b}  ✓")
    print("  ✅  PASS")


def test_da1_r4_factors_by_pile_type():
    """R4 base factors differ by pile type (Table A.6)."""
    print("\n══  P7-G-2  DA1 R4 factors by pile type  ══")
    layers = [PileSoilLayer(10.0, 18.0, 30.0, 0.0, 'sand')]
    for ptype, exp_gb in [('driven', 1.30), ('bored', 1.60), ('CFA', 1.45)]:
        res = verify_pile_da1(Pile(ptype, 0.4, 10.0), layers, Gk=100.0, Qk=50.0)
        assert abs(res.comb2.gamma_b - exp_gb) < 1e-9
        print(f"  {ptype}: γ_b,C2={res.comb2.gamma_b} == {exp_gb}  ✓")
    print("  ✅  PASS")


def test_da1_pass_fail_logic():
    """Overall pass = C1 AND C2. Fail if either combination fails."""
    print("\n══  P7-G-3  DA1 pass/fail logic  ══")
    layers = [PileSoilLayer(10.0, 18.0, 0.0, 60.0, 'clay')]
    pile   = Pile('driven', 0.3, 10.0)

    # Small pile, moderate load → PASS
    r_pass = verify_pile_da1(pile, layers, Gk=100.0, Qk=50.0)
    print(f"  Light load: C1={r_pass.comb1.passes}  C2={r_pass.comb2.passes}  Overall={r_pass.passes}")

    # Huge load → FAIL
    r_fail = verify_pile_da1(pile, layers, Gk=1000.0, Qk=500.0)
    assert not r_fail.passes, "Overloaded pile should FAIL"
    print(f"  Heavy load: Overall FAIL ✓ (η_C1={r_fail.comb1.utilisation:.2f})")
    print("  ✅  PASS")


def test_da1_governing_combination():
    """
    Governing combination is the one with the higher utilisation.

    For piles, C2 typically governs (R4 >> R1, while A2 < A1).
    """
    print("\n══  P7-G-4  Governing combination selection  ══")
    layers = [PileSoilLayer(12.0, 18.0, 30.0, 0.0, 'sand')]
    res = verify_pile_da1(Pile('driven', 0.4, 12.0), layers, Gk=300.0, Qk=150.0)
    gov = res.governing
    other = res.comb1 if gov is res.comb2 else res.comb2
    assert gov.utilisation >= other.utilisation
    print(f"  Governing: {gov.label}  η={gov.utilisation:.4f}  ≥  other η={other.utilisation:.4f}  ✓")
    print("  ✅  PASS")


def test_da1_utilisation_formula():
    """Utilisation η = F_c,d / R_c,d verified from stored components."""
    print("\n══  P7-G-5  DA1 utilisation formula  ══")
    layers = [PileSoilLayer(10.0, 18.0, 0.0, 50.0, 'clay')]
    res = verify_pile_da1(Pile('driven', 0.4, 10.0), layers, Gk=150.0, Qk=60.0)
    for comb in (res.comb1, res.comb2):
        eta_check = comb.F_c_d / comb.R_c_d
        assert abs(eta_check - comb.utilisation) < 1e-9, (
            f"{comb.label}: η={comb.utilisation:.6f} ≠ F/R={eta_check:.6f}"
        )
        print(f"  {comb.label}: F={comb.F_c_d:.2f}  R={comb.R_c_d:.2f}  η={comb.utilisation:.4f}  ✓")
    print("  ✅  PASS")


# ============================================================
#  P7-H  Monotonicity and physics checks
# ============================================================

def test_longer_pile_higher_capacity():
    """R_c,k increases monotonically with pile length."""
    print("\n══  P7-H-1  Longer pile → higher R_c,k  ══")
    lengths = [6.0, 8.0, 10.0, 12.0, 15.0]
    prev_Rck = 0.0
    for L in lengths:
        pile   = Pile('driven', 0.4, L)
        layers = [PileSoilLayer(L, 18.0, 0.0, 60.0, 'clay')]
        R_bk, R_sk, _, _ = characteristic_pile_capacity(pile, layers)
        R_ck = R_bk + R_sk
        assert R_ck > prev_Rck, f"R_c,k not increasing at L={L}"
        print(f"  L={L:4.0f}m → R_c,k={R_ck:.1f} kN")
        prev_Rck = R_ck
    print("  ✅  PASS")


def test_higher_phi_higher_r_bk_sand():
    """Higher φ'_k → higher N_q → higher R_b,k in sand."""
    print("\n══  P7-H-2  Higher phi → higher R_b,k (sand)  ══")
    prev_Rbk = 0.0
    for phi in [25.0, 28.0, 30.0, 32.0, 35.0]:
        pile   = Pile('driven', 0.4, 10.0)
        layers = [PileSoilLayer(10.0, 18.0, phi, 0.0, 'sand')]
        R_bk, _, _, _ = characteristic_pile_capacity(pile, layers)
        assert R_bk > prev_Rbk, f"R_b,k not increasing at phi={phi}"
        print(f"  phi={phi}°  R_b,k={R_bk:.1f} kN")
        prev_Rbk = R_bk
    print("  ✅  PASS")


def test_shaft_dominates_in_clay():
    """For long clay piles (L/D > 10), R_s,k >> R_b,k (shaft dominance)."""
    print("\n══  P7-H-3  Shaft dominates for long clay pile  ══")
    pile   = Pile('driven', 0.4, 20.0)
    layers = [PileSoilLayer(20.0, 18.0, 0.0, 50.0, 'clay')]
    R_bk, R_sk, _, _ = characteristic_pile_capacity(pile, layers)
    assert R_sk > 5.0 * R_bk, (
        f"Expected R_s >> R_b for long clay pile; R_s={R_sk:.1f}  R_b={R_bk:.1f}"
    )
    print(f"  R_s,k={R_sk:.1f}  R_b,k={R_bk:.1f}  ratio={R_sk/R_bk:.1f}  ✓")
    print("  ✅  PASS")


def test_c2_governs_for_piles():
    """
    C2 typically governs for piles (R4 resistance factors > R1).

    The R4 set applies γ_b=1.30/1.60 (driven/bored) vs R1=1.00,
    while the A2 load reduction γ_G=1.00 (vs 1.35 in A1) only partially
    compensates.  For most practical pile geometries C2 is critical.

    Reference: EC7 §7.6.2; Bond & Harris §15.
    """
    print("\n══  P7-H-4  C2 typically governs over C1 for driven piles  ══")
    pile   = Pile('driven', 0.4, 12.0)
    layers = [PileSoilLayer(12.0, 18.0, 30.0, 0.0, 'sand')]
    res = verify_pile_da1(pile, layers, Gk=300.0, Qk=150.0)
    assert res.comb2.utilisation >= res.comb1.utilisation, (
        f"Expected C2 to govern: η_C2={res.comb2.utilisation:.4f} < η_C1={res.comb1.utilisation:.4f}"
    )
    print(f"  η_C1={res.comb1.utilisation:.4f}  η_C2={res.comb2.utilisation:.4f}  ✓")
    print("  ✅  PASS")


# ============================================================
#  P7-I  Edge cases and validation
# ============================================================

def test_invalid_pile_capacity_inputs():
    """Invalid inputs to verify_pile_da1 raise ValueError."""
    print("\n══  P7-I-1  Invalid pile capacity inputs  ══")
    pile   = Pile('driven', 0.4, 10.0)
    layers = [PileSoilLayer(10.0, 18.0, 0.0, 50.0, 'clay')]
    # Gk < 0
    try:
        verify_pile_da1(pile, layers, Gk=-10.0, Qk=0.0)
        raise AssertionError("Should have raised")
    except ValueError:
        print("  Gk<0: raised ValueError ✓")
    # Qk < 0
    try:
        verify_pile_da1(pile, layers, Gk=100.0, Qk=-5.0)
        raise AssertionError("Should have raised")
    except ValueError:
        print("  Qk<0: raised ValueError ✓")
    # Empty layers
    try:
        verify_pile_da1(pile, [], Gk=100.0, Qk=0.0)
        raise AssertionError("Should have raised")
    except ValueError:
        print("  Empty layers: raised ValueError ✓")
    print("  ✅  PASS")


def test_nq_invalid_phi():
    """_nq_meyerhof raises for phi outside (0, 45)."""
    print("\n══  P7-I-2  Nq invalid phi raises  ══")
    for phi in [0.0, 45.0, -5.0, 90.0]:
        try:
            _nq_meyerhof(phi)
            raise AssertionError(f"Should have raised for phi={phi}")
        except ValueError:
            print(f"  phi={phi}: raised ValueError ✓")
    print("  ✅  PASS")


def test_alpha_invalid_cu():
    """_alpha_tomlinson raises for c_u <= 0."""
    print("\n══  P7-I-3  Alpha invalid c_u raises  ══")
    try:
        _alpha_tomlinson(0.0)
        raise AssertionError("Should have raised")
    except ValueError:
        print("  c_u=0: raised ValueError ✓")
    print("  ✅  PASS")


def test_summary_string():
    """PileResult.summary() produces a well-formed output string."""
    print("\n══  P7-I-4  PileResult.summary() format  ══")
    pile   = Pile('driven', 0.4, 12.0)
    layers = [PileSoilLayer(12.0, 18.0, 30.0, 0.0, 'sand')]
    res = verify_pile_da1(pile, layers, Gk=300.0, Qk=150.0)
    summ = res.summary()
    for phrase in ('R_b,k', 'R_s,k', 'R_c,k', 'DA1-C1', 'DA1-C2', 'Governing'):
        assert phrase in summ, f"summary() missing '{phrase}'"
    print(f"  All required phrases present in summary()  ✓")
    print("  ✅  PASS")


# ============================================================
#  Runner
# ============================================================

if __name__ == "__main__":
    tests = [
        # P7-A Geometry
        test_pile_types_accepted,
        test_pile_derived_geometry,
        test_pile_slenderness,
        test_pile_invalid_params,
        test_pile_soil_layer_validation,
        # P7-B Factors and helpers
        test_da1_factor_constants,
        test_tomlinson_alpha_breakpoints,
        test_tomlinson_alpha_monotonicity,
        test_nq_meyerhof_known_values,
        test_nq_monotonicity,
        # P7-C Clay pile
        test_clay_pile_alpha_shaft,
        test_clay_pile_base_nc,
        test_clay_pile_total_capacity,
        test_clay_pile_da1_pass,
        # P7-D Sand pile
        test_sand_pile_beta_shaft,
        test_sand_pile_base_nq,
        test_sand_pile_total_capacity,
        test_sand_pile_da1_pass,
        # P7-E Multi-layer
        test_multilayer_pile_reference,
        test_multilayer_layer_depth_tracking,
        test_layer_thickness_mismatch_raises,
        # P7-F Bored pile
        test_bored_pile_base_reduction,
        test_bored_pile_warning_issued,
        # P7-G DA1 verification
        test_da1_factor_application,
        test_da1_r4_factors_by_pile_type,
        test_da1_pass_fail_logic,
        test_da1_governing_combination,
        test_da1_utilisation_formula,
        # P7-H Monotonicity
        test_longer_pile_higher_capacity,
        test_higher_phi_higher_r_bk_sand,
        test_shaft_dominates_in_clay,
        test_c2_governs_for_piles,
        # P7-I Edge cases
        test_invalid_pile_capacity_inputs,
        test_nq_invalid_phi,
        test_alpha_invalid_cu,
        test_summary_string,
    ]

    passed = failed = 0
    failures = []

    print("\n" + "═"*65)
    print("  SPRINT 7 — EC7 §7 Pile Axial Capacity Suite")
    print("═"*65)

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

    print("\n" + "═"*65)
    print(f"  SPRINT 7 RESULTS: {passed}/{passed+failed} passed, {failed} failed")
    print("═"*65)
    if failures:
        for name, err in failures:
            print(f"    - {name}: {err}")
        sys.exit(1)
    else:
        print("\n  ✅  ALL SPRINT 7 TESTS PASS")
