"""
Cross-check the Craig Example 9.1 slope against pySlope.

This test is intentionally light on new math: it runs the same dry 1V:2H
homogeneous slope through both engines and compares the characteristic Bishop
FoS values directly. If the values drift by more than 1%, it is a strong sign
that our search domain or search acceptance rules are not finding the same
critical mechanism.
"""

from __future__ import annotations

import math
import os
import sys

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import api


CRAIG_EX_9_1_PARAMS = dict(
    soil_name="Dense Sand",
    gamma=19.0,
    phi_k=35.0,
    c_k=0.0,
    slope_points=[[0, 3], [6, 3], [12, 0], [18, 0]],
    ru=0.0,
    # Use a denser-than-UI grid so this parity check is driven by the search
    # logic rather than a coarse discretisation artifact.
    n_cx=24,
    n_cy=20,
    n_r=12,
    num_slices=30,
)


def _run_designapp_engine() -> tuple[float, dict]:
    result = api.run_slope_analysis(dict(CRAIG_EX_9_1_PARAMS))
    assert result["ok"], result.get("error", "DesignApp slope analysis failed")
    return float(result["fos_char"]), result


def _run_pyslope() -> tuple[float, tuple[float, float, float]]:
    pyslope = pytest.importorskip(
        "pyslope",
        reason="Install dev dependencies from requirements-dev.txt to enable pySlope parity checks.",
    )

    slope = pyslope.Slope(height=3.0, angle=None, length=6.0)
    material = pyslope.Material(
        unit_weight=19.0,
        friction_angle=35.0,
        cohesion=0.0,
        depth_to_bottom=30.0,
    )

    slope.set_materials(material)

    slope.update_analysis_options(
        slices=30,
        iterations=5000,
        tolerance=0.001,
        max_iterations=100,
    )
    slope.analyse_slope()

    fos = float(slope.get_min_FOS())
    circle = tuple(float(value) for value in slope.get_min_FOS_circle())
    return fos, circle


def test_craig_ex_9_1_matches_pyslope_within_one_percent():
    """
    Craig Example 9.1 should give materially the same Bishop FoS in both tools.

    We compare characteristic/unfactored FoS values so that any failure points
    directly to search behaviour, not EC7 partial-factor application.
    """
    engine_fos, engine_result = _run_designapp_engine()
    pyslope_fos, pyslope_circle = _run_pyslope()

    assert math.isfinite(engine_fos)
    assert math.isfinite(pyslope_fos)
    assert pyslope_fos > 0.0

    relative_difference = abs(engine_fos - pyslope_fos) / pyslope_fos
    engine_circle = engine_result["critical_circle"]
    boundary_warning = engine_result.get("boundary_warning") or "none"

    assert relative_difference <= 0.01, (
        "Craig Ex. 9.1 parity check failed:\n"
        f"  DesignApp FoS = {engine_fos:.4f}\n"
        f"  pySlope  FoS = {pyslope_fos:.4f}\n"
        f"  Relative diff = {relative_difference:.2%}\n"
        f"  DesignApp circle = (cx={engine_circle['cx']:.3f}, cy={engine_circle['cy']:.3f}, r={engine_circle['r']:.3f})\n"
        f"  pySlope circle   = (cx={pyslope_circle[0]:.3f}, cy={pyslope_circle[1]:.3f}, r={pyslope_circle[2]:.3f})\n"
        f"  Boundary warning = {boundary_warning}"
    )
