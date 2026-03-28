"""
sheet_pile_analysis.py — Free-earth support method for propped sheet piles.

Implements the classical Blum (1931) free-earth support method as presented
in Craig's Soil Mechanics, 9th ed., §12.2, with EC7 DA1 partial factors.

Scope of Sprint 10
------------------
  • Propped/anchored sheet pile in homogeneous cohesionless soil.
  • Rankine earth pressure coefficients (Ka, Kp).
  • Optional uniform surcharge on the retained surface.
  • Optional water table on the retained side (with dry passive side).
  • EC7 DA1: combination C1 (A1+M1+R1) and C2 (A2+M2+R1).
  • Outputs: minimum embedment depth d_min, prop force T, pressure diagram,
    maximum bending moment and its depth, full DA1 result.

NOT in scope (Sprint 10):
  • Fixed-earth support / cantilever walls (Sprint 11).
  • Cohesive soils (c' > 0) in the embedded zone.
  • Interface friction (δ ≠ 0); Coulomb Ka/Kp (Sprint 11 upgrade).
  • Rowe's moment reduction (Sprint 11).
  • Seismic forces (Sprint 12+).

Free-earth support method (Craig §12.2)
----------------------------------------
For a propped wall with prop at depth z_prop from the top of the retained
soil (z_prop = 0 means prop at the very top):

  1. Compute active pressure on retained side and passive on embedded side.
  2. Take moments about the prop location.
  3. Solve the resulting cubic equation in d (embedment depth) numerically.
  4. Compute prop force from horizontal equilibrium.
  5. Find maximum bending moment from the shear-force diagram.

EC7 DA1 partial factors (Table A.4 — GEO)
-----------------------------------------
  C1 (A1+M1+R1):  γ_G=1.35, γ_Q=1.50, γ_φ=1.00  (actions factored, strength char.)
  C2 (A2+M2+R1):  γ_G=1.00, γ_Q=1.30, γ_φ=1.25  (strength factored)

For embedded walls, EC7 §9.7.4 specifies that the partial factor γ_φ is
applied to tan φ', giving:
    tan φ'_d = tan φ'_k / γ_φ
    Ka_d, Kp_d derived from φ'_d.

C2 with γ_φ=1.25 governs the embedment depth for dense sands (φ'>30°).
C1 with factored actions can govern the prop force.

Geometry sign convention
------------------------
    z  = 0      : prop level (top of wall or anchor point)
    z  = h_prop : excavation level  (= h_retained - |z_prop_from_top|)
    z  > h_prop : embedded section  (d = z − h_prop)

References
----------
Blum, H. (1931). Einspannungsverhältnisse bei Bohlwerken. Wilhelm Ernst
    & Sohn, Berlin.
Craig's Soil Mechanics, 9th ed., §12.2 (Knappett & Craig).
EC7 EN 1997-1:2004, §9.7, Tables A.4/A.13.
Bond, A. & Harris, A. (2008). Decoding Eurocode 7. Taylor & Francis, §12.
Das, B.M. (2019). Principles of Geotechnical Engineering, §11.6.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional

from models.sheet_pile import SheetPile
from models.soil import Soil


# ── Constants ─────────────────────────────────────────────────────────────────

GAMMA_W: float = 9.81   # Unit weight of water (kN/m³)

# EC7 Table A.4 — Design Approach 1 partial factors for GEO
# C1 (A1 + M1 + R1): actions factored, characteristic strength
DA1_C1_GAMMA_PHI: float = 1.00   # M1 — characteristic
DA1_C1_GAMMA_G:   float = 1.35   # A1 permanent unfavourable
DA1_C1_GAMMA_Q:   float = 1.50   # A1 variable unfavourable

# C2 (A2 + M2 + R1): characteristic actions, factored strength
DA1_C2_GAMMA_PHI: float = 1.25   # M2 — factored tan φ'
DA1_C2_GAMMA_G:   float = 1.00   # A2 permanent unfavourable
DA1_C2_GAMMA_Q:   float = 1.30   # A2 variable unfavourable

_NEWTON_MAX_ITER: int   = 200
_NEWTON_TOL:      float = 1e-10


# ── Result containers ─────────────────────────────────────────────────────────

@dataclass
class PressurePoint:
    """
    A single point on the earth pressure diagram.

    Attributes
    ----------
    z       : Depth below the TOP of the wall (m), not from prop.
    z_datum : Depth relative to the excavation (dredge) level (m).
              Negative = above excavation.  Positive = embedded.
    p_a     : Active earth pressure at this depth (kPa).
    p_p     : Passive earth pressure at this depth (kPa).
    u       : Pore water pressure at this depth (kPa), combined (both sides).
    p_net   : Net pressure = p_a − p_p + u_net (kPa).
              Positive → towards excavation side (active dominates).
    """
    z       : float
    z_datum : float
    p_a     : float
    p_p     : float
    u       : float = 0.0
    p_net   : float = 0.0


@dataclass
class SheetPileCombResult:
    """
    EC7 DA1 result for one combination (C1 or C2).

    Attributes
    ----------
    label        : 'DA1-C1' or 'DA1-C2'.
    gamma_phi    : Partial factor on tan φ'.
    phi_d_deg    : Design friction angle φ'_d (degrees).
    Ka_d         : Design active earth pressure coefficient.
    Kp_d         : Design passive earth pressure coefficient.
    d_min        : Minimum required embedment depth (m).
    T_k          : Characteristic prop force per unit width (kN/m).
    z_Mmax       : Depth of maximum bending moment below prop (m).
    M_max        : Maximum bending moment per unit width (kN·m/m).
    converged    : True if the moment equation solver converged.
    """
    label     : str
    gamma_phi : float
    phi_d_deg : float
    Ka_d      : float
    Kp_d      : float
    d_min     : float
    T_k       : float
    z_Mmax    : float
    M_max     : float
    converged : bool = True


@dataclass
class SheetPileResult:
    """
    Complete result from analyse_sheet_pile_da1().

    Attributes
    ----------
    pile          : The input SheetPile model (with d_embed set to d_design).
    soil          : The input Soil.
    Ka_k, Kp_k    : Characteristic Ka, Kp (γ_φ=1.00).
    comb1, comb2  : DA1 combination results.
    governing     : The governing combination (higher d_min).
    d_design      : Governing design embedment depth (m) = max(C1, C2) d_min.
    T_design      : Governing prop force (kN/m).
    M_max_design  : Governing maximum bending moment (kN·m/m).
    pressure_diagram : List of PressurePoint objects for the characteristic
                       (unfactored) pressure diagram.
    passes        : True if the wall passes both combinations.
    warnings      : List of informational/advisory strings.
    """
    pile             : SheetPile
    soil             : Soil
    Ka_k             : float
    Kp_k             : float
    comb1            : SheetPileCombResult
    comb2            : SheetPileCombResult
    governing        : SheetPileCombResult
    d_design         : float
    T_design         : float
    M_max_design     : float
    pressure_diagram : list[PressurePoint] = field(default_factory=list)
    passes           : bool = True
    warnings         : list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            f"SheetPile — Free-Earth Support (EC7 DA1)",
            f"  Pile:        {self.pile.label}  h={self.pile.h_retained:.2f}m",
            f"  Soil:        {self.soil.name}  φ'={self.soil.phi_k:.1f}°  γ={self.soil.gamma:.1f} kN/m³",
            f"  Ka_k={self.Ka_k:.4f}  Kp_k={self.Kp_k:.4f}",
            f"  Governing:   {self.governing.label}  (φ'_d={self.governing.phi_d_deg:.2f}°)",
            f"  d_design:    {self.d_design:.4f} m",
            f"  T (prop):    {self.T_design:.3f} kN/m",
            f"  M_max:       {self.M_max_design:.3f} kN·m/m  @ z={self.governing.z_Mmax:.3f} m below prop",
            f"  Passes:      {'✅ YES' if self.passes else '❌ NO'}",
        ]
        if self.warnings:
            lines += [f"  ⚠ {w}" for w in self.warnings]
        return "\n".join(lines)


# ── Pressure coefficient helpers ──────────────────────────────────────────────

def ka_rankine(phi_deg: float) -> float:
    """
    Rankine active earth pressure coefficient.

    Ka = tan²(45° − φ'/2)

    Reference: Craig §11.3, eq. (11.1). Rankine (1857).

    :param phi_deg: Friction angle φ' (degrees).
    :return: Ka (dimensionless).
    """
    if not (0.0 <= phi_deg < 90.0):
        raise ValueError(f"phi_deg must be in [0, 90), got {phi_deg}")
    return math.tan(math.radians(45.0 - phi_deg / 2.0)) ** 2


def kp_rankine(phi_deg: float) -> float:
    """
    Rankine passive earth pressure coefficient.

    Kp = tan²(45° + φ'/2)

    Reference: Craig §11.3, eq. (11.2). Rankine (1857).

    :param phi_deg: Friction angle φ' (degrees).
    :return: Kp (dimensionless).
    """
    if not (0.0 <= phi_deg < 90.0):
        raise ValueError(f"phi_deg must be in [0, 90), got {phi_deg}")
    return math.tan(math.radians(45.0 + phi_deg / 2.0)) ** 2


def _design_phi(phi_k: float, gamma_phi: float) -> float:
    """
    Factored design friction angle.

    tan φ'_d = tan φ'_k / γ_φ

    Reference: EC7 §2.4.6.2(3)P; Table A.4 M1/M2.

    :param phi_k:     Characteristic friction angle (degrees).
    :param gamma_phi: Partial factor on tan φ' (1.00 for C1, 1.25 for C2).
    :return: Design friction angle φ'_d (degrees).
    """
    tan_phi_d = math.tan(math.radians(phi_k)) / gamma_phi
    return math.degrees(math.atan(tan_phi_d))


# ── Active pressure blocks ────────────────────────────────────────────────────

def _active_blocks(
    Ka      : float,
    gamma   : float,
    h       : float,
    z_prop  : float,
    q       : float = 0.0,
    z_w     : float | None = None,
    gamma_prime: float | None = None,
    gamma_w : float = GAMMA_W,
) -> list[tuple[float, float, float]]:
    """
    Return a list of (force, arm_from_prop) tuples for active pressure blocks.

    All depths are measured from the TOP of the retained soil.
    The prop is at depth z_prop from the top (z_prop=0 → prop at top).

    Active pressure σ_a(z):
      • Surcharge:        Ka * q            (uniform, full depth)
      • Soil above WT:    Ka * γ * z        (dry unit weight)
      • Soil below WT:    Ka * γ' * (z−z_w) (buoyant unit weight)
      • Hydrostatic:      γ_w * (z−z_w)     (below WT)

    Only the portion ABOVE the excavation level (z ≤ z_prop + h_exc) is
    included here.  h_exc = total retained height (h measured in SheetPile
    is the height from top of retained soil to excavation level).

    :param Ka:          Active pressure coefficient.
    :param gamma:       Total unit weight of soil (kN/m³).
    :param h:           Retained height (excavation depth from top, m).
    :param z_prop:      Depth of prop below top of retained soil (m).
    :param q:           Uniform surcharge at retained surface (kPa).
    :param z_w:         Depth to water table from top of retained soil (m).
                        None = no water table (dry analysis).
    :param gamma_prime: Buoyant unit weight (kN/m³), required if z_w given.
    :param gamma_w:     Unit weight of water (kN/m³).
    :return: List of (force_kN_per_m, arm_from_prop_m) tuples.
             Force is positive (drives wall toward excavation).
    """
    blocks: list[tuple[float, float, float]] = []
    # h_e = retained height above excavation = h
    # Depth axis z: 0=top of retained soil, h=excavation level
    # Prop arm = depth - z_prop  (positive when below prop)

    def arm(z_centroid: float) -> float:
        return z_centroid - z_prop

    # 1. Surcharge: uniform pressure Ka*q over full depth 0..h
    if q > 0.0:
        F_q = Ka * q * h
        z_q = h / 2.0
        blocks.append((F_q, arm(z_q)))

    if z_w is None:
        # DRY: single triangular block 0..h
        # σ_a(h) = Ka*gamma*h
        F_dry = 0.5 * Ka * gamma * h**2
        z_dry = 2.0 * h / 3.0
        blocks.append((F_dry, arm(z_dry)))
    else:
        # WT at z_w
        if z_w > h:
            z_w = h   # WT below excavation → treat as dry above dredge
        if z_prime := (h - z_w):
            # Zone 1: 0..z_w — dry triangle
            F1 = 0.5 * Ka * gamma * z_w**2
            z1 = 2.0 * z_w / 3.0
            blocks.append((F1, arm(z1)))
            # Zone 2: z_w..h — rectangle of Ka*gamma*z_w
            pa_zw = Ka * gamma * z_w
            F2 = pa_zw * z_prime
            z2 = z_w + z_prime / 2.0
            blocks.append((F2, arm(z2)))
            # Zone 3: z_w..h — triangle Ka*gamma'*(z-z_w)
            F3 = 0.5 * Ka * gamma_prime * z_prime**2
            z3 = z_w + 2.0 * z_prime / 3.0
            blocks.append((F3, arm(z3)))
            # Zone 4: z_w..h — hydrostatic: 0.5*gamma_w*(z-z_w)²
            F4 = 0.5 * gamma_w * z_prime**2
            z4 = z_w + 2.0 * z_prime / 3.0
            blocks.append((F4, arm(z4)))
        else:
            # z_w >= h: treat as dry
            F_dry = 0.5 * Ka * gamma * h**2
            z_dry = 2.0 * h / 3.0
            blocks.append((F_dry, arm(z_dry)))

    return blocks


# ── Core solver ───────────────────────────────────────────────────────────────

def _solve_embedment(
    Ka      : float,
    Kp      : float,
    gamma   : float,
    h       : float,
    z_prop  : float,
    q       : float = 0.0,
    z_w     : float | None = None,
    gamma_prime: float | None = None,
    gamma_w : float = GAMMA_W,
    d_max   : float = 50.0,
    tol     : float = _NEWTON_TOL,
) -> tuple[float, bool]:
    """
    Solve for minimum embedment depth by moment equilibrium about the prop.

    Driving moments (active above + below dredge) = Resisting moment (passive).

    For depth d below excavation level:
        Active below dredge:
          Rect: Ka*gamma*σ_v_top*d   at (h_exc + d/2) from top
          Tri:  0.5*Ka*gamma*d²      at (h_exc + 2d/3) from top
          (plus water terms if z_w < h_exc)
        Passive:
          Tri:  0.5*Kp*gamma*d²      at (h_exc + 2d/3) from top
          (dry passive side assumed)

    Reference: Craig §12.2, eq. (12.1).

    :param Ka:      Design active pressure coefficient.
    :param Kp:      Design passive pressure coefficient.
    :param gamma:   Total unit weight (kN/m³).
    :param h:       Retained height (m) [= depth from top to excavation].
    :param z_prop:  Depth of prop below top (m).
    :param q:       Surface surcharge (kPa).
    :param z_w:     Depth to water table from top (m), or None if dry.
    :param gamma_prime: Buoyant unit weight (m³/kN), required if z_w given.
    :param gamma_w: Unit weight of water (kN/m³).
    :param d_max:   Upper bound for solver (m).
    :param tol:     Convergence tolerance on d (m).
    :return: (d_min, converged).
    """
    # σ'_v at the TOP of the embedded section (at excavation level)
    if z_w is None or z_w >= h:
        sigma_v_dredge = gamma * h
    else:
        sigma_v_dredge = gamma * z_w + (gamma_prime or (gamma - GAMMA_W)) * (h - z_w)

    # Pore pressure at dredge level (retained side water table)
    u_dredge = gamma_w * max(0.0, h - (z_w if z_w is not None else h))

    # Total active+water pressure at dredge level (acts as the constant term below)
    p_a_dredge = Ka * sigma_v_dredge + u_dredge + Ka * q  # kPa

    # Below excavation (depth d, passive side is dry):
    # Active contribution per unit depth: Ka*gamma_sub (submerged)
    # where gamma_sub = gamma_prime if below WT, else gamma
    if z_w is not None and z_w < h:
        gamma_sub = gamma_prime or (gamma - gamma_w)
    else:
        gamma_sub = gamma

    # Net active below dredge: p_a(d) = p_a_dredge + Ka*gamma_sub*d + gamma_w*d (if WT below dredge)
    # + u from behind (retained side WT continues below dredge)
    u_below_coeff = gamma_w if (z_w is not None and z_w < h) else 0.0
    # Passive: p_p(d) = Kp*gamma*d  (dry passive side)

    # Moment equation (about prop at z=z_prop from top):
    # M_above = sum of blocks above dredge (pre-computed)
    blocks = _active_blocks(Ka, gamma, h, z_prop, q, z_w, gamma_prime, gamma_w)
    M_above = sum(F * arm for F, arm in blocks)

    def moment_eqn(d: float) -> float:
        """M_above + M_below_active − M_passive = 0."""
        if d <= 0.0:
            return M_above
        h_exc = h   # arm = depth_from_top − z_prop
        # Active rectangle below dredge: p_a_dredge * d
        F_rect  = p_a_dredge * d
        arm_rect = (h_exc + d / 2.0) - z_prop

        # Active + water triangle below dredge
        ka_sub_plus_u = Ka * gamma_sub + u_below_coeff
        F_tri   = 0.5 * ka_sub_plus_u * d**2
        arm_tri = (h_exc + 2.0 * d / 3.0) - z_prop

        # Passive triangle (dry)
        F_pass   = 0.5 * Kp * gamma * d**2
        arm_pass = (h_exc + 2.0 * d / 3.0) - z_prop

        M_below = F_rect * arm_rect + F_tri * arm_tri
        M_resist = F_pass * arm_pass

        return M_above + M_below - M_resist

    # Bisection (reliable for monotone-ish cubic)
    # Find sign change
    f_lo = moment_eqn(1e-6)
    d_hi = 0.5
    f_hi = moment_eqn(d_hi)
    # Expand upper bracket if needed
    for _ in range(60):
        if f_lo * f_hi < 0.0:
            break
        d_hi *= 2.0
        f_hi  = moment_eqn(d_hi)
        if d_hi > d_max:
            return d_max, False

    # Bisection
    d_lo = 1e-6
    for _ in range(_NEWTON_MAX_ITER):
        d_mid = (d_lo + d_hi) / 2.0
        f_mid = moment_eqn(d_mid)
        if abs(d_hi - d_lo) < tol:
            return d_mid, True
        if f_lo * f_mid <= 0.0:
            d_hi = d_mid
            f_hi = f_mid
        else:
            d_lo = d_mid
            f_lo = f_mid

    return (d_lo + d_hi) / 2.0, False


def _prop_force(
    Ka      : float,
    Kp      : float,
    gamma   : float,
    h       : float,
    d       : float,
    z_prop  : float = 0.0,
    q       : float = 0.0,
    z_w     : float | None = None,
    gamma_prime: float | None = None,
    gamma_w : float = GAMMA_W,
) -> float:
    """
    Prop force T from horizontal equilibrium.

    T = ΣP_active − ΣP_passive   (kN/m run)

    Positive T = compression in prop (wall being pushed against prop).

    Reference: Craig §12.2 — horizontal force equilibrium.

    :param Ka, Kp: Active/passive coefficients.
    :param gamma:  Total unit weight (kN/m³).
    :param h:      Retained height (m).
    :param d:      Embedment depth (m).
    :param z_prop: Prop depth from top (m).
    :param q:      Surcharge (kPa).
    :param z_w:    WT depth from top (m), or None.
    :param gamma_prime: Buoyant unit weight.
    :param gamma_w: Unit weight of water.
    :return: T (kN/m).
    """
    if z_w is None or z_w >= h:
        sigma_v_dredge = gamma * h
    else:
        sigma_v_dredge = gamma * z_w + (gamma_prime or (gamma - gamma_w)) * (h - z_w)

    u_dredge = gamma_w * max(0.0, h - (z_w if z_w is not None else h))
    p_a_dredge = Ka * sigma_v_dredge + u_dredge + Ka * q

    if z_w is not None and z_w < h:
        gamma_sub = gamma_prime or (gamma - gamma_w)
    else:
        gamma_sub = gamma
    u_below_coeff = gamma_w if (z_w is not None and z_w < h) else 0.0

    # Total active above dredge
    Pa_above = sum(F for F, _ in _active_blocks(Ka, gamma, h, z_prop, q, z_w, gamma_prime, gamma_w))

    # Total active below dredge
    ka_sub_plus_u = Ka * gamma_sub + u_below_coeff
    Pa_below = p_a_dredge * d + 0.5 * ka_sub_plus_u * d**2

    # Total passive
    Pp = 0.5 * Kp * gamma * d**2

    return Pa_above + Pa_below - Pp


def _max_bending_moment(
    T       : float,
    Ka      : float,
    gamma   : float,
    q       : float = 0.0,
    z_w     : float | None = None,
    gamma_prime: float | None = None,
    gamma_w : float = GAMMA_W,
) -> tuple[float, float]:
    """
    Maximum bending moment and its depth below the prop.

    The maximum BM occurs where the shear force V(z) = 0.
    Starting from the prop (z=0), moving downward:

        V(z) = T − (Ka*q*z) − (soil pressure contribution)

    For the dry case (no water table):
        V(z) = T − Ka*q*z − 0.5*Ka*γ*z²
        V=0: solve quadratic in z.

    For the WT case (z_w below prop):
        Zone 1 (z < z_w):  same as dry.
        Zone 2 (z ≥ z_w):  different gradient (buoyant + water).

    This function uses bisection on V(z)=0.

    Reference: Craig §12.2, BM diagram derivation.
    Das (2019), §11.6.

    :return: (z_Mmax, M_max) — depth below prop (m) and moment (kN·m/m).
    """
    # Choose an appropriate search depth
    z_top = 0.0
    z_bot = 50.0

    def shear(z: float) -> float:
        """Shear force at depth z below prop."""
        v = T
        # Surcharge contribution
        v -= Ka * q * z
        # Dry soil above WT (or full depth if no WT)
        z_w_eff = z_w if z_w is not None else 1e9
        if z <= z_w_eff:
            v -= 0.5 * Ka * gamma * z**2
        else:
            # Dry zone z_w_eff
            v -= 0.5 * Ka * gamma * z_w_eff**2
            # Below WT: rectangle Ka*gamma*z_w_eff*(z-z_w_eff)
            dz = z - z_w_eff
            v -= Ka * gamma * z_w_eff * dz
            # Below WT: triangle Ka*gamma_prime*(z-z_w_eff)
            gp = gamma_prime or (gamma - gamma_w)
            v -= 0.5 * Ka * gp * dz**2
            # Water pressure triangle 0.5*gamma_w*(z-z_w_eff)²
            v -= 0.5 * gamma_w * dz**2
        return v

    # Find sign change
    f_top = shear(z_top + 1e-9)
    if f_top <= 0.0:
        return 0.0, 0.0   # V≤0 immediately → no positive moment

    f_bot = shear(z_bot)
    if f_top * f_bot > 0.0:
        # No sign change; try expanding
        z_bot *= 3.0
        f_bot = shear(z_bot)
        if f_top * f_bot > 0.0:
            return z_bot / 2.0, 0.0

    # Bisect
    for _ in range(100):
        z_mid = (z_top + z_bot) / 2.0
        f_mid = shear(z_mid)
        if abs(z_bot - z_top) < 1e-8:
            break
        if f_top * f_mid <= 0.0:
            z_bot = z_mid
            f_bot = f_mid
        else:
            z_top = z_mid
            f_top = f_mid
    z_Mmax = (z_top + z_bot) / 2.0

    # Integrate shear to get BM
    M = _integrate_shear(shear, 0.0, z_Mmax)
    return z_Mmax, M


def _integrate_shear(shear_fn, z0: float, z1: float, n: int = 2000) -> float:
    """Numerically integrate shear force to get bending moment (trapezoidal rule)."""
    dz = (z1 - z0) / n
    M  = 0.0
    for i in range(n):
        za = z0 + i * dz
        zb = za + dz
        M += 0.5 * (shear_fn(za) + shear_fn(zb)) * dz
    return M


def _build_pressure_diagram(
    Ka      : float,
    Kp      : float,
    gamma   : float,
    h       : float,
    d       : float,
    z_prop  : float = 0.0,
    q       : float = 0.0,
    z_w     : float | None = None,
    gamma_prime: float | None = None,
    gamma_w : float = GAMMA_W,
    n_embed : int   = 20,
) -> list[PressurePoint]:
    """
    Build the pressure diagram for reporting.

    Depths are relative to the TOP of the retained soil.

    Key nodes: top, WT (if any), dredge level, embedded zone at n_embed points.
    """
    pts: list[PressurePoint] = []
    h_total = h + d   # from top of retained to pile toe

    def z_datum(z: float) -> float:
        return z - h   # negative above dredge, positive below

    def pa_at(z: float) -> float:
        """Active pressure at depth z from top."""
        v = Ka * q
        z_w_eff = z_w if z_w is not None else 1e9
        if z <= z_w_eff:
            v += Ka * gamma * z
        else:
            v += Ka * gamma * z_w_eff
            gp = gamma_prime or (gamma - gamma_w)
            v += Ka * gp * (z - z_w_eff)
        return v

    def u_at(z: float) -> float:
        """Pore pressure at depth z (retained side WT, passive dry)."""
        if z_w is None:
            return 0.0
        return gamma_w * max(0.0, z - z_w)

    def pp_at(z: float) -> float:
        """Passive pressure at depth z from top (only below dredge, passive side dry)."""
        if z <= h:
            return 0.0
        return Kp * gamma * (z - h)

    # Sample depths
    depths = [0.0]
    if z_w is not None and z_w < h:
        depths.append(z_w)
    depths.append(h)  # dredge level
    # Embedded zone
    for i in range(1, n_embed + 1):
        depths.append(h + i * d / n_embed)

    seen = set()
    for z in depths:
        key = round(z, 8)
        if key in seen:
            continue
        seen.add(key)
        pa  = pa_at(z)
        pp  = pp_at(z)
        u   = u_at(z)
        u_net = u  # water on retained side only (passive side dry above)
        p_net = pa - pp + u_net
        pts.append(PressurePoint(
            z=round(z, 4), z_datum=round(z_datum(z), 4),
            p_a=round(pa, 4), p_p=round(pp, 4),
            u=round(u, 4), p_net=round(p_net, 4),
        ))

    pts.sort(key=lambda p: p.z)
    return pts


# ── Public API ────────────────────────────────────────────────────────────────

def analyse_sheet_pile_da1(
    pile       : SheetPile,
    soil       : Soil,
    q          : float = 0.0,
    z_w        : float | None = None,
    gamma_w    : float = GAMMA_W,
) -> SheetPileResult:
    """
    Free-earth support analysis + EC7 DA1 verification.

    The minimum embedment depth is the larger of the DA1-C1 and DA1-C2 values.
    The governing combination governs design output (d, T, M_max).

    EC7 DA1 approach for embedded walls (§9.7.4):
      C1 (A1+M1+R1): γ_φ=1.00 → characteristic Ka, Kp; factored actions.
      C2 (A2+M2+R1): γ_φ=1.25 → factored Ka, Kp; characteristic actions.
    For cohesionless soils, C2 almost always governs the embedment depth.

    Limitations:
      • Rankine Ka/Kp only (no wall friction δ).
      • Homogeneous single-layer soil.
      • Cohesionless soil in the embedded zone (c_k ignored for passive).
      • Water table on retained side only; passive side assumed dry.
      • Prop at fixed depth z_prop from top of retained soil.

    Reference:
        Craig §12.2 — free-earth support method.
        EC7 EN 1997-1:2004, §9.7, Tables A.4/A.13.

    :param pile:    SheetPile model. Must have support='propped' or 'free'.
    :param soil:    Soil with phi_k (degrees) and gamma (kN/m³).
    :param q:       Uniform surcharge on retained surface (kPa). Default 0.
    :param z_w:     Depth to water table from top of retained soil (m).
                    None = dry analysis. Must be ≥ 0 if given.
    :param gamma_w: Unit weight of water (kN/m³). Default 9.81.
    :return:        SheetPileResult.
    :raises ValueError: If input is geometrically invalid.
    """
    # ── Validation ────────────────────────────────────────────────────────
    if soil.phi_k <= 0.0:
        raise ValueError(
            f"Free-earth support requires cohesionless soil (φ'_k > 0), "
            f"got φ'_k={soil.phi_k}"
        )
    if pile.support not in ("propped", "free"):
        raise ValueError(
            f"analyse_sheet_pile_da1 handles 'propped' or 'free' support, "
            f"got {pile.support!r}. Use 'propped' for a propped wall."
        )
    if q < 0.0:
        raise ValueError(f"Surcharge q must be ≥ 0, got {q}")
    if z_w is not None and z_w < 0.0:
        raise ValueError(f"z_w must be ≥ 0, got {z_w}")

    h       = pile.h_retained
    # z_prop in SheetPile uses the dredge-level datum (z=0 at excavation).
    # The analysis engine measures prop depth from the TOP of the retained soil.
    # Conversion: z_prop_from_top = z_prop_dredge + h_retained
    # Example: prop at top (z_prop_dredge = -h) → z_prop_from_top = 0.
    _z_prop_dredge = pile.z_prop if pile.z_prop is not None else -h
    z_prop = _z_prop_dredge + h   # depth from top of retained soil (0 = at top)
    # Ensure prop is at or above dredge
    if z_prop > h:
        raise ValueError(
            f"Prop depth ({z_prop:.2f} m from top) cannot be below excavation ({h:.2f} m)."
        )

    gamma   = soil.gamma
    phi_k   = soil.phi_k
    gamma_prime = gamma - gamma_w if z_w is not None else None

    Ka_k = ka_rankine(phi_k)
    Kp_k = kp_rankine(phi_k)

    warnings_out: list[str] = []

    # ── Solve each DA1 combination ────────────────────────────────────────
    results = []
    for label, gamma_phi in [("DA1-C1", DA1_C1_GAMMA_PHI), ("DA1-C2", DA1_C2_GAMMA_PHI)]:
        phi_d   = _design_phi(phi_k, gamma_phi)
        Ka_d    = ka_rankine(phi_d)
        Kp_d    = kp_rankine(phi_d)

        d_min, conv = _solve_embedment(
            Ka=Ka_d, Kp=Kp_d, gamma=gamma, h=h, z_prop=z_prop,
            q=q, z_w=z_w, gamma_prime=gamma_prime, gamma_w=gamma_w,
        )

        T_k = _prop_force(
            Ka=Ka_d, Kp=Kp_d, gamma=gamma, h=h, d=d_min,
            z_prop=z_prop, q=q, z_w=z_w, gamma_prime=gamma_prime, gamma_w=gamma_w,
        )

        z_M, M_max = _max_bending_moment(
            T=T_k, Ka=Ka_d, gamma=gamma, q=q,
            z_w=z_w, gamma_prime=gamma_prime, gamma_w=gamma_w,
        )

        if not conv:
            warnings_out.append(
                f"{label}: embedment solver did not converge — result may be unreliable."
            )

        results.append(SheetPileCombResult(
            label=label, gamma_phi=gamma_phi,
            phi_d_deg=phi_d, Ka_d=Ka_d, Kp_d=Kp_d,
            d_min=d_min, T_k=T_k, z_Mmax=z_M, M_max=M_max,
            converged=conv,
        ))

    comb1, comb2 = results
    # Governing = combination requiring the larger embedment
    governing = comb2 if comb2.d_min >= comb1.d_min else comb1

    # Design embedment = governing d_min (designers often add ~20–30% ULS)
    d_design = governing.d_min
    T_design  = governing.T_k
    M_max_d   = governing.M_max

    if phi_k < 20.0:
        warnings_out.append(
            f"φ'_k={phi_k:.1f}° is low; passive resistance may be unreliable. "
            f"Consider cohesive model (Sprint 11)."
        )
    if T_design < 0.0:
        warnings_out.append(
            "Negative prop force detected; the wall may be unstable without a prop. "
            "Check geometry."
        )

    # Build characteristic pressure diagram
    diagram = _build_pressure_diagram(
        Ka_k, Kp_k, gamma, h, d_design, z_prop=z_prop, q=q,
        z_w=z_w, gamma_prime=gamma_prime, gamma_w=gamma_w,
    )

    # Update pile with design embedment
    pile.d_embed  = d_design
    pile.F_prop_k = T_design

    return SheetPileResult(
        pile=pile, soil=soil,
        Ka_k=Ka_k, Kp_k=Kp_k,
        comb1=comb1, comb2=comb2,
        governing=governing,
        d_design=d_design,
        T_design=T_design,
        M_max_design=M_max_d,
        pressure_diagram=diagram,
        passes=True,
        warnings=warnings_out,
    )
