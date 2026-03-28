"""
foundation_check.py -- EC7 DA1 ULS + SLS verification for spread foundations.

Performs the complete Eurocode 7 Design Approach 1 (DA1) foundation check:

    GEO ULS (Bearing capacity):
        Vd <= Rd   where Rd = bearing_resistance_ec7(phi_d, c_d) * A_eff / gamma_Rv
        Both DA1 Combination 1 (A1+M1+R1) and Combination 2 (A2+M2+R1) must pass.

    SLS (Settlement):
        s_d = s_i + s_c <= s_lim  (design total settlement <= serviceability limit)

EC7 DA1 partial factors (Tables A.3 / A.4 / A.5):
    +-----------+---------+--------+--------+--------+--------+--------+
    | Comb      | gG_unfav| gG_fav | gQ     | g_phi  | g_c    | gR_v   |
    +-----------+---------+--------+--------+--------+--------+--------+
    | C1 A1+M1  |  1.35   |  1.00  | 1.50   |  1.00  |  1.00  |  1.00  |
    | C2 A2+M2  |  1.00   |  1.00  | 1.30   |  1.25  |  1.25  |  1.00  |
    +-----------+---------+--------+--------+--------+--------+--------+

    Resistance factor gamma_Rv = 1.00 for both combinations in R1 set.
    Note: R2 set (gRv = 1.40 for C2) is not used unless the user selects it.

Design load on foundation:
    Vd = gG_unfav * Gk_unfav + gG_fav * Gk_fav + gQ * Qk
    Here simplified to: Vd = gG * Gk + gQ * Qk  (single permanent load assumed
    unfavourable for bearing capacity).

Pass criterion (GEO ULS):
    utilisation = Vd / Rd <= 1.0  for each combination.

Reference:
    Eurocode 7 -- EN 1997-1:2004, Section 6, Tables A.3/A.4/A.5.
    Craig's Soil Mechanics, 9th ed., Chapter 8.
    Bond, A. & Harris, A. (2008). Decoding Eurocode 7, Chapters 10-11.
    Das, B.M. (2019). Principles of Geotechnical Engineering, Chapter 3.

Units:
    Forces (kN), pressures (kPa), lengths (m), settlements (m).
"""

import math
from dataclasses import dataclass, field

from models.soil       import Soil
from models.foundation import Foundation
from core.bearing_capacity import bearing_resistance_ec7, BearingResult
from core.settlement       import (
    consolidation_settlement, immediate_settlement,
    ConsolidationResult, ImmediateSettlementResult,
    S_LIM_ISOLATED,
)
from core.boussinesq import stress_below_centre


# ============================================================
#  EC7 DA1 partial factor constants  (Tables A.3 / A.4 / A.5)
# ============================================================

# Combination 1  (A1 + M1 + R1)
C1_G   : float = 1.35   # gamma_G permanent (unfavourable)
C1_Q   : float = 1.50   # gamma_Q variable
C1_PHI : float = 1.00   # gamma_phi
C1_C   : float = 1.00   # gamma_c
C1_RV  : float = 1.00   # gamma_Rv bearing resistance

# Combination 2  (A2 + M2 + R1)
C2_G   : float = 1.00
C2_Q   : float = 1.30
C2_PHI : float = 1.25
C2_C   : float = 1.25
C2_RV  : float = 1.00


# ============================================================
#  ClayLayer — input for multi-layer consolidation
# ============================================================

@dataclass
class ClayLayer:
    """
    Parameters for a single compressible clay sub-layer.

    Attributes
    ----------
    H        : Layer thickness (m).  > 0.
    Cc       : Compression index (NC branch slope).  > 0.
    e0       : Initial void ratio.  > 0.
    sigma_v0 : Initial effective vertical stress at MID-LAYER (kPa).  > 0.
    Cs       : Swelling/recompression index (OC branch).  Default 0.
    sigma_pc : Preconsolidation pressure (kPa).  None = NC clay.
    cv       : Coefficient of consolidation (m²/year).  None = no time-rate.
    label    : Optional name/identifier (e.g. 'Upper clay', 'Layer 2').

    Reference:
        Das, B.M. (2019). Principles of Geotechnical Engineering, §11.7.
        Craig's Soil Mechanics, 9th ed., §7.4.
    """
    H        : float
    Cc       : float
    e0       : float
    sigma_v0 : float
    Cs       : float       = 0.0
    sigma_pc : float | None = None
    cv       : float | None = None
    label    : str          = ""


@dataclass
class LayerConsolidationResult:
    """
    Consolidation result for one clay sub-layer with depth metadata.

    Attributes
    ----------
    layer          : The ClayLayer input.
    z_mid          : Depth to mid-layer below foundation base (m).
    delta_sigma    : Stress increase at mid-layer via Boussinesq (kPa).
    consolidation  : ConsolidationResult from settlement.py.
    t_95           : Time to 95% consolidation (years).  None if cv not given.
    """
    layer         : ClayLayer
    z_mid         : float
    delta_sigma   : float
    consolidation : ConsolidationResult
    t_95          : float | None = None


# ============================================================
#  Result containers
# ============================================================

@dataclass
class BearingCombResult:
    """
    GEO ULS bearing capacity check for one DA1 combination.

    Attributes
    ----------
    label       : 'DA1-C1' or 'DA1-C2'.
    gG, gQ      : Action partial factors applied.
    g_phi, g_c  : Material partial factors applied.
    gR_v        : Resistance partial factor applied.
    Vd          : Factored design vertical load (kN or kN/m).
    Rd          : Design bearing resistance (kN or kN/m).
    utilisation : Vd / Rd.  Must be <= 1.0 to pass.
    passes      : True if utilisation <= 1.0.
    bearing     : BearingResult (pressure/factor breakdown).
    """
    label       : str
    gG          : float
    gQ          : float
    g_phi       : float
    g_c         : float
    gR_v        : float
    Vd          : float
    Rd          : float
    utilisation : float
    passes      : bool
    bearing     : BearingResult

    def summary_line(self) -> str:
        ok = "PASS" if self.passes else "FAIL"
        return (
            f"  {self.label}  gG={self.gG:.2f}  gQ={self.gQ:.2f}"
            f"  g_phi={self.g_phi:.2f}  |"
            f"  Vd={self.Vd:.1f} kN  Rd={self.Rd:.1f} kN"
            f"  eta={self.utilisation:.3f}  [{ok}]"
        )


@dataclass
class FoundationCheckResult:
    """
    Complete EC7 DA1 foundation bearing + multi-layer settlement check.

    Attributes
    ----------
    foundation     : Foundation geometry.
    soil           : Characteristic soil used.
    Gk             : Characteristic permanent load (kN or kN/m).
    Qk             : Characteristic variable load (kN or kN/m).
    comb1          : BearingCombResult for DA1-C1.
    comb2          : BearingCombResult for DA1-C2.
    governing      : The combination with higher utilisation ratio.
    uls_passes     : True if BOTH combinations pass the GEO ULS check.
    settlement     : ConsolidationResult (single-layer, legacy).  None if multi-layer.
    s_immediate    : ImmediateSettlementResult.  None if not computed.
    layer_results  : Per-layer consolidation results (multi-layer path).  [] if single-layer.
    s_total        : Total settlement s_i + Σs_c (m).  None if not computed.
    s_lim          : Settlement serviceability limit (m).
    sls_passes     : True if s_total <= s_lim (or None if settlement not checked).
    t_95_years     : Time to 95% consolidation (years).  None if not computed.
    passes         : True if uls_passes AND (sls_passes or sls not checked).
    warnings       : Advisory messages.
    """
    foundation    : Foundation
    soil          : Soil
    Gk            : float
    Qk            : float
    comb1         : BearingCombResult
    comb2         : BearingCombResult
    governing     : BearingCombResult
    uls_passes    : bool
    settlement    : ConsolidationResult | None
    s_immediate   : ImmediateSettlementResult | None
    layer_results : list[LayerConsolidationResult] = field(default_factory=list)
    s_total       : float | None = None
    s_lim         : float = S_LIM_ISOLATED
    sls_passes    : bool | None = None
    t_95_years    : float | None = None
    passes        : bool = False
    warnings      : list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            "=" * 70,
            "  EC7 DA1 Foundation Bearing + Settlement Check",
            "-" * 70,
            f"  Foundation : {self.foundation}",
            f"  Soil       : {self.soil.name}"
            f"  phi_k={self.soil.phi_k:.1f}  c_k={self.soil.c_k:.1f} kPa"
            f"  gamma={self.soil.gamma:.1f} kN/m3",
            f"  Loading    : Gk={self.Gk:.1f} kN  Qk={self.Qk:.1f} kN",
            "-" * 70,
            "  GEO ULS Bearing Capacity:",
            self.comb1.summary_line(),
            self.comb2.summary_line(),
            "-" * 70,
            f"  Governing  : {self.governing.label}"
            f"  (utilisation = {self.governing.utilisation:.3f})",
        ]

        if self.s_total is not None:
            sls_str = "PASS" if self.sls_passes else "FAIL"
            si_mm   = self.s_immediate.s_i * 1000 if self.s_immediate else 0.0
            sc_mm   = (self.s_total - (self.s_immediate.s_i if self.s_immediate else 0.0)) * 1000
            lines += [
                "-" * 70,
                f"  SLS Settlement breakdown:",
                f"    s_immediate       = {si_mm:.1f} mm",
                f"    s_consolidation   = {sc_mm:.1f} mm"
                + (f"  ({len(self.layer_results)} layers)" if self.layer_results else ""),
                f"    s_total           = {self.s_total*1000:.1f} mm",
                f"    SLS limit         = {self.s_lim*1000:.1f} mm  [{sls_str}]",
            ]
            if self.t_95_years is not None:
                lines.append(f"    t_95 consolidation = {self.t_95_years:.2f} years")

        uls_str  = "PASS" if self.uls_passes else "FAIL"
        overall  = "PASS" if self.passes else "FAIL"
        lines += [
            "-" * 70,
            f"  ULS Bearing : {uls_str}   Overall : {overall}",
            "=" * 70,
        ]
        if self.warnings:
            lines.insert(-1, f"  WARNING: {len(self.warnings)} advisory message(s) -- see .warnings")
        return "\n".join(lines)


# ============================================================
#  Private helpers
# ============================================================

def _design_phi(phi_k: float, g_phi: float) -> float:
    """Design friction angle per EC7 §2.4.6.2: phi_d = arctan(tan(phi_k)/g_phi)."""
    return math.degrees(math.atan(math.tan(math.radians(phi_k)) / g_phi))


def _design_c(c_k: float, g_c: float) -> float:
    """Design cohesion per EC7 §2.4.6.2: c_d = c_k / g_c."""
    return c_k / g_c


def _run_combination(
    label      : str,
    foundation : Foundation,
    soil       : Soil,
    Gk         : float,
    Qk         : float,
    Hk         : float,
    gG         : float,
    gQ         : float,
    g_phi      : float,
    g_c        : float,
    gR_v       : float,
) -> BearingCombResult:
    """Runs one DA1 combination and returns BearingCombResult."""
    phi_d = _design_phi(soil.phi_k, g_phi)
    c_d   = _design_c(soil.c_k,   g_c)

    Vd = gG * Gk + gQ * Qk
    Hd = gG * Hk   # horizontal treated as permanent here (conservative)

    br = bearing_resistance_ec7(
        foundation  = foundation,
        phi_d       = phi_d,
        c_d         = c_d,
        gamma_soil  = soil.gamma,
        V           = Vd if Hd > 0 else None,
        H           = Hd,
    )

    Rd          = br.R_ult / gR_v
    utilisation = Vd / max(Rd, 1e-9)
    passes      = utilisation <= 1.0

    return BearingCombResult(
        label       = label,
        gG          = gG,
        gQ          = gQ,
        g_phi       = g_phi,
        g_c         = g_c,
        gR_v        = gR_v,
        Vd          = Vd,
        Rd          = Rd,
        utilisation = utilisation,
        passes      = passes,
        bearing     = br,
    )


# ============================================================
#  Public API
# ============================================================

def multi_layer_consolidation_settlement(
    foundation  : Foundation,
    q_net       : float,
    clay_layers : list[ClayLayer],
    z_top       : float = 0.0,
) -> list[LayerConsolidationResult]:
    """
    Consolidation settlement for a stack of clay sub-layers using
    Boussinesq stress distribution (Fadum 1948) at each layer mid-point.

    For each layer the stress increase Δσ_v at the mid-layer depth is
    computed using stress_below_centre() from boussinesq.py, which applies
    the Fadum (1948) influence factor for a uniformly loaded rectangle.

    This replaces the conservative 2:1 stress approximation used in the
    legacy single-layer path, giving more accurate settlement predictions
    for deep or stiff soil profiles.

    Formula per layer (Craig §7.4 / Das §11.7):

        z_mid = z_top + H/2
        Δσ_v  = stress_below_centre(q_net, B, L, z_mid)   [Boussinesq]

        For NC clay (sigma_v0 < sigma_pc or sigma_pc is None):
            s_c = (Cc / (1+e0)) * H * log10((sigma_v0 + Δσ_v) / sigma_v0)

        For OC clay (Δσ pushes past sigma_pc):
            s_c = Cs/(1+e0) * H * log10(sigma_pc / sigma_v0)
                + Cc/(1+e0) * H * log10((sigma_v0 + Δσ_v) / sigma_pc)

        t_95 = T_v * H_dr² / cv    (Terzaghi, U=0.95 → T_v=1.129)

    Reference:
        Craig's Soil Mechanics, 9th ed., §7.4 (layered consolidation).
        Das, B.M. (2019). Principles of Geotechnical Engineering, §11.7.
        Fadum, R.E. (1948). Proc. 2nd ICSMFE, Vol. 3 (influence factors).

    :param foundation:   Foundation geometry — B and L used for Boussinesq.
    :param q_net:        Net applied pressure at foundation level (kPa).
    :param clay_layers:  Ordered list of ClayLayer objects, shallowest first.
    :param z_top:        Depth to top of first layer below foundation base (m).
                         Default 0 (layer immediately below foundation).
    :return:             List of LayerConsolidationResult, one per layer.
    :raises ValueError:  If clay_layers is empty or any layer has H <= 0.
    """
    if not clay_layers:
        raise ValueError("clay_layers must not be empty.")
    for i, lay in enumerate(clay_layers):
        if lay.H <= 0:
            raise ValueError(f"Layer {i} has H={lay.H} <= 0.")

    B = foundation.B_eff or foundation.B
    L = foundation.L_eff or None   # None → strip (very large L)

    results: list[LayerConsolidationResult] = []
    z_cursor = z_top

    for lay in clay_layers:
        z_mid = z_cursor + lay.H / 2.0

        # Boussinesq stress at layer mid-point (Fadum 1948)
        if L is None:
            # Strip footing: use large-L approximation (L = 50*B)
            L_bouss = B * 50.0
        else:
            L_bouss = L

        delta_sigma = stress_below_centre(q_net, B, L_bouss, z_mid)

        # Consolidation settlement for this layer
        consol = consolidation_settlement(
            H          = lay.H,
            Cc         = lay.Cc,
            e0         = lay.e0,
            sigma_v0   = lay.sigma_v0,
            delta_sigma= delta_sigma,
            Cs         = lay.Cs,
            sigma_pc   = lay.sigma_pc,
        )

        # Time to 95% consolidation for this layer (if cv given)
        t_95 = None
        if lay.cv is not None and lay.cv > 0:
            from core.settlement import time_to_consolidation
            H_dr  = lay.H / 2.0   # double drainage assumed
            t_res = time_to_consolidation(U=0.95, H_dr=H_dr, cv=lay.cv)
            t_95  = t_res.t

        results.append(LayerConsolidationResult(
            layer        = lay,
            z_mid        = z_mid,
            delta_sigma  = delta_sigma,
            consolidation= consol,
            t_95         = t_95,
        ))

        z_cursor += lay.H

    return results


def check_foundation_da1(
    foundation       : Foundation,
    soil             : Soil,
    Gk               : float,
    Qk               : float                       = 0.0,
    Hk               : float                       = 0.0,
    consolidation    : ConsolidationResult | None  = None,
    s_immediate_res  : ImmediateSettlementResult | None = None,
    clay_layers      : list[ClayLayer] | None      = None,
    s_lim            : float                       = S_LIM_ISOLATED,
) -> FoundationCheckResult:
    """
    EC7 DA1 foundation bearing capacity (GEO ULS) + full settlement (SLS) check.

    Supports three settlement paths (in order of precedence):
        1. Multi-layer (clay_layers supplied):
           - Boussinesq stress at each layer mid-point (Fadum 1948).
           - s_c = Σ consolidation_settlement(layer_i).
           - t_95 = max(t_95 per layer) — governing (largest drainage path).
        2. Single-layer (consolidation pre-computed externally):
           - Legacy path; consolidation ConsolidationResult passed directly.
        3. Immediate only (neither of the above):
           - s_total = s_i; no consolidation component.

    Immediate settlement (s_immediate_res) is combined with whichever
    consolidation path is active:  s_total = s_i + s_c.

    :param foundation:      Foundation geometry (Foundation object).
    :param soil:            Characteristic bearing soil (Soil object).
    :param Gk:              Characteristic permanent vertical load (kN or kN/m).
    :param Qk:              Characteristic variable vertical load (kN or kN/m).
    :param Hk:              Characteristic horizontal load (kN or kN/m).
    :param consolidation:   Pre-computed ConsolidationResult (single-layer legacy path).
    :param s_immediate_res: Pre-computed ImmediateSettlementResult.
    :param clay_layers:     List of ClayLayer for multi-layer Boussinesq path.
                            Overrides single-layer `consolidation` if both supplied.
    :param s_lim:           SLS settlement limit (m). Default 0.025 m (25 mm).
    :return:                FoundationCheckResult with full breakdown.
    :raises ValueError:     If Gk <= 0, Qk < 0, or layer geometry invalid.

    Reference:
        EC7 §6.6 (SLS). Craig §7.4. Das §11.7. Fadum (1948).
    """
    warnings: list[str] = []

    if Gk <= 0:
        raise ValueError(f"Gk must be > 0 (self-weight), got {Gk}")
    if Qk < 0:
        raise ValueError(f"Qk must be >= 0, got {Qk}")
    if Hk < 0:
        raise ValueError(f"Hk must be >= 0, got {Hk}")

    # ── DA1 Combination 1  (A1 + M1 + R1) ────────────────────────────────
    comb1 = _run_combination(
        "DA1-C1", foundation, soil, Gk, Qk, Hk,
        gG=C1_G, gQ=C1_Q, g_phi=C1_PHI, g_c=C1_C, gR_v=C1_RV,
    )

    # ── DA1 Combination 2  (A2 + M2 + R1) ────────────────────────────────
    comb2 = _run_combination(
        "DA1-C2", foundation, soil, Gk, Qk, Hk,
        gG=C2_G, gQ=C2_Q, g_phi=C2_PHI, g_c=C2_C, gR_v=C2_RV,
    )

    governing  = comb1 if comb1.utilisation >= comb2.utilisation else comb2
    uls_passes = comb1.passes and comb2.passes

    # ── Settlement SLS — resolve active path ──────────────────────────────
    s_total     : float | None = None
    sls_passes  : bool  | None = None
    layer_res   : list[LayerConsolidationResult] = []
    t_95_years  : float | None = None
    active_consol : ConsolidationResult | None = consolidation  # legacy default

    if clay_layers:
        # Path 1: multi-layer Boussinesq (Sprint 5)
        # q_net for SLS uses characteristic (unfactored) loads — EC7 §6.6.1
        A_ref  = foundation.A_eff if foundation.A_eff else foundation.B
        q_net  = (Gk + Qk) / max(A_ref, 1e-9)

        layer_res = multi_layer_consolidation_settlement(
            foundation  = foundation,
            q_net       = q_net,
            clay_layers = clay_layers,
        )
        s_c_total    = sum(lr.consolidation.s_c for lr in layer_res)
        active_consol = None   # superseded by layer_res

        # Governing t_95 = worst layer (maximum time)
        t95_vals = [lr.t_95 for lr in layer_res if lr.t_95 is not None]
        if t95_vals:
            t_95_years = max(t95_vals)

        if s_immediate_res is not None or s_c_total > 0:
            s_i     = s_immediate_res.s_i if s_immediate_res else 0.0
            s_total = s_i + s_c_total
            sls_passes = s_total <= s_lim

    elif consolidation is not None or s_immediate_res is not None:
        # Path 2 / 3: single-layer or immediate-only (legacy)
        s_c = consolidation.s_c if consolidation is not None else 0.0
        s_i = s_immediate_res.s_i if s_immediate_res is not None else 0.0
        s_total    = s_i + s_c
        sls_passes = s_total <= s_lim

    if sls_passes is not None and not sls_passes:
        warnings.append(
            f"SLS settlement EXCEEDED: s_total={s_total*1000:.1f} mm > "  # type: ignore[operator]
            f"s_lim={s_lim*1000:.1f} mm."
        )

    if not uls_passes:
        warnings.append(
            "GEO ULS bearing capacity FAILED.  Increase foundation dimensions, "
            "embedment depth, or improve soil conditions."
        )

    passes = uls_passes and (sls_passes is None or sls_passes)

    return FoundationCheckResult(
        foundation    = foundation,
        soil          = soil,
        Gk            = Gk,
        Qk            = Qk,
        comb1         = comb1,
        comb2         = comb2,
        governing     = governing,
        uls_passes    = uls_passes,
        settlement    = active_consol,
        s_immediate   = s_immediate_res,
        layer_results = layer_res,
        s_total       = s_total,
        s_lim         = s_lim,
        sls_passes    = sls_passes,
        t_95_years    = t_95_years,
        passes        = passes,
        warnings      = warnings,
    )
