"""FoS heatmap plot helpers for the slope search surface."""

from __future__ import annotations

import math

import matplotlib
import numpy as np

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from core.search import SearchResult
from models.geometry import SlopeGeometry


def _coerce_result(soil_or_result, result: SearchResult | None) -> SearchResult:
    """
    Backward-compatible argument handling.

    Old signature:
        plot_fos_heatmap(slope, soil, result, ...)
    New signature:
        plot_fos_heatmap(slope, result, ...)
    """
    if result is not None:
        return result
    if isinstance(soil_or_result, SearchResult):
        return soil_or_result
    raise TypeError("plot_fos_heatmap() requires a SearchResult.")


def _materialize_grid(result: SearchResult) -> np.ndarray:
    grid = np.asarray(result.fos_grid, dtype=float)
    if grid.size == 0:
        raise ValueError("SearchResult does not contain a FoS grid.")
    return grid


def plot_fos_heatmap(
    slope: SlopeGeometry,
    soil_or_result,
    result: SearchResult | None = None,
    ru: float = 0.0,
    n_cx: int | None = None,
    n_cy: int | None = None,
    title: str = "FoS Heatmap - Bishop Simplified",
    figsize: tuple = (10, 7),
    fos_clip: float = 3.0,
) -> plt.Figure:
    """Render a FoS heatmap from an existing SearchResult surface."""
    search_result = _coerce_result(soil_or_result, result)
    fos_grid = _materialize_grid(search_result)
    cx_values = np.asarray(search_result.cx_values, dtype=float)
    cy_values = np.asarray(search_result.cy_values, dtype=float)

    masked = np.ma.masked_invalid(np.clip(fos_grid, None, fos_clip))
    if masked.count() == 0:
        raise ValueError("SearchResult FoS grid contains no finite values.")

    cx_mesh, cy_mesh = np.meshgrid(cx_values, cy_values)
    fig, ax = plt.subplots(figsize=figsize)

    finite_min = float(masked.min())
    level_min = max(0.5, min(finite_min, fos_clip))
    levels = np.linspace(level_min, fos_clip, 20)

    contour = ax.contourf(cx_mesh, cy_mesh, masked, levels=levels, cmap="RdYlGn", extend="both")
    isolines = ax.contour(cx_mesh, cy_mesh, masked, levels=levels, colors="black", linewidths=0.3, alpha=0.4)
    ax.clabel(isolines, levels[::4], inline=True, fontsize=7, fmt="%.2f")

    cbar = fig.colorbar(contour, ax=ax, label="Factor of Safety (FoS)")
    cbar.ax.tick_params(labelsize=8)

    crit = search_result.critical_circle
    label = f"Critical: FoS={search_result.best_fos_result.fos:.4f}"
    ax.plot(crit.cx, crit.cy, "r*", markersize=14, zorder=5, label=label)
    ax.plot(crit.cx, crit.cy, "k+", markersize=8, markeredgewidth=1.5, zorder=6)

    try:
        cs1 = ax.contour(cx_mesh, cy_mesh, masked, levels=[1.0], colors="red", linewidths=1.5, linestyles="--")
        ax.clabel(cs1, fmt="FoS=1.0", fontsize=8)
    except ValueError:
        pass

    ax.set_xlabel("Circle centre x (m)", fontsize=9)
    ax.set_ylabel("Circle centre y (m)", fontsize=9)
    ax.set_title(title, fontsize=11, fontweight="bold")
    ax.legend(loc="upper right", fontsize=8)
    ax.tick_params(labelsize=8)
    ax.set_aspect("equal")
    fig.tight_layout()
    return fig


def save_fos_heatmap(
    slope: SlopeGeometry,
    soil_or_result,
    result: SearchResult | None = None,
    filepath: str = "",
    title: str = "FoS Heatmap - Bishop Simplified",
    dpi: int = 150,
    **kwargs,
) -> None:
    """Render a FoS heatmap and save it to disk."""
    fig = plot_fos_heatmap(slope, soil_or_result, result=result, title=title, **kwargs)
    fig.savefig(filepath, dpi=dpi, bbox_inches="tight")
    plt.close(fig)
