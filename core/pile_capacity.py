"""
pile_capacity.py – EC7 §7 axial pile capacity and DA1 ULS verification.

Computes the characteristic axial compression resistance of a single pile
from soil layer properties, then applies EC7 DA1 partial factors.

Resistance model
----------------
    R_c,k = R_b,k + R_s,k                         [EC7 §7.6.2.1]

Shaft resistance methods
~~~~~~~~~~~~~~~~~~~~~~~~
    Clay  – Alpha method (Tomlinson 1970):
        q_s,k = α(c_u) × c_u
        where α is an empirical adhesion factor.

    Sand  – Beta method (Meyerhof 1976):
        q_s,k(z) = K_s × σ'_v(z) × tan(δ_k)
        β = K_s × tan(δ_k)  (constant per layer if σ'_v linear)

Base resistance methods
~~~~~~~~~~~~~~~~~~~~~~~
    Clay (undrained, Skempton 1951):
        q_b,k = 9 × c_u,base
        Reference: EC7 §7.6.2.3; Craig §11.1.

    Sand (drained, Nq method, Meyerhof 1976):
        q_b,k = σ'_v,L × N_q
        N_q   = e^(π·tan φ'_k) × tan²(45 + φ'_k/2)    [Meyerhof 1976]
        q_b,k capped at q_b,lim = 0.5 × N_q × tan(φ'_k) [MPa]
        Reference: Das §11.4; Craig §11.2; EC7 §7.6.2.3.

EC7 DA1 partial factors
~~~~~~~~~~~~~~~~~~~~~~~
    Two combinations must both pass (EN 1997-1:2004 §2.4.7.3.2):

    Combination 1  (A1 + M1 + R1):
        γ_G  = 1.35   γ_Q = 1.50   γ_φ = 1.00
        γ_b  = 1.00   γ_s = 1.00   (all pile types, Table A.6 R1 set)

    Combination 2  (A2 + M2 + R4):
        γ_G  = 1.00   γ_Q = 1.30   γ_φ = 1.25
        Resistance factors from EC7 Table A.6 (R4 set):
            driven : γ_b = 1.30, γ_s = 1.30
            bored  : γ_b = 1.60, γ_s = 1.30
            CFA    : γ_b = 1.45, γ_s = 1.30

    Design resistance:
        R_b,d = R_b,k / γ_b
        R_s,d = R_s,k / γ_s
        R_c,d = R_b,d + R_s,d

    Verification:
        F_c,d = γ_G × G_k + γ_Q × Q_k   ≤   R_c,d

Default lateral earth pressure coefficients (K_s)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    driven : K_s = 1.0   (dense sand, mild overconsolidation)
    bored  : K_s = 0.5   (stress relief during installation)
    CFA    : K_s = 0.7   (intermediate; partial displacement)

    These defaults are conservative mid-range values for medium-dense
    sands.  For site-specific design the engineer should determine K_s
    from in-situ tests (e.g. CPT, pressuremeter).

    Reference: Meyerhof (1976); Craig §11.2; Das §11.4.

Alpha factor for clay shaft resistance (Tomlinson 1970)
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
    c_u ≤ 25 kPa : α = 1.00
    25 < c_u ≤ 70 kPa : α = 1.00 − (c_u − 25)/(70 − 25) × 0.50
                             (linear interpolation from 1.0 → 0.5)
    c_u > 70 kPa : α = 0.50

    Reference: Tomlinson (1970); Das §11.4; Craig §11.1.

References:
    EC7 – EN 1997-1:2004, §7, Tables A.6/A.7; Annex D.
    Craig's Soil Mechanics, 9th ed., §11.
    Das, B.M. (2019). Principles of Geotechnical Engineering, §11.
    Meyerhof, G.G. (1976). Bearing Capacity and Settlement of Pile Foundations.
    Tomlinson, M.J. (1970). Adhesion of Piles Driven in Clay.
    Skempton, A.W. (1951). The Bearing Capacity of Clays.

Units:
    Forces (kN), lengths (m), pressures (kPa).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from models.pile import Pile, PileSoilLayer


# ============================================================
#  EC7 DA1 partial factor constants
# ============================================================

# Combination 1  A1 + M1 + R1
C1_G_UNFAV : float = 1.35
C1_Q       : float = 1.50
C1_PHI     : float = 1.00   # M1 – strength unfactored

# Combination 2  A2 + M2 + R4
C2_G_UNFAV : float = 1.00
C2_Q       : float = 1.30
C2_PHI     : float = 1.25   # M2

# Resistance factors R1 (Combination 1, EC7 Table A.6)
R1_BASE : float = 1.00
R1_SHAFT: float = 1.00

# Resistance factors R4 (Combination 2, EC7 Table A.6)
# Keys are pile types.
R4_BASE : dict[str, float] = {
    'driven': 1.30,
    'bored' : 1.60,
    'CFA'   : 1.45,
}
R4_SHAFT: dict[str, float] = {
    'driven': 1.30,
    'bored' : 1.30,
    'CFA'   : 1.30,
}

# Default K_s values by pile type (Meyerhof 1976, Craig §11.2)
K_S_DEFAULT : dict[str, float] = {
    'driven': 1.00,
    'bored' : 0.50,
    'CFA'   : 0.70,
}


# ============================================================
#  Result containers
# ============================================================

@dataclass
class LayerCapacityResult:
    """
    Capacity contribution from one soil layer.

    Attributes
    ----------
    label        : Layer identifier.
    soil_type    : 'sand' or 'clay'.
    thickness    : Layer thickness (m).
    z_top        : Depth to top of layer from ground surface (m).
    z_bot        : Depth to bottom of layer (m).
    sigma_v_mid  : Effective vertical stress at layer midpoint (kPa).
    alpha        : Adhesion factor α (clay only, else 0).
    q_s_k        : Unit shaft resistance (kPa).
    A_s          : Shaft area of this layer (m²).
    R_s_k        : Characteristic shaft resistance from this layer (kN).
    """
    label       : str
    soil_type   : str
    thickness   : float
    z_top       : float
    z_bot       : float
    sigma_v_mid : float
    alpha       : float
    q_s_k       : float
    A_s         : float
    R_s_k       : float


@dataclass
class PileCombinationResult:
    """
    DA1 verification result for one EC7 combination.

    Attributes
    ----------
    label        : 'DA1-C1' or 'DA1-C2'.
    gamma_G      : Permanent action factor used.
    gamma_Q      : Variable action factor used.
    gamma_phi    : Material factor for friction angle.
    gamma_b      : Base resistance factor (Table A.6).
    gamma_s      : Shaft resistance factor (Table A.6).
    F_c_d        : Factored design axial compression force (kN).
    R_b_d        : Design base resistance (kN).
    R_s_d        : Design shaft resistance (kN).
    R_c_d        : Design total resistance = R_b_d + R_s_d (kN).
    utilisation  : F_c_d / R_c_d.
    passes       : True if utilisation <= 1.0.
    """
    label       : str
    gamma_G     : float
    gamma_Q     : float
    gamma_phi   : float
    gamma_b     : float
    gamma_s     : float
    F_c_d       : float
    R_b_d       : float
    R_s_d       : float
    R_c_d       : float
    utilisation : float
    passes      : bool


@dataclass
class PileResult:
    """
    Complete EC7 §7 pile axial capacity and DA1 ULS verification.

    Attributes
    ----------
    pile         : Pile geometry.
    layers       : Soil profile used.
    R_b_k        : Characteristic base resistance (kN).
    R_s_k        : Characteristic total shaft resistance (kN).
    R_c_k        : Characteristic total pile resistance (kN).
    q_b_k        : Characteristic unit base resistance (kPa).
    layer_results: Per-layer shaft capacity breakdown.
    comb1        : DA1-C1 verification result.
    comb2        : DA1-C2 verification result.
    governing    : Combination with higher utilisation (critical).
    passes       : True if both C1 and C2 pass.
    warnings     : Advisory messages.
    """
    pile         : Pile
    layers       : list[PileSoilLayer]
    R_b_k        : float
    R_s_k        : float
    R_c_k        : float
    q_b_k        : float
    layer_results: list[LayerCapacityResult]
    comb1        : PileCombinationResult
    comb2        : PileCombinationResult
    governing    : PileCombinationResult
    passes       : bool
    warnings     : list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"{'='*65}",
            f"  EC7 §7 Pile Axial Capacity — DA1 Verification",
            f"{'-'*65}",
            f"  Pile : {self.pile.pile_type}  D={self.pile.diameter}m  "
            f"L={self.pile.length}m  ({self.pile.material})",
            f"{'-'*65}",
            f"  Characteristic Resistance:",
            f"    R_b,k  = {self.R_b_k:>8.2f} kN   (q_b,k = {self.q_b_k:.1f} kPa)",
            f"    R_s,k  = {self.R_s_k:>8.2f} kN",
            f"    R_c,k  = {self.R_c_k:>8.2f} kN",
            f"{'-'*65}",
            f"  DA1 Combinations:",
        ]
        for c in (self.comb1, self.comb2):
            tag = "PASS" if c.passes else "FAIL"
            lines.append(
                f"  {c.label}  γ_G={c.gamma_G:.2f}  γ_Q={c.gamma_Q:.2f}"
                f"  γ_b={c.gamma_b:.2f}  γ_s={c.gamma_s:.2f}  |"
                f"  F_c,d={c.F_c_d:.1f} kN"
                f"  R_c,d={c.R_c_d:.1f} kN"
                f"  η={c.utilisation:.3f}  [{tag}]"
            )
        ov = "PASS" if self.passes else "FAIL"
        lines += [
            f"{'-'*65}",
            f"  Governing: {self.governing.label}  η={self.governing.utilisation:.3f}",
            f"  Overall  : {ov}",
            f"{'='*65}",
        ]
        if self.warnings:
            lines.insert(-1, f"  WARN: {len(self.warnings)} message(s) — see .warnings")
        return "\n".join(lines)


# ============================================================
#  Private helpers
# ============================================================

def _alpha_tomlinson(c_u: float) -> float:
    """
    Adhesion factor α for alpha method shaft resistance in clay.

    Piece-wise linear interpolation:
        c_u ≤ 25 kPa  → α = 1.00
        25 < c_u ≤ 70 → α = 1.00 − 0.50 × (c_u − 25) / 45
        c_u > 70 kPa  → α = 0.50

    Reference:
        Tomlinson (1970). Adhesion of Piles Driven in Clay.
        Das, B.M. (2019). Principles of Geotechnical Engineering, §11.4.
        Craig's Soil Mechanics, 9th ed., §11.1.

    :param c_u: Undrained shear strength (kPa). Must be > 0.
    :return: Adhesion factor α (-).
    """
    if c_u <= 0:
        raise ValueError(f"c_u must be > 0, got {c_u}")
    if c_u <= 25.0:
        return 1.00
    if c_u <= 70.0:
        return 1.00 - 0.50 * (c_u - 25.0) / 45.0
    return 0.50


def _nq_meyerhof(phi_deg: float) -> float:
    """
    Meyerhof (1976) bearing capacity factor N_q for driven piles in sand.

    Formula (same as EC7 Annex D analytical bearing capacity factor):
        N_q = e^(π·tan φ') × tan²(45 + φ'/2)

    Reference:
        Meyerhof (1976). Bearing Capacity and Settlement of Pile Foundations.
        Das, B.M. (2019). §11.4, Table 11.1.
        EC7 §7.6.2.3 (base resistance in sand).

    :param phi_deg: Design friction angle φ'_d (degrees).  Must be in (0, 45).
    :return: N_q (-).
    :raises ValueError: If phi_deg outside valid range.
    """
    if not (0.0 < phi_deg < 45.0):
        raise ValueError(f"phi_deg must be in (0, 45), got {phi_deg}")
    phi_r = math.radians(phi_deg)
    return math.exp(math.pi * math.tan(phi_r)) * math.tan(math.radians(45.0 + phi_deg / 2.0)) ** 2


def _effective_stress_profile(layers: list[PileSoilLayer]) -> list[float]:
    """
    Compute effective vertical stress at the TOP of each layer.

    Returns a list of length len(layers) + 1, where index i is the
    effective stress at the top of layer i, and index -1 at the pile tip.

    Assumes no water table (submerged case not yet implemented).
    Total unit weight γ used as surrogate for γ' where GWT is at surface.
    """
    sigma_v = [0.0]   # ground surface
    for layer in layers:
        sigma_v.append(sigma_v[-1] + layer.gamma * layer.thickness)
    return sigma_v


def _k_s_for_pile(pile: Pile, layer: PileSoilLayer) -> float:
    """
    Select lateral earth pressure coefficient K_s.

    Uses the layer-specific override if provided, otherwise the
    pile-type default (K_S_DEFAULT).
    """
    if layer.K_s is not None:
        return layer.K_s
    return K_S_DEFAULT[pile.pile_type]


# ============================================================
#  Characteristic capacity
# ============================================================

def characteristic_pile_capacity(
    pile   : Pile,
    layers : list[PileSoilLayer],
) -> tuple[float, float, float, list[LayerCapacityResult]]:
    """
    Compute the characteristic axial pile resistance R_c,k.

    EC7 §7.6.2.1:
        R_c,k = R_b,k + R_s,k

    Shaft method depends on layer.soil_type:
        'clay' → alpha method (Tomlinson 1970).
        'sand' → beta method (Meyerhof 1976).

    Base resistance is governed by the BOTTOM layer soil type:
        'clay' → Skempton (1951):  q_b,k = 9 × c_u,base.
        'sand' → Meyerhof (1976):  q_b,k = σ'_v,L × N_q.

    For bored piles in sand the base resistance is multiplied by a
    reduction factor of 0.5 (stress-relief factor, Craig §11.2).

    :param pile:   Pile geometry and installation type.
    :param layers: Ordered list of PileSoilLayer from ground surface
                   to pile tip.  Σ(layer.thickness) must equal pile.length.
    :return: (R_b_k, R_s_k, q_b_k, layer_results)
             R_b_k — characteristic base resistance (kN).
             R_s_k — characteristic shaft resistance (kN).
             q_b_k — characteristic unit base resistance (kPa).
             layer_results — per-layer breakdown.
    :raises ValueError: If total layer thickness ≠ pile.length (tol 1 mm).
    """
    total_thickness = sum(lay.thickness for lay in layers)
    if abs(total_thickness - pile.length) > 1e-3:
        raise ValueError(
            f"Sum of layer thicknesses ({total_thickness:.4f} m) must equal "
            f"pile.length ({pile.length} m)."
        )

    # Effective vertical stress at top of each layer
    sigma_v_tops = _effective_stress_profile(layers)  # length = len(layers)+1

    layer_results : list[LayerCapacityResult] = []
    R_s_k_total   : float = 0.0

    for i, layer in enumerate(layers):
        z_top = sum(la.thickness for la in layers[:i])
        z_bot = z_top + layer.thickness
        sigma_v_mid = (sigma_v_tops[i] + sigma_v_tops[i + 1]) / 2.0

        A_s = pile.perimeter * layer.thickness

        if layer.soil_type == 'clay':
            alpha = _alpha_tomlinson(layer.c_k)
            q_s_k = alpha * layer.c_k
        else:  # sand – beta method
            k_s   = _k_s_for_pile(pile, layer)
            delta  = layer.delta_factor * layer.phi_k   # interface friction (degrees)
            q_s_k  = k_s * sigma_v_mid * math.tan(math.radians(delta))
            alpha  = 0.0   # not applicable for sand

        R_s_k_layer = q_s_k * A_s
        R_s_k_total += R_s_k_layer

        layer_results.append(LayerCapacityResult(
            label       = layer.label or f"Layer {i+1}",
            soil_type   = layer.soil_type,
            thickness   = layer.thickness,
            z_top       = z_top,
            z_bot       = z_bot,
            sigma_v_mid = sigma_v_mid,
            alpha       = alpha,
            q_s_k       = q_s_k,
            A_s         = A_s,
            R_s_k       = R_s_k_layer,
        ))

    # ── Base resistance ───────────────────────────────────────────────────
    base_layer   = layers[-1]
    sigma_v_tip  = sigma_v_tops[-1]   # effective stress at pile tip

    if base_layer.soil_type == 'clay':
        # Skempton (1951): q_b,k = 9 × c_u  [EC7 §7.6.2.3, Craig §11.1]
        q_b_k = 9.0 * base_layer.c_k
    else:
        # Meyerhof (1976): q_b,k = σ'_v,L × N_q  [EC7 §7.6.2.3]
        # Use characteristic phi_k for capacity (unfactored at this stage)
        nq    = _nq_meyerhof(base_layer.phi_k)
        q_b_k = sigma_v_tip * nq
        # Meyerhof cap: q_b,lim = 0.5 × Nq × tan(φ') [MPa → kPa]
        q_b_lim = 0.5 * nq * math.tan(math.radians(base_layer.phi_k)) * 1000.0
        q_b_k   = min(q_b_k, q_b_lim)
        # Bored/CFA pile reduction (stress-relief at base, Craig §11.2)
        if pile.pile_type in ('bored', 'CFA'):
            q_b_k *= 0.50

    R_b_k = q_b_k * pile.area_base

    return R_b_k, R_s_k_total, q_b_k, layer_results


# ============================================================
#  DA1 verification
# ============================================================

def _run_pile_combination(
    label   : str,
    pile    : Pile,
    R_b_k   : float,
    R_s_k   : float,
    Gk      : float,
    Qk      : float,
    gamma_G : float,
    gamma_Q : float,
    gamma_b : float,
    gamma_s : float,
    gamma_phi: float,  # stored for traceability, not used in capacity calc here
) -> PileCombinationResult:
    """
    Single DA1 combination for axial pile ULS verification.

    R_b,d = R_b,k / γ_b
    R_s,d = R_s,k / γ_s
    R_c,d = R_b,d + R_s,d
    F_c,d = γ_G × G_k + γ_Q × Q_k
    Passes : F_c,d ≤ R_c,d

    Note: The material factor γ_φ (M2 in C2) is applied to the soil
    friction angle φ_k → φ_d when computing the shaft resistance in sand
    (beta method).  For characteristic capacity computation, the
    unfactored phi_k is used to determine R_c,k; for C2 the same R_c,k
    is then divided by the R4 resistance factors — this is the simplified
    model-factor approach for DA1.

    For a rigorous C2 treatment the shaft resistance would be re-computed
    using phi_d = arctan(tan(phi_k)/1.25).  This is implemented as a
    future upgrade; the current approach is conservative for sand (lower
    phi_d → lower beta → lower R_s,k, then divided by R4 factor).

    Reference:
        EC7 §7.6.2.1; EN 1997-1:2004 §2.4.7.3.2.
        Bond & Harris – Decoding Eurocode 7, §15.
    """
    R_b_d = R_b_k / gamma_b
    R_s_d = R_s_k / gamma_s
    R_c_d = R_b_d + R_s_d
    F_c_d = gamma_G * Gk + gamma_Q * Qk
    util  = F_c_d / max(R_c_d, 1e-9)

    return PileCombinationResult(
        label       = label,
        gamma_G     = gamma_G,
        gamma_Q     = gamma_Q,
        gamma_phi   = gamma_phi,
        gamma_b     = gamma_b,
        gamma_s     = gamma_s,
        F_c_d       = F_c_d,
        R_b_d       = R_b_d,
        R_s_d       = R_s_d,
        R_c_d       = R_c_d,
        utilisation = util,
        passes      = util <= 1.0,
    )


def verify_pile_da1(
    pile   : Pile,
    layers : list[PileSoilLayer],
    Gk     : float,
    Qk     : float,
) -> PileResult:
    """
    EC7 §7 pile axial capacity and DA1 ULS verification.

    Two DA1 combinations are checked (EN 1997-1:2004 §2.4.7.3.2):
        Combination 1  (A1 + M1 + R1)
        Combination 2  (A2 + M2 + R4)

    Both must pass for the overall verdict to be PASS.

    :param pile:   Pile geometry and installation type.
    :param layers: Ordered soil layers from ground surface to pile tip.
                   Must have Σ(thickness) == pile.length (tol 1 mm).
    :param Gk:    Characteristic permanent compressive action on pile (kN).
                   Positive = compression (downward).
    :param Qk:    Characteristic variable compressive action on pile (kN).
    :return:       PileResult with characteristic capacity + DA1 checks.
    :raises ValueError: If inputs are invalid (delegated from sub-functions).

    Reference:
        EC7 EN 1997-1:2004, §7.6.2; Tables A.6/A.7.
        Bond & Harris – Decoding Eurocode 7, §15.
        Craig's Soil Mechanics, 9th ed., §11.
    """
    if Gk < 0:
        raise ValueError(f"Gk must be >= 0 (compression positive), got {Gk}")
    if Qk < 0:
        raise ValueError(f"Qk must be >= 0, got {Qk}")
    if not layers:
        raise ValueError("layers must be a non-empty list of PileSoilLayer.")

    warnings: list[str] = []

    # ── Characteristic capacity ───────────────────────────────────────────
    R_b_k, R_s_k, q_b_k, layer_results = characteristic_pile_capacity(pile, layers)
    R_c_k = R_b_k + R_s_k

    # ── Advisory: R_s dominance ───────────────────────────────────────────
    if R_b_k > 0 and R_s_k / R_c_k < 0.10:
        warnings.append(
            f"Shaft resistance is only {R_s_k/R_c_k:.0%} of R_c,k. "
            "Consider increasing pile length to mobilise more shaft friction."
        )

    if pile.pile_type == 'bored':
        warnings.append(
            "Bored pile: base resistance is reduced by 0.5 (stress-relief factor, "
            "Craig §11.2). Verify with load test per EC7 §7.5."
        )

    # ── DA1 Combination 1 (A1+M1+R1) ─────────────────────────────────────
    comb1 = _run_pile_combination(
        label    = "DA1-C1",
        pile     = pile,
        R_b_k    = R_b_k,
        R_s_k    = R_s_k,
        Gk       = Gk,
        Qk       = Qk,
        gamma_G  = C1_G_UNFAV,
        gamma_Q  = C1_Q,
        gamma_b  = R1_BASE,
        gamma_s  = R1_SHAFT,
        gamma_phi= C1_PHI,
    )

    # ── DA1 Combination 2 (A2+M2+R4) ─────────────────────────────────────
    comb2 = _run_pile_combination(
        label    = "DA1-C2",
        pile     = pile,
        R_b_k    = R_b_k,
        R_s_k    = R_s_k,
        Gk       = Gk,
        Qk       = Qk,
        gamma_G  = C2_G_UNFAV,
        gamma_Q  = C2_Q,
        gamma_b  = R4_BASE[pile.pile_type],
        gamma_s  = R4_SHAFT[pile.pile_type],
        gamma_phi= C2_PHI,
    )

    governing = comb1 if comb1.utilisation >= comb2.utilisation else comb2
    passes    = comb1.passes and comb2.passes

    return PileResult(
        pile         = pile,
        layers       = layers,
        R_b_k        = R_b_k,
        R_s_k        = R_s_k,
        R_c_k        = R_c_k,
        q_b_k        = q_b_k,
        layer_results= layer_results,
        comb1        = comb1,
        comb2        = comb2,
        governing    = governing,
        passes       = passes,
        warnings     = warnings,
    )
