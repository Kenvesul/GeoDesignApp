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


def _auto_bounds(
    slope: SlopeGeometry,
) -> tuple[
    tuple[float, float],
    tuple[float, float],
    tuple[float, float],
]:
    """Derive conservative default search bounds from slope geometry."""
    xs = [p[0] for p in slope.points]
    ys = [p[1] for p in slope.points]

    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)

    height = y_max - y_min
    width = x_max - x_min
    height_eff = max(height, width * 0.1)

    cx_min = x_min
    cx_max = x_min + 0.50 * width
    cy_min = y_max + 0.50 * height_eff
    cy_max = y_max + 3.00 * height_eff
    r_min = 0.5 * height_eff
    r_max = 3.0 * height_eff

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
    """Attempt a Bishop analysis for one trial circle."""
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
