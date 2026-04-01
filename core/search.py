"""
Critical slip-circle search for minimum factor of safety.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from core.limit_equilibrium import FoSResult, bishop_simplified
from core.slicer import create_slices
from models.geometry import SlipCircle, SlopeGeometry
from models.soil import Soil

if TYPE_CHECKING:
    from core.seepage import PhreaticSurface
    from models.stratigraphy import Stratigraphy


_INF = float("inf")
_MIN_EFFECTIVE_SLICES = 5
_MIN_MASS_AREA_RATIO = 0.005
# Maximum allowed absolute base angle for any slice (degrees).
# Circles that clip only a steep corner of the slope produce nearly-vertical
# slice bases (|α| close to 90°) with unrealistically large driving moments.
_MAX_BASE_ANGLE_DEG = 75.0
# Minimum arc span as a fraction of total slope width.
# Rejects circles that do not represent a slope-wide failure mechanism.
_MIN_SPAN_FRACTION = 0.25


@dataclass
class SearchResult:
    """Complete output from a critical circle search."""

    critical_circle: SlipCircle
    fos_min: float
    best_fos_result: FoSResult
    fos_grid: list[list[float]]
    cx_values: list[float]
    cy_values: list[float]
    r_values: list[float]
    cx_range: tuple[float, float]
    cy_range: tuple[float, float]
    r_range: tuple[float, float]
    n_circles_tested: int
    n_valid: int
    method: str
    ru: float
    warnings: list[str] = field(default_factory=list)
    search_zone: dict[str, float | int] = field(default_factory=dict)
    search_diagnostics: dict[str, int] = field(default_factory=dict)
    boundary_warning: str | None = None

    def summary(self) -> str:
        """Human-readable search summary."""
        valid_pct = 100.0 * self.n_valid / max(self.n_circles_tested, 1)
        lines = [
            f"{'=' * 58}",
            f"  Critical Circle Search  [{self.method}]",
            f"{'-' * 58}",
            f"  FoS (min)       : {self.fos_min:.4f}",
            f"  Critical centre : ({self.critical_circle.cx:.2f}, {self.critical_circle.cy:.2f}) m",
            f"  Critical radius : {self.critical_circle.r:.2f} m",
            f"  Grid size       : {len(self.cx_values)} cx x {len(self.cy_values)} cy x {len(self.r_values)} R",
            f"  Circles tested  : {self.n_circles_tested} ({valid_pct:.1f}% valid)",
            f"  ru              : {self.ru:.3f}",
            f"{'-' * 58}",
            f"  EC7 Stable : {'YES' if self.fos_min >= 1.00 else 'NO'}",
            f"  EC7 Pass   : {'YES' if self.fos_min >= 1.25 else 'NO'}",
        ]
        if self.boundary_warning:
            lines.append("  Boundary      : critical circle lies near the search edge")
        if self.warnings:
            lines.append(f"  Warnings      : {len(self.warnings)}")
        lines.append(f"{'=' * 58}")
        return "\n".join(lines)


@dataclass
class CircleEvaluation:
    """Internal container for one circle evaluation."""

    status: str
    fos: float | None = None
    fos_result: FoSResult | None = None
    n_slices: int = 0
    mass_area: float = 0.0
    total_weight: float = 0.0
    message: str = ""


def _slope_direction(slope: SlopeGeometry) -> int:
    """
    Return +1 if slope descends left→right (standard),
    -1 if slope descends right→left (mirrored).
    Uses the signed elevation change from first to last point.
    """
    dy = slope.points[-1][1] - slope.points[0][1]
    return -1 if dy > 0 else +1


def _slope_profile_metrics(slope: SlopeGeometry) -> dict[str, float]:
    """Geometry metrics reused by the search heuristics and quality filters."""
    xs = [p[0] for p in slope.points]
    ys = [p[1] for p in slope.points]

    raw_height = max(ys) - min(ys)
    height = max(raw_height, 1.0)
    width = max(max(xs) - min(xs), 1.0)

    steepest_face_len = 1.0
    steepest_gradient = 0.0
    for i in range(len(slope.points) - 1):
        dx = abs(slope.points[i + 1][0] - slope.points[i][0])
        dy = abs(slope.points[i + 1][1] - slope.points[i][1])
        steepest_face_len = max(steepest_face_len, math.hypot(dx, dy))
        if dx > 1e-9:
            steepest_gradient = max(steepest_gradient, dy / dx)

    return {
        "raw_height": raw_height,
        "height": height,
        "width": width,
        "steepest_face_len": steepest_face_len,
        "steepest_gradient": steepest_gradient,
        "slenderness": raw_height / max(width, 1e-9),
    }


def _adaptive_filter_params(slope: SlopeGeometry) -> dict[str, float]:
    """
    Relax geometric filters for shallow, broad profiles without disabling them.
    """
    metrics = _slope_profile_metrics(slope)
    shallow_factor = max(0.0, min(1.0, (0.05 - metrics["slenderness"]) / 0.05))

    return {
        "max_base_angle_deg": _MAX_BASE_ANGLE_DEG + 12.5 * shallow_factor,
        "min_span_fraction": max(0.10, _MIN_SPAN_FRACTION - 0.15 * shallow_factor),
        "min_face_gradient": max(0.005, 0.05 - 0.045 * shallow_factor),
        "face_margin_fraction": 0.10 + 0.25 * shallow_factor,
        "max_bottom_depth": (
            1.5 * metrics["height"]
            + shallow_factor
            * (
                max(1.5 * metrics["steepest_face_len"], 0.20 * metrics["width"])
                - 1.5 * metrics["height"]
            )
        ),
    }


def _auto_bounds(
    slope: SlopeGeometry,
) -> tuple[
    tuple[float, float],
    tuple[float, float],
    tuple[float, float],
]:
    """
    Derive robust default search bounds from slope geometry.

    The bounds cover the region where the classical Bishop critical circle
    is known to lie (Taylor 1937; Bishop & Morgenstern 1960; Craig §9.3):

    * Circle centres must be *above* the slope surface (cy > y_crest).
    * For a left→right descending slope the centre is typically above the
      upper portion of the slope face; the search is widened to cover the
      full slope width ± 1H on each side.
    * Radius spans from 0.5H (shallow, near-toe circle) to 4×W
      (near-planar failure approaching infinite-slope mechanism).

    For a mirrored (right→left descending) slope the cx bounds are
    reflected symmetrically about the slope midpoint so that the circle
    centre lands on the *upslope* side of the mass, keeping Σ(W·sinα)
    in the correct sign direction for that orientation.
    """
    xs = [p[0] for p in slope.points]
    ys = [p[1] for p in slope.points]

    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)

    metrics = _slope_profile_metrics(slope)
    H = metrics["height"]          # slope height (avoid zero)
    direction = _slope_direction(slope)  # +1 standard, -1 mirrored

    if direction >= 0:
        # Standard: descends left→right.  Centre should be above the left
        # portion of the slope; search from x_min−H to x_max+H.
        cx_min = x_min - (1.0 * H)
        cx_max = x_max + (0.75 * H)
    else:
        # Mirrored: descends right→left.  Centre should be above the right
        # portion; mirror the cx range.
        cx_min = x_min - (0.75 * H)
        cx_max = x_max + (1.0 * H)

    # cy must be above the highest point.  Upper bound is y_max + 5H,
    # which is sufficient for near-planar (very large R) mechanisms.
    cy_min = y_max
    cy_max = y_max + 5.0 * H

    # Radius: from half the slope height to 3× the length of the steepest
    # slope face segment.  This range captures all realistic circular failure
    # surfaces.  Near-planar (very large R) mechanisms for c'=0 soils are
    # handled analytically by the infinite-slope check in api.py, so the
    # search does not need to reach R → ∞.
    #
    # Slope face length = sqrt(ΔX² + ΔY²) for the steepest segment.
    r_min = 0.5 * H
    r_max = max(3.0 * metrics["steepest_face_len"], 3.0 * H)

    return (cx_min, cx_max), (cy_min, cy_max), (r_min, r_max)


def _resolve_search_zone(
    slope: SlopeGeometry,
    search_zone: dict[str, float | int] | None,
    cx_range: tuple[float, float] | None,
    cy_range: tuple[float, float] | None,
    r_range: tuple[float, float] | None,
    n_cx: int,
    n_cy: int,
    n_r: int,
) -> dict[str, float | int]:
    """Merge auto bounds, legacy tuple ranges, and explicit search-zone input."""
    auto_cx, auto_cy, auto_r = _auto_bounds(slope)
    zone: dict[str, float | int] = {
        "xc_min": auto_cx[0],
        "xc_max": auto_cx[1],
        "yc_min": auto_cy[0],
        "yc_max": auto_cy[1],
        "r_min": auto_r[0],
        "r_max": auto_r[1],
        "n_cx": n_cx,
        "n_cy": n_cy,
        "n_r": n_r,
    }

    if search_zone:
        alias_map = {
            "cx_min": "xc_min",
            "cx_max": "xc_max",
            "cy_min": "yc_min",
            "cy_max": "yc_max",
        }
        for key, value in search_zone.items():
            if value is None:
                continue
            zone[alias_map.get(key, key)] = value

    if cx_range is not None:
        zone["xc_min"], zone["xc_max"] = cx_range
    if cy_range is not None:
        zone["yc_min"], zone["yc_max"] = cy_range
    if r_range is not None:
        zone["r_min"], zone["r_max"] = r_range

    resolved = {
        "xc_min": float(zone["xc_min"]),
        "xc_max": float(zone["xc_max"]),
        "yc_min": float(zone["yc_min"]),
        "yc_max": float(zone["yc_max"]),
        "r_min": float(zone["r_min"]),
        "r_max": float(zone["r_max"]),
        "n_cx": int(zone["n_cx"]),
        "n_cy": int(zone["n_cy"]),
        "n_r": int(zone["n_r"]),
    }
    return resolved


def _linspace(lo: float, hi: float, n: int) -> list[float]:
    if n == 1:
        return [(lo + hi) / 2.0]
    step = (hi - lo) / (n - 1)
    return [lo + i * step for i in range(n)]


def _circle_reference_area(slope: SlopeGeometry) -> float:
    ys = [p[1] for p in slope.points]
    height = max(ys) - min(ys)
    width = max(slope.x_max - slope.x_min, 1e-9)
    return max(width * max(height, width * 0.1), 1e-9)


def _evaluate_circle(
    slope: SlopeGeometry,
    circle: SlipCircle,
    soil: "Soil | None",
    ru: float,
    num_slices: int,
    stratigraphy: "Stratigraphy | None" = None,
    phreatic_surface: "PhreaticSurface | None" = None,
    reference_area: float = 1.0,
) -> CircleEvaluation:
    """
    Attempt a Bishop analysis for one trial circle.

    Quality filters (applied before the Bishop solve):

    1. **Too few slices** — fewer than _MIN_EFFECTIVE_SLICES effective slices.
    2. **Tiny mass** — sliding-mass area < _MIN_MASS_AREA_RATIO × slope area.
    3. **Extreme base angles** — any slice with |α| > _MAX_BASE_ANGLE_DEG is
       a sign that the circle clips only a steep corner of the slope.  Such
       circles have nearly-vertical slice bases; the horizontal distance from
       the circle centre to the slice base is very large relative to the arc
       length, producing large W·sinα values and unrealistically low FoS.
       Classical Bishop practice excludes circles where the base angle
       exceeds 80° (near-vertical base is geometrically ill-conditioned).
    4. **Insufficient span** — the sliding mass must span at least
       _MIN_SPAN_FRACTION of the total slope width.  This rejects circles
       that clip only the crest or only the toe but do not represent a
       slope-wide failure mechanism.
    """
    try:
        slices = create_slices(
            slope,
            circle,
            soil=soil,
            num_slices=num_slices,
            stratigraphy=stratigraphy,
            phreatic_surface=phreatic_surface,
        )
    except ValueError as exc:
        return CircleEvaluation(status="invalid_geometry", message=str(exc))

    if len(slices) < _MIN_EFFECTIVE_SLICES:
        return CircleEvaluation(
            status="too_few_slices",
            n_slices=len(slices),
            message=f"Only {len(slices)} effective slices.",
        )

    mass_area = sum(s.b * s.height for s in slices)
    total_weight = sum(abs(s.weight) for s in slices)
    if mass_area / max(reference_area, 1e-9) < _MIN_MASS_AREA_RATIO:
        return CircleEvaluation(
            status="tiny_mass",
            n_slices=len(slices),
            mass_area=mass_area,
            total_weight=total_weight,
            message="Sliding mass is too small to be physically meaningful.",
        )

    # ── Filter 3: extreme base angles ─────────────────────────────────────
    filter_params = _adaptive_filter_params(slope)
    max_alpha = max(abs(math.degrees(s.alpha)) for s in slices)
    if max_alpha > filter_params["max_base_angle_deg"]:
        return CircleEvaluation(
            status="invalid_geometry",
            n_slices=len(slices),
            mass_area=mass_area,
            total_weight=total_weight,
            message=(
                f"Max base angle {max_alpha:.1f}° exceeds {_MAX_BASE_ANGLE_DEG}° — "
                "circle clips only a steep corner; not a valid slope-failure mode."
            ),
        )

    # ── Filter 4: insufficient horizontal span ────────────────────────────
    xs = [s.x for s in slices]
    arc_span = max(xs) - min(xs)
    slope_width = max(slope.x_max - slope.x_min, 1e-9)
    if arc_span < filter_params["min_span_fraction"] * slope_width:
        return CircleEvaluation(
            status="invalid_geometry",
            n_slices=len(slices),
            mass_area=mass_area,
            total_weight=total_weight,
            message=(
                f"Arc span {arc_span:.2f} m < {_MIN_SPAN_FRACTION*100:.0f}% of slope "
                f"width {slope_width:.2f} m — circle does not represent a slope-wide failure."
            ),
        )

    # ── Filter 4b: arc must be centred on the inclined slope face ─────────
    # Circles that only clip the flat crest or flat toe do not represent a
    # slope failure mechanism.  Two checks are applied:
    #   (a) The arc x-range must OVERLAP an inclined slope segment.
    #   (b) The arc centroid (mean x of all slice midpoints) must lie within
    #       the x-bounds of the inclined portion.  This rejects circles whose
    #       arc barely touches the face at one edge but is mostly over the
    #       flat crest or toe — such circles are driven by the flat-region
    #       weight, not the slope face geometry.
    inclined_xs: list[tuple[float, float]] = []
    for _i in range(len(slope.points) - 1):
        _x1, _y1 = slope.points[_i]
        _x2, _y2 = slope.points[_i + 1]
        _dx = abs(_x2 - _x1)
        _grad = abs(_y2 - _y1) / max(_dx, 1e-9)
        if _grad >= filter_params["min_face_gradient"]:
            inclined_xs.append((min(_x1, _x2), max(_x1, _x2)))

    if inclined_xs:
        arc_x_min = min(xs)
        arc_x_max = max(xs)
        arc_x_mid = sum(xs) / len(xs)   # centroid of slice midpoints

        # (a) Overlap check
        arc_on_face = any(
            arc_x_max > seg_lo and arc_x_min < seg_hi
            for seg_lo, seg_hi in inclined_xs
        )
        if not arc_on_face:
            return CircleEvaluation(
                status="invalid_geometry",
                n_slices=len(slices),
                mass_area=mass_area,
                total_weight=total_weight,
                message=(
                    f"Arc x-range [{arc_x_min:.2f}, {arc_x_max:.2f}] does not "
                    "intersect any inclined slope segment — circle clips only "
                    "a flat crest or toe, not the actual slope face."
                ),
            )

        # (b) Centroid check: arc centroid must be within the combined
        #     x-range of all inclined segments (expanded 10 % each side).
        face_lo = min(seg[0] for seg in inclined_xs)
        face_hi = max(seg[1] for seg in inclined_xs)
        margin  = filter_params["face_margin_fraction"] * (face_hi - face_lo)
        if not (face_lo - margin <= arc_x_mid <= face_hi + margin):
            return CircleEvaluation(
                status="invalid_geometry",
                n_slices=len(slices),
                mass_area=mass_area,
                total_weight=total_weight,
                message=(
                    f"Arc centroid x={arc_x_mid:.2f} m lies outside the slope "
                    f"face zone [{face_lo:.2f}, {face_hi:.2f}] m — circle is "
                    "dominated by the flat crest/toe, not the slope face."
                ),
            )

    # ── Filter 5: circle bottom not excessively deep below slope toe ──────
    # Circles that extend more than 1.5× the slope height below the lowest
    # slope elevation create unrealistically deep failure surfaces.  Standard
    # Bishop search practice (Taylor 1937; Duncan & Wright 2005 §5.3) limits
    # the critical circle depth to approximately one slope height below the toe.
    # We use 1.5H to allow for base-failure mechanisms while excluding the
    # degenerate deep-graben circles that produce spuriously low FoS.
    ys = [p[1] for p in slope.points]
    y_min_slope = min(ys)
    arc_bottom  = circle.cy - circle.r
    if arc_bottom < y_min_slope - filter_params["max_bottom_depth"]:
        return CircleEvaluation(
            status="invalid_geometry",
            n_slices=len(slices),
            mass_area=mass_area,
            total_weight=total_weight,
            message=(
                f"Circle bottom {arc_bottom:.2f} m is more than {filter_params['max_bottom_depth']:.2f} m "
                f"below slope toe ({y_min_slope:.2f} m) — unrealistically deep failure surface."
            ),
        )

    _ru = 0.0 if phreatic_surface is not None else ru
    try:
        result = bishop_simplified(slices, ru=_ru)
    except ZeroDivisionError as exc:
        return CircleEvaluation(status="invalid_geometry", message=str(exc))
    except ValueError as exc:
        message = str(exc)
        status = "low_driving" if "meaningful sliding mass" in message else "invalid_geometry"
        return CircleEvaluation(
            status=status,
            n_slices=len(slices),
            mass_area=mass_area,
            total_weight=total_weight,
            message=message,
        )

    if not result.converged:
        return CircleEvaluation(
            status="nonconvergent",
            fos_result=result,
            n_slices=len(slices),
            mass_area=mass_area,
            total_weight=total_weight,
            message=result.warning,
        )

    if result.fos <= 0:
        return CircleEvaluation(
            status="nonpositive_fos",
            fos_result=result,
            n_slices=len(slices),
            mass_area=mass_area,
            total_weight=total_weight,
            message="FoS must be positive.",
        )

    return CircleEvaluation(
        status="valid",
        fos=result.fos,
        fos_result=result,
        n_slices=len(slices),
        mass_area=mass_area,
        total_weight=total_weight,
    )


def _boundary_warning(
    best_indices: tuple[int, int, int] | None,
    cx_values: list[float],
    cy_values: list[float],
) -> str | None:
    if best_indices is None:
        return None

    i_cx, i_cy, _ = best_indices
    near_x = i_cx <= 1 or i_cx >= len(cx_values) - 2
    near_y = i_cy <= 1 or i_cy >= len(cy_values) - 2
    if near_x or near_y:
        return (
            "Critical circle center is near the search boundary - expand the "
            "zone to confirm the global minimum."
        )
    return None


def grid_search(
    slope: SlopeGeometry,
    soil: "Soil | None" = None,
    ru: float = 0.0,
    search_zone: dict[str, float | int] | None = None,
    cx_range: tuple[float, float] | None = None,
    cy_range: tuple[float, float] | None = None,
    r_range: tuple[float, float] | None = None,
    n_cx: int = 10,
    n_cy: int = 10,
    n_r: int = 5,
    num_slices: int = 20,
    verbose: bool = False,
    stratigraphy: "Stratigraphy | None" = None,
    phreatic_surface: "PhreaticSurface | None" = None,
) -> SearchResult:
    """Grid search for the critical slip circle (minimum FoS)."""
    if stratigraphy is None and soil is None:
        raise ValueError("Provide either 'soil' (uniform) or 'stratigraphy' (multi-layer).")
    if n_cx < 2 or n_cy < 2 or n_r < 1:
        raise ValueError(
            f"Grid dimensions must be n_cx>=2, n_cy>=2, n_r>=1. Got n_cx={n_cx}, n_cy={n_cy}, n_r={n_r}."
        )
    if phreatic_surface is None and not (0.0 <= ru < 1.0):
        raise ValueError(f"ru must be in [0, 1), got {ru}")
    if num_slices < 5:
        raise ValueError(f"num_slices must be >= 5 for a reliable search, got {num_slices}")

    resolved_zone = _resolve_search_zone(
        slope=slope,
        search_zone=search_zone,
        cx_range=cx_range,
        cy_range=cy_range,
        r_range=r_range,
        n_cx=n_cx,
        n_cy=n_cy,
        n_r=n_r,
    )
    cx_lo, cx_hi = resolved_zone["xc_min"], resolved_zone["xc_max"]
    cy_lo, cy_hi = resolved_zone["yc_min"], resolved_zone["yc_max"]
    r_lo, r_hi = resolved_zone["r_min"], resolved_zone["r_max"]
    n_cx = int(resolved_zone["n_cx"])
    n_cy = int(resolved_zone["n_cy"])
    n_r = int(resolved_zone["n_r"])

    if cx_lo >= cx_hi:
        raise ValueError(f"cx_range: min ({cx_lo}) must be < max ({cx_hi})")
    if cy_lo >= cy_hi:
        raise ValueError(f"cy_range: min ({cy_lo}) must be < max ({cy_hi})")
    if r_lo <= 0 or r_lo >= r_hi:
        raise ValueError(f"r_range: must have 0 < r_min ({r_lo}) < r_max ({r_hi})")

    cx_vals = _linspace(cx_lo, cx_hi, n_cx)
    cy_vals = _linspace(cy_lo, cy_hi, n_cy)
    r_vals = _linspace(r_lo, r_hi, n_r)
    fos_grid: list[list[float]] = [[_INF] * n_cx for _ in range(n_cy)]

    best_fos = _INF
    best_circle: SlipCircle | None = None
    best_fos_result: FoSResult | None = None
    best_indices: tuple[int, int, int] | None = None
    n_tested = 0
    n_valid = 0
    warnings: list[str] = []
    diagnostics = {
        "tested": 0,
        "valid": 0,
        "rejected_invalid_geometry": 0,
        "rejected_too_few_slices": 0,
        "rejected_tiny_mass": 0,
        "rejected_low_driving": 0,
        "rejected_nonconvergent": 0,
        "rejected_nonpositive_fos": 0,
    }
    total = n_cx * n_cy * n_r
    reference_area = _circle_reference_area(slope)

    for j, cy in enumerate(cy_vals):
        for i, cx in enumerate(cx_vals):
            for k, r in enumerate(r_vals):
                n_tested += 1
                diagnostics["tested"] += 1

                if verbose and n_tested % max(1, total // 10) == 0:
                    pct = 100.0 * n_tested / total
                    print(
                        f"  [search] {pct:5.1f}% tested={n_tested} "
                        f"valid={n_valid} best FoS={best_fos:.4f}"
                    )

                if r <= 0:
                    continue

                try:
                    circle = SlipCircle(cx, cy, r)
                except ValueError:
                    continue

                evaluation = _evaluate_circle(
                    slope=slope,
                    circle=circle,
                    soil=soil,
                    ru=ru,
                    num_slices=num_slices,
                    stratigraphy=stratigraphy,
                    phreatic_surface=phreatic_surface,
                    reference_area=reference_area,
                )

                if evaluation.status != "valid":
                    status_key = {
                        "invalid_geometry": "rejected_invalid_geometry",
                        "too_few_slices": "rejected_too_few_slices",
                        "tiny_mass": "rejected_tiny_mass",
                        "low_driving": "rejected_low_driving",
                        "nonconvergent": "rejected_nonconvergent",
                        "nonpositive_fos": "rejected_nonpositive_fos",
                    }.get(evaluation.status)
                    if status_key:
                        diagnostics[status_key] += 1
                    continue

                n_valid += 1
                diagnostics["valid"] += 1
                fos = evaluation.fos
                assert fos is not None

                if fos < fos_grid[j][i]:
                    fos_grid[j][i] = fos

                if fos < best_fos:
                    best_fos = fos
                    best_circle = circle
                    best_fos_result = evaluation.fos_result
                    best_indices = (i, j, k)

    if best_circle is None or math.isinf(best_fos):
        raise ValueError(
            f"No valid slip circle was found in the search domain.\n"
            f"  cx in [{cx_lo:.2f}, {cx_hi:.2f}]  n={n_cx}\n"
            f"  cy in [{cy_lo:.2f}, {cy_hi:.2f}]  n={n_cy}\n"
            f"  R  in [{r_lo:.2f}, {r_hi:.2f}]  n={n_r}\n"
            "Suggestions: widen the search bounds, expand the search zone, "
            "or check that the slope geometry is correct."
        )

    if best_fos_result is None:
        try:
            critical_slices = create_slices(
                slope,
                best_circle,
                soil=soil,
                num_slices=num_slices,
                stratigraphy=stratigraphy,
                phreatic_surface=phreatic_surface,
            )
            _ru_final = 0.0 if phreatic_surface is not None else ru
            best_fos_result = bishop_simplified(critical_slices, ru=_ru_final)
        except ValueError as exc:
            warnings.append(f"Re-evaluation of critical circle failed: {exc}.")
            best_fos_result = None  # type: ignore[assignment]

    boundary_warning = _boundary_warning(best_indices, cx_vals, cy_vals)
    if boundary_warning:
        warnings.append(boundary_warning)

    if verbose:
        print(f"\n  [search] Complete - {n_tested} circles, {n_valid} valid, best FoS = {best_fos:.4f}")

    return SearchResult(
        critical_circle=best_circle,
        fos_min=best_fos,
        best_fos_result=best_fos_result,
        fos_grid=fos_grid,
        cx_values=cx_vals,
        cy_values=cy_vals,
        r_values=r_vals,
        cx_range=(cx_lo, cx_hi),
        cy_range=(cy_lo, cy_hi),
        r_range=(r_lo, r_hi),
        n_circles_tested=n_tested,
        n_valid=n_valid,
        method=f"Grid ({n_cx}x{n_cy}x{n_r})",
        ru=ru,
        warnings=warnings,
        search_zone=resolved_zone,
        search_diagnostics=diagnostics,
        boundary_warning=boundary_warning,
    )


def refine_search(
    result: SearchResult,
    slope: SlopeGeometry,
    soil: "Soil | None" = None,
    zoom: float = 0.3,
    n_cx: int = 12,
    n_cy: int = 12,
    n_r: int = 6,
    num_slices: int = 20,
    verbose: bool = False,
    stratigraphy: "Stratigraphy | None" = None,
) -> SearchResult:
    """Refine a coarse grid result by zooming in around the critical circle."""
    if not (0.0 < zoom <= 1.0):
        raise ValueError(f"zoom must be in (0, 1], got {zoom}")

    cx_best = result.critical_circle.cx
    cy_best = result.critical_circle.cy
    r_best = result.critical_circle.r

    cx_span = (result.cx_range[1] - result.cx_range[0]) * zoom
    cy_span = (result.cy_range[1] - result.cy_range[0]) * zoom
    r_span = (result.r_range[1] - result.r_range[0]) * zoom

    return grid_search(
        slope=slope,
        soil=soil,
        ru=result.ru,
        cx_range=(cx_best - cx_span, cx_best + cx_span),
        cy_range=(cy_best - cy_span, cy_best + cy_span),
        r_range=(max(0.1, r_best - r_span), r_best + r_span),
        n_cx=n_cx,
        n_cy=n_cy,
        n_r=n_r,
        num_slices=num_slices,
        verbose=verbose,
        stratigraphy=stratigraphy,
    )
