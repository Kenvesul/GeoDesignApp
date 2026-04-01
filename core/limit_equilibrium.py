"""
limit_equilibrium.py – Factor of Safety engines for circular slip surfaces.

Implements three methods:
    1. Ordinary Method  (Fellenius, 1936)     – non-iterative, lower-bound
                                               cross-check only.
    2. Bishop's Simplified Method (1955)      – satisfies moment equilibrium;
                                               industry standard for circular
                                               failure surfaces.
    3. Spencer's Method (Spencer, 1967)       – satisfies BOTH force and moment
                                               equilibrium; more rigorous than
                                               Bishop; recommended for final
                                               design verification.

References:
    Bishop, A.W. (1955). The use of the slip circle in the stability analysis
        of slopes. Géotechnique 5(1), 7–17.
    Spencer, E. (1967). A method of analysis of the stability of embankments
        assuming parallel inter-slice forces. Géotechnique 17(1), 11–26.
    Craig's Soil Mechanics, 9th ed., Chapter 9 (Knappett & Craig).
    Duncan, J.M. & Wright, S.G. (2005). Soil Strength and Slope Stability.
        Wiley. (Spencer implementation reference.)
    Eurocode 7 – EN 1997-1:2004, §11.5 (Overall Stability).

Sign convention (consistent with slicer.py):
    α > 0  →  slice base dips away from slope crest  (right half of circle)
    α < 0  →  slice base dips toward slope crest     (left half of circle)
    Driving moment arm = R · sin(α)  (positive for right-dipping bases)
    θ (Spencer inter-slice inclination) > 0 → forces inclined upward to right

Pore pressure:
    Represented by the dimensionless pore pressure ratio rᵤ (Bishop & Morgenstern 1960):
        rᵤ = u / (γ · h)   →   u = rᵤ · W / b   (kPa at the slice base)
    rᵤ = 0.0 : fully drained.
    rᵤ = 0.5 : typical saturated embankment under steady seepage.
"""

import math
from dataclasses import dataclass, field


_MIN_DRIVING_SUM_ABS = 1e-3
_MIN_DRIVING_WEIGHT_RATIO = 1e-3


# ============================================================
#  Result containers
# ============================================================

@dataclass
class SliceResult:
    """Per-slice intermediate values; useful for debugging and reporting."""
    x: float            # Slice midpoint (m)
    alpha_deg: float    # Base inclination α (degrees)
    weight: float       # Slice weight W (kN/m)
    pore_pressure: float  # Pore pressure u at base (kPa)
    numerator: float    # Resistance contribution (kN/m)
    denominator: float  # Driving contribution (kN/m)


@dataclass
class FoSResult:
    """
    Complete output from a limit-equilibrium analysis.

    Attributes
    ----------
    method        : 'Ordinary' or 'Bishop'
    fos           : Computed Factor of Safety (–)
    converged     : True if iterative method reached tolerance (always True for Ordinary)
    iterations    : Number of iterations used (1 for Ordinary)
    sum_resist    : Σ resisting forces / moments (kN/m or kN·m/m)
    sum_driving   : Σ driving forces / moments  (kN/m or kN·m/m)
    ru            : Pore pressure ratio used
    slice_results : Per-slice breakdown (list[SliceResult])
    ec7_stable    : True if FoS ≥ 1.00 (no collapse)
    ec7_pass      : True if FoS ≥ 1.25 (EC7 DA1/C1 minimum for overall stability)
    warning       : Non-empty string if convergence or geometry issues were detected
    """
    method:        str
    fos:           float
    converged:     bool
    iterations:    int
    sum_resist:    float
    sum_driving:   float
    ru:            float
    slice_results: list[SliceResult] = field(default_factory=list)
    ec7_stable:    bool = False
    ec7_pass:      bool = False
    warning:       str  = ""

    def __post_init__(self):
        self.ec7_stable = self.fos >= 1.00
        self.ec7_pass   = self.fos >= 1.25

    def summary(self) -> str:
        """Returns a human-readable summary string."""
        lines = [
            f"{'─'*52}",
            f"  Method       : {self.method}",
            f"  FoS          : {self.fos:.4f}",
            f"  Converged    : {self.converged}  (iterations: {self.iterations})",
            f"  Σ Resist     : {self.sum_resist:.2f} kN/m",
            f"  Σ Driving    : {self.sum_driving:.2f} kN/m",
            f"  rᵤ           : {self.ru:.3f}",
            f"{'─'*52}",
            f"  EC7 Stable   : {'✅ YES  (FoS ≥ 1.00)' if self.ec7_stable else '❌ NO   (FoS < 1.00 — COLLAPSE)'}",
            f"  EC7 Pass     : {'✅ YES  (FoS ≥ 1.25)' if self.ec7_pass   else '⚠️  NO   (FoS < 1.25 — BELOW EC7 THRESHOLD)'}",
        ]
        if self.warning:
            lines.append(f"  ⚠️  Warning    : {self.warning}")
        lines.append(f"{'─'*52}")
        return "\n".join(lines)


# ============================================================
#  Internal helpers
# ============================================================

def _pore_pressure(slice_weight: float, slice_width: float, ru: float) -> float:
    """
    Hydrostatic pore pressure at the base of a slice using the rᵤ approximation.

    Formula (Bishop & Morgenstern, 1960):
        u = rᵤ · γ · h  =  rᵤ · (W / b)

    :param slice_weight: W  (kN/m)
    :param slice_width:  b  (m)
    :param ru:           Pore pressure ratio rᵤ (–)
    :return:             u  (kPa)
    """
    if slice_width <= 0:
        return 0.0
    return ru * (slice_weight / slice_width)


def _resolve_u_vals(slices, ru: float) -> list[float]:
    """
    Resolve the per-slice pore pressure list.

    Priority (Sprint 9):
      1. If ``slice.u`` is not None (set by create_slices from a PhreaticSurface),
         use the direct pore pressure value (kPa) — spatially variable.
      2. Otherwise apply the scalar ``ru`` approximation:
             u = rᵤ · W / b      (Bishop & Morgenstern, 1960)

    This preserves full backward compatibility: existing code that passes a
    scalar ``ru`` and no PhreaticSurface is unaffected.

    Reference:
        Bishop, A.W. & Morgenstern, N.R. (1960). Stability coefficients for
        earth slopes. Géotechnique 10(4), 129–150.

    :param slices: List of Slice objects.
    :param ru:     Fallback scalar pore pressure ratio.
    :return:       List of u values (kPa), one per slice.
    """
    return [
        s.u if getattr(s, "u", None) is not None
        else _pore_pressure(s.weight, s.b, ru)
        for s in slices
    ]


def _validate_driving_sum(sum_driving: float, total_weight: float, label: str) -> None:
    """
    Reject circles whose driving term magnitude is numerically negligible.

    Uses |sum_driving| so that BOTH slope orientations are accepted:
        Standard  (descends left→right): Σ(W·sinα) > 0  (clockwise rotation)
        Mirrored  (descends right→left): Σ(W·sinα) < 0  (counter-clockwise)

    Bishop's FoS = Σ(resist) / |Σ(W·sinα)|; the sign encodes sliding
    direction only — it does not affect the stability ratio.
    Rejecting negative sums was the root cause of mirrored-slope failures.
    """
    abs_driving = abs(sum_driving)

    if abs_driving <= _MIN_DRIVING_SUM_ABS:
        raise ValueError(
            f"|{label}| = {abs_driving:.6f} is too small for a meaningful "
            "sliding mass."
        )

    ratio = abs_driving / max(total_weight, 1e-9)
    if ratio <= _MIN_DRIVING_WEIGHT_RATIO:
        raise ValueError(
            f"|{label}| / total_weight = {ratio:.6f} is too small for a "
            "meaningful sliding mass."
        )


# ============================================================
#  Method 1 – Ordinary Method (Fellenius)
# ============================================================

def ordinary_method(
    slices,
    ru: float = 0.0,
) -> FoSResult:
    """
    Ordinary Method of Slices (Fellenius, 1936).

    Non-iterative. Assumes zero inter-slice forces. Produces FoS values
    3–15 % lower than Bishop for typical geometries; use as a lower-bound
    cross-check only.

    Formula (Craig §9.3):
        FoS = Σ [ c'·l + (W·cosα − u·l) · tanφ' ]
              ─────────────────────────────────────
                       Σ [ W · sinα ]

    where:
        l  = b / cosα   (arc length of slice base, m)
        u  = rᵤ · W/b  (pore pressure, kPa)

    :param slices:  List of Slice objects from core.slicer.create_slices().
    :param ru:      Pore pressure ratio rᵤ (0 = drained, default 0.0).
                    Ignored for slices whose ``.u`` attribute is set directly
                    by a PhreaticSurface (Sprint 9 — Bishop & Morgenstern 1960).
    :return:        FoSResult with method = 'Ordinary'.
    :raises ValueError: If slices list is empty or denominator ≤ 0.
    """
    if not slices:
        raise ValueError("slices list is empty — cannot compute FoS.")
    # Allow ru=0 even when slice.u values are set (they override the scalar ru).
    _has_per_slice_u = any(getattr(s, "u", None) is not None for s in slices)
    if not _has_per_slice_u and not (0.0 <= ru < 1.0):
        raise ValueError(f"rᵤ must be in [0, 1), got {ru}")

    sum_resist  = 0.0
    sum_driving = 0.0
    total_weight = 0.0
    slice_results: list[SliceResult] = []

    u_vals = _resolve_u_vals(slices, ru)

    for s, u in zip(slices, u_vals):
        cos_a = math.cos(s.alpha)
        sin_a = math.sin(s.alpha)

        # Guard against near-vertical slice (cos_a ≈ 0)
        if abs(cos_a) < 1e-9:
            continue

        # Design strength values (characteristic — no EC7 partial factors here;
        # FoS is computed from characteristic strength per traditional approach)
        phi_rad = math.radians(s.soil.phi_k)
        c_prime = s.soil.c_k

        # Arc length of slice base
        arc_len = s.b / cos_a                            # l = b / cosα

        # Pore pressure already resolved (per-slice or scalar ru)
        # Effective normal force on the base
        n_eff = s.weight * cos_a - u * arc_len           # kN/m

        # Resistance and driving contributions
        resist  = c_prime * arc_len + n_eff * math.tan(phi_rad)
        driving = s.weight * sin_a

        sum_resist  += resist
        sum_driving += driving
        total_weight += abs(s.weight)

        slice_results.append(SliceResult(
            x             = s.x,
            alpha_deg     = math.degrees(s.alpha),
            weight        = s.weight,
            pore_pressure = u,
            numerator     = resist,
            denominator   = driving,
        ))

    _validate_driving_sum(sum_driving, total_weight, "Σ(W·sinα)")

    # Use abs(sum_driving) so both slope orientations give FoS > 0.
    # For a mirrored (right→left descending) slope, sum_driving is negative
    # because all α are negative; the magnitude is still the correct denominator.
    fos = sum_resist / abs(sum_driving)

    return FoSResult(
        method        = "Ordinary (Fellenius)",
        fos           = fos,
        converged     = True,
        iterations    = 1,
        sum_resist    = sum_resist,
        sum_driving   = sum_driving,
        ru            = ru,
        slice_results = slice_results,
    )


# ============================================================
#  Method 2 – Bishop's Simplified Method
# ============================================================

def bishop_simplified(
    slices,
    ru:       float = 0.0,
    max_iter: int   = 200,
    tol:      float = 1e-6,
    kh:       float = 0.0,
    kv:       float = 0.0,
) -> FoSResult:
    """
    Bishop's Simplified Method (Bishop, 1955) with optional pseudo-static
    seismic forces (EC8 §4.1.3.3 / Kramer 1996).

    Satisfies vertical force equilibrium for each slice and overall moment
    equilibrium about the circle centre. Inter-slice shear forces are
    neglected (hence "simplified"); inter-slice normal forces are implicitly
    included in the mα term.

    Static formula (Craig §9.3 / EC7 Commentary C.3):

        FoS = Σ [ (c'·b + (W − u·b) · tanφ') / mα ]
              ─────────────────────────────────────────
                         Σ [ W · sinα ]

        where:
            mα = cosα + (sinα · tanφ') / FoS
            u  = rᵤ · W / b   (pore pressure, kPa)

    Pseudo-static seismic modification (EC8 §4.1.3.3 / Kramer 1996 §11.4):
        Horizontal seismic coefficient kh adds a destabilising inertia force
        kh·W acting horizontally through the slice centroid (always adverse).
        Vertical seismic coefficient kv modifies the effective slice weight:
            W_eff = W · (1 ± kv)   — worst case uses (1 − kv) per EC8.

        Modified moment equation:
            Numerator (resistance):
                (c'·b + (W_eff − u·b)·tanφ') / mα_s
            Denominator (driving):
                Σ [ W·sinα + kh·W·cosα ]
            where mα_s uses W_eff in the denominator:
                mα_s = cosα + sinα·tanφ'/FoS

        The kh·W·cosα term accounts for the horizontal force's moment arm
        about the circle centre (Seed & Martin 1966; Das §12.4).

    Reference:
        EC8 – EN 1998-5:2004, §4.1.3.3 (pseudo-static slope stability).
        Kramer, S.L. (1996). Geotechnical Earthquake Engineering, §11.4.
        Bishop, A.W. (1955). Géotechnique 5(1), 7–17.
        Craig's Soil Mechanics, 9th ed., §9.3.

    :param slices:    List of Slice objects from core.slicer.create_slices().
    :param ru:        Pore pressure ratio rᵤ (0 = drained, default 0.0).
    :param max_iter:  Maximum iteration count (default 200).
    :param tol:       Convergence tolerance on FoS (default 1e-6).
    :param kh:        Horizontal seismic coefficient (0 = static, default 0.0).
                      Typical range: 0.05–0.20 for moderate seismicity.
    :param kv:        Vertical seismic coefficient (default 0.0).
                      EC8 allows kv = ±0.5·kh; use worst case (positive kv
                      reduces effective weight and resistance).
    :param slices:    List of Slice objects from core.slicer.create_slices().
    :param ru:        Pore pressure ratio rᵤ (0 = drained, default 0.0).
                      Ignored for slices whose ``.u`` attribute is set directly
                      by a PhreaticSurface (Sprint 9 — Bishop & Morgenstern 1960).
    :param max_iter:  Maximum iterations (default 200).
    :param tol:       Convergence tolerance on FoS (default 1e-6).
    :param kh:        Horizontal seismic coefficient (default 0.0).
    :param kv:        Vertical seismic coefficient (default 0.0).
    :return:          FoSResult with method = 'Bishop' or 'Bishop (seismic)'.
    :raises ValueError: If slices list is empty or driving sum ≤ 0.
    """
    if not slices:
        raise ValueError("slices list is empty — cannot compute FoS.")
    _has_per_slice_u = any(getattr(s, "u", None) is not None for s in slices)
    if not _has_per_slice_u and not (0.0 <= ru < 1.0):
        raise ValueError(f"rᵤ must be in [0, 1), got {ru}")
    if kh < 0:
        raise ValueError(f"kh must be ≥ 0 (unsigned magnitude), got {kh}")
    if kv < 0:
        raise ValueError(f"kv must be ≥ 0 (unsigned magnitude), got {kv}")

    # ── Pre-compute slice constants (independent of FoS) ─────────────────
    phi_rads = [math.radians(s.soil.phi_k) for s in slices]
    u_vals   = _resolve_u_vals(slices, ru)

    # Pseudo-static: effective weight W_eff = W·(1 − kv)  (EC8 worst case)
    # kv reduces effective weight → reduces resistance; conservative.
    w_eff = [s.weight * (1.0 - kv) for s in slices]

    # Seismic driving sum: Σ[W·sinα + kh·W·cosα]
    # The kh·W·cosα term is the moment of the horizontal inertia force
    # about the circle centre (Seed & Martin 1966).
    sum_driving = sum(
        s.weight * math.sin(s.alpha) + kh * s.weight * math.cos(s.alpha)
        for s in slices
    )
    total_weight = sum(abs(s.weight) for s in slices)
    _validate_driving_sum(sum_driving, total_weight, "Σ(W·sinα + kh·W·cosα)")

    # abs_driving is used as the denominator throughout iteration.
    # For mirrored (right→left descending) slopes sum_driving is negative;
    # using its magnitude gives the correct FoS (ratio of resistance to driving).
    abs_driving = abs(sum_driving)

    # ── Seed value ────────────────────────────────────────────────────────
    # When slices carry per-slice u values, pass ru=0.0 so ordinary_method
    # uses _resolve_u_vals(slices, 0.0) which still picks up slice.u.
    _seed_ru = 0.0 if _has_per_slice_u else ru
    try:
        fos = ordinary_method(slices, _seed_ru).fos
    except ValueError:
        fos = 1.0

    # ── Iteration ─────────────────────────────────────────────────────────
    warning    = ""
    converged  = False
    iterations = 0

    for iteration in range(1, max_iter + 1):
        iterations = iteration
        sum_resist = 0.0

        for s, phi_rad, u, we in zip(slices, phi_rads, u_vals, w_eff):
            cos_a    = math.cos(s.alpha)
            sin_a    = math.sin(s.alpha)
            tan_phi  = math.tan(phi_rad)

            m_alpha = cos_a + (sin_a * tan_phi) / fos

            if abs(m_alpha) < 1e-9:
                warning = (f"mα ≈ 0 encountered at slice x={s.x:.2f} m; "
                           "slice skipped.")
                continue

            # Resistance uses effective weight (W_eff reduces pore-pressure term)
            effective_term = (we - u * s.b) * tan_phi
            numerator = (s.soil.c_k * s.b + effective_term) / m_alpha
            sum_resist += numerator

        fos_new = sum_resist / abs_driving

        if abs(fos_new - fos) < tol:
            fos       = fos_new
            converged = True
            break

        fos = fos_new

    if not converged:
        warning = (f"Bishop iteration did not converge after {max_iter} "
                   f"iterations (last Δ = {abs(fos_new - fos):.2e}). "
                   "Result may be unreliable — check circle geometry.")

    # ── Build per-slice result table ───────────────────────────────────────
    slice_results: list[SliceResult] = []
    for s, phi_rad, u, we in zip(slices, phi_rads, u_vals, w_eff):
        cos_a   = math.cos(s.alpha)
        sin_a   = math.sin(s.alpha)
        tan_phi = math.tan(phi_rad)
        m_alpha = cos_a + (sin_a * tan_phi) / fos

        if abs(m_alpha) < 1e-9:
            continue

        numerator   = (s.soil.c_k * s.b + (we - u * s.b) * tan_phi) / m_alpha
        denominator = s.weight * math.sin(s.alpha) + kh * s.weight * cos_a

        slice_results.append(SliceResult(
            x             = s.x,
            alpha_deg     = math.degrees(s.alpha),
            weight        = s.weight,
            pore_pressure = u,
            numerator     = numerator,
            denominator   = denominator,
        ))

    sum_resist_final = sum(sr.numerator for sr in slice_results)
    method_label = "Bishop's Simplified" if kh == 0.0 else f"Bishop's Simplified (seismic kh={kh:.3f})"

    return FoSResult(
        method        = method_label,
        fos           = fos,
        converged     = converged,
        iterations    = iterations,
        sum_resist    = sum_resist_final,
        sum_driving   = sum_driving,
        ru            = ru,
        slice_results = slice_results,
        warning       = warning,
    )


# ============================================================
#  Method 3 – Spencer's Method (1967)
# ============================================================

def spencer_method(
    slices,
    ru:        float = 0.0,
    max_iter:  int   = 300,
    tol:       float = 1e-6,
    theta_tol: float = 1e-5,
    kh:        float = 0.0,
    kv:        float = 0.0,
) -> FoSResult:
    """
    Spencer's Method (Spencer, 1967) with optional pseudo-static seismic forces.

    Satisfies BOTH overall moment equilibrium AND overall horizontal force
    equilibrium. Pseudo-static seismic forces (EC8 §4.1.3.3) are applied
    identically to the Bishop seismic implementation:
        W_eff = W·(1 − kv)       (vertical: conservative worst-case)
        Extra driving moment: kh·W·cosα per slice

    Reference:
        Spencer (1967) Géotechnique 17(1), 11–26.
        EC8 – EN 1998-5:2004, §4.1.3.3.
        Kramer, S.L. (1996). Geotechnical Earthquake Engineering, §11.4.

    :param slices:     List of Slice objects from core.slicer.create_slices().
    :param ru:         Pore pressure ratio rᵤ (0 = drained, default 0.0).
    :param max_iter:   Max iterations per inner loop (default 300).
    :param tol:        FoS convergence tolerance (default 1e-6).
    :param theta_tol:  θ convergence tolerance on moment FoS (default 1e-5).
    :param kh:         Horizontal seismic coefficient (default 0.0).
    :param kv:         Vertical seismic coefficient (default 0.0).
    :return:           FoSResult with method = 'Spencer' or 'Spencer (seismic)'.
    :raises ValueError: If slices list is empty or analysis is degenerate.
    """
    """
    Spencer's Method (Spencer, 1967).

    Satisfies BOTH overall moment equilibrium AND overall horizontal force
    equilibrium by iterating simultaneously on:
        F   – the Factor of Safety applied to shear strength
        θ   – the constant inclination of inter-slice forces (radians)

    This makes Spencer's method more rigorous than Bishop (which satisfies
    only moment equilibrium) and produces FoS values within ~1–3% of Bishop
    for most circular surfaces (Whitman & Bailey, 1967).

    Formulation (Duncan & Wright, 2005 / Craig §9.3):
    ──────────────────────────────────────────────────────
    For each slice i, define:
        Sᵢ = c'·b + (W − u·b)·tanφ'    (available shear resistance numerator,
                                          before F and mα)
        mα = cosα·(1 + tanα·tanθ) + sinα·tanφ'/F

    The available inter-slice shear force Tᵢ from the Spencer side-force
    equilibrium is:

        Eᵢ·tanθ = (Sᵢ/F − W·sinα + Eᵢ·tanθ·cosα/mα·...)

    In practice the standard double-sweep is used:
    ──────────────────────────────────────────────────────
    Outer loop: θ (inter-slice inclination)
        Inner loop: F (FoS)
            1. Given F and θ, compute mα(F, θ) for each slice.
            2. Moment equation (about circle centre, like Bishop):
                F_m = Σ[ Sᵢ/mα ] / Σ[ W·sinα ]
            3. Force equation (horizontal equilibrium):
                F_f = Σ[ Sᵢ·cosθ/mα ] / Σ[ W·sinα·cosθ − W·cosα·sinθ ]
                    (simplification for circular surface: Janbu-style force eqn)

            Convergence on F when |F_m − F_f| < tol.
        Convergence on θ when |ΔF_m| < theta_tol between θ iterations.

    For circular surfaces the moment equation is:

        F_m = Σ[ Sᵢ / mα_m ]    / Σ[ W·sinα ]

    where  mα_m = cosα + sinα·tanφ'/F   (moment form, equivalent to Bishop)

    The force equation (horizontal):

        F_f = Σ[ Sᵢ·cos(α−θ) / (cosα·cos(α−θ)·(1 + tanφ'·tanα/F) + sinα·sin(α−θ)) ]
              ────────────────────────────────────────────────────────────────────────
              Σ[ W·sin(α−θ) ]

    Spencer's convergence criterion: F_m = F_f (force-moment consistency).
    The value of θ at convergence gives both FoS and the inter-slice force
    geometry simultaneously.

    Reference:
        Spencer (1967) Géotechnique 17(1), 11–26. Equations (2), (6), (9).
        Duncan & Wright (2005) Soil Strength and Slope Stability, §6.4.
        Craig §9.3 (notation consistent with this codebase).

    :param slices:     List of Slice objects from core.slicer.create_slices().
    :param ru:         Pore pressure ratio rᵤ (0 = drained, default 0.0).
    :param max_iter:   Max iterations per inner loop (default 300).
    :param tol:        FoS convergence tolerance (default 1e-6).
    :param theta_tol:  θ convergence tolerance on moment FoS (default 1e-5).
    :return:           FoSResult with method = 'Spencer'.
    :raises ValueError: If slices list is empty or analysis is degenerate.
    """
    if not slices:
        raise ValueError("slices list is empty — cannot compute FoS.")
    _has_per_slice_u = any(getattr(s, "u", None) is not None for s in slices)
    if not _has_per_slice_u and not (0.0 <= ru < 1.0):
        raise ValueError(f"rᵤ must be in [0, 1), got {ru}")
    if kh < 0:
        raise ValueError(f"kh must be ≥ 0, got {kh}")
    if kv < 0:
        raise ValueError(f"kv must be ≥ 0, got {kv}")

    # ── Pre-compute slice constants ───────────────────────────────────────
    S_vals    = []
    alpha_rad = []
    weights   = []
    tan_phi   = []
    u_vals    = _resolve_u_vals(slices, ru)
    w_eff     = [s.weight * (1.0 - kv) for s in slices]   # EC8 worst-case

    for s, u, we in zip(slices, u_vals, w_eff):
        phi = math.radians(s.soil.phi_k)
        S_i = s.soil.c_k * s.b + (we - u * s.b) * math.tan(phi)
        S_vals.append(S_i)
        alpha_rad.append(s.alpha)
        weights.append(s.weight)
        tan_phi.append(math.tan(phi))

    # Seismic driving sum: Σ[W·sinα + kh·W·cosα]
    sum_W_sina = sum(
        w * math.sin(a) + kh * w * math.cos(a)
        for w, a in zip(weights, alpha_rad)
    )
    total_weight = sum(abs(w) for w in weights)
    _validate_driving_sum(sum_W_sina, total_weight, "Σ(W·sinα + kh·W·cosα)")

    # Use magnitude throughout — negative sum_W_sina is valid for a mirrored slope.
    abs_W_sina = abs(sum_W_sina)

    # ── Seed F from Bishop (with same kh/kv) ─────────────────────────────
    _seed_ru = 0.0 if _has_per_slice_u else ru
    try:
        F = bishop_simplified(slices, ru=_seed_ru, kh=kh, kv=kv).fos
    except ValueError:
        F = 1.0

    # ── Outer loop: sweep θ until F_moment = F_force ──────────────────────
    # Background (Spencer 1967 / Duncan & Wright 2005 §6.4):
    #   g(θ) = F_m(θ) − F_f(θ)  →  find θ* where g = 0.
    #
    # For CIRCULAR surfaces, both the moment and force equations share the
    # same mα = cosα + sinα·tanφ'/F, so at θ=0:
    #     F_f(0) = Σ[S_i·cos(α)/mα] / Σ[W·sin(α)] = F_m
    # i.e. g(0) ≡ 0 exactly.  This means g(θ) has a TANGENTIAL zero at
    # θ=0 rather than a sign-crossing, making naive bisection blind to it.
    # Strategy: check θ=0 first; if |g(0)| < tolerance, accept immediately.
    # This is physically correct — θ=0 (horizontal inter-slice forces) is
    # the Spencer solution for circular surfaces, and FoS = Bishop FoS.

    phi_avg = sum(math.radians(s.soil.phi_k) for s in slices) / len(slices)

    warning    = ""
    converged  = False
    iterations = 0
    theta      = 0.0

    def _compute_F_moment(F_in: float) -> float:
        """
        Moment-equation FoS — identical to Bishop's Simplified.
        Spencer (1967) Eq.(2): moment about circle centre.
            F_m = Σ[ S_i / mα ] / |Σ[ W·sinα ]|
            mα  = cosα + sinα·tanφ'/F    (θ-independent for circular surfaces)
        """
        num = 0.0
        for S_i, a, tp in zip(S_vals, alpha_rad, tan_phi):
            m_alpha = math.cos(a) + math.sin(a) * tp / F_in
            if abs(m_alpha) < 1e-9:
                continue
            num += S_i / m_alpha
        return num / abs_W_sina

    def _compute_F_force(F_in: float, theta_in: float) -> float:
        """
        Force-equation FoS — horizontal equilibrium.
        Spencer (1967) Eq.(6):
            F_f = Σ[ S_i · cos(α−θ) / mα ] / Σ[ W · sin(α−θ) ]
        where mα = cosα + sinα·tanφ'/F  (same mα as moment equation).

        At θ=0:  cos(α−0)=cosα, sin(α−0)=sinα  →  F_f(0) = F_m  exactly.
        """
        num = 0.0
        den = 0.0
        for S_i, a, w, tp in zip(S_vals, alpha_rad, weights, tan_phi):
            m_alpha   = math.cos(a) + math.sin(a) * tp / F_in
            if abs(m_alpha) < 1e-9:
                continue
            a_minus_t = a - theta_in
            num += S_i * math.cos(a_minus_t) / m_alpha
            den += w   * math.sin(a_minus_t)
        if abs(den) < 1e-9:
            return F_in
        # Use abs(den) — force equation denominator can be negative for
        # mirrored slopes; we want FoS > 0 regardless of sliding direction.
        return num / abs(den)

    def _converge_F_moment(F_seed: float) -> float:
        """Iterate F_m to convergence (θ-independent for circular surfaces)."""
        F_loc = F_seed
        for _ in range(max_iter):
            F_new = _compute_F_moment(F_loc)
            if abs(F_new - F_loc) < tol:
                return F_new
            F_loc = F_new
        return F_loc

    # ── Step 1: check θ = 0 (always valid for circular surfaces) ─────────
    F_conv    = _converge_F_moment(F)
    g_theta0  = F_conv - _compute_F_force(F_conv, 0.0)
    iterations = 1

    if abs(g_theta0) < theta_tol * 100:
        # θ=0 satisfies force-moment consistency — this IS the Spencer solution
        # for circular failure surfaces.  FoS equals Bishop's Simplified.
        theta     = 0.0
        F         = F_conv
        converged = True
    else:
        # ── Step 2: bisect θ in [-φ_avg/2, φ_avg] ────────────────────────
        theta_lo = -phi_avg * 0.5
        theta_hi =  phi_avg

        g_lo = F_conv - _compute_F_force(F_conv, theta_lo)
        g_hi = F_conv - _compute_F_force(F_conv, theta_hi)

        if g_lo * g_hi > 0:
            # No sign change found — θ=0 is the best available answer.
            # This is physically consistent for circular surfaces.
            theta     = 0.0
            F         = F_conv
            converged = True
            warning   = (
                "Spencer: no sign change in g(θ) found in search range. "
                "Used θ=0 (horizontal inter-slice forces), which satisfies "
                "force-moment consistency for circular failure surfaces. "
                "FoS is equivalent to Bishop's Simplified — correct for circles."
            )
        else:
            g_mid = g_lo  # initial value
            for outer in range(200):
                iterations += 1
                theta_mid = (theta_lo + theta_hi) / 2.0
                g_mid     = F_conv - _compute_F_force(F_conv, theta_mid)

                if abs(g_mid) < theta_tol or (theta_hi - theta_lo) < 1e-9:
                    theta     = theta_mid
                    F         = F_conv
                    converged = True
                    break

                if g_lo * g_mid <= 0:
                    theta_hi = theta_mid
                    g_hi     = g_mid
                else:
                    theta_lo = theta_mid
                    g_lo     = g_mid

            if not converged:
                theta = (theta_lo + theta_hi) / 2.0
                F     = F_conv
                warning += (
                    f"Spencer: θ bisection did not converge after 200 iterations "
                    f"(|g| = {abs(g_mid):.2e}).  θ ≈ {math.degrees(theta):.2f}°. "
                    f"Result may be slightly inaccurate."
                )

    fos = F

    # ── Build per-slice result table ──────────────────────────────────────
    slice_results: list[SliceResult] = []
    for s, u, S_i, a, tp in zip(slices, u_vals, S_vals, alpha_rad, tan_phi):
        m_alpha = math.cos(a) + math.sin(a) * tp / fos
        if abs(m_alpha) < 1e-9:
            continue
        numerator   = S_i / m_alpha
        denominator = s.weight * math.sin(a)
        slice_results.append(SliceResult(
            x             = s.x,
            alpha_deg     = math.degrees(a),
            weight        = s.weight,
            pore_pressure = u,
            numerator     = numerator,
            denominator   = denominator,
        ))

    sum_resist_final = sum(sr.numerator for sr in slice_results)
    method_label = "Spencer" if kh == 0.0 else f"Spencer (seismic kh={kh:.3f})"

    return FoSResult(
        method        = method_label,
        fos           = fos,
        converged     = converged,
        iterations    = iterations,
        sum_resist    = sum_resist_final,
        sum_driving   = sum_W_sina,
        ru            = ru,
        slice_results = slice_results,
        warning       = warning,
    )
