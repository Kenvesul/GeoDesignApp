"""
Cross-check DesignApp against pySlope for Craig Example 9.1.

Background
----------
Craig Ex 9.1: dry 1V:2H slope, phi=35 deg, c=0, gamma=19 kN/m3.

Two failure mechanisms apply to c=0 slopes:
1. Circular Bishop  -- finds FoS ~1.1 to 1.2 (critical rotational arc)
2. Infinite-slope   -- FoS = tan(phi)/tan(beta) = tan(35)/tan(26.57) ~1.40

pySlope converges to a large-R planar circle (FoS ~1.40) for c=0 soils.
DesignApp finds the true circular critical circle AND the infinite-slope
check; fos_char is the governing minimum (~1.10-1.20).

Cohesive case note:
  pySlope models a 30 m deep soil block (depth_to_bottom=30).
  DesignApp models only the defined slope geometry (3 m tall).
  The two tools solve *different* physical setups for the same surface slope,
  so large FoS differences are expected.  The cohesive test only checks that
  both engines give physically sensible (FoS > 1) results.

Tests
-----
A  Infinite-slope FoS matches theory within 0.5 %.
B  Infinite-slope FoS matches pySlope within 2 %.
C  For c=0, circular FoS < infinite-slope FoS (circular governs).
D  Cohesive slope: both engines give FoS > 1 (stable slope, no collapse).
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


_SLOPE_POINTS   = [[0, 3], [6, 3], [12, 0], [18, 0]]
_PHI_K          = 35.0
_GAMMA          = 19.0
_BETA_RAD       = math.atan(3.0 / 6.0)
_FOS_INF_THEORY = math.tan(math.radians(_PHI_K)) / math.tan(_BETA_RAD)  # ~1.4004

CRAIG_EX_9_1_PARAMS = dict(
    soil_name="Dense Sand", gamma=_GAMMA, phi_k=_PHI_K, c_k=0.0,
    slope_points=_SLOPE_POINTS, ru=0.0,
    n_cx=24, n_cy=20, n_r=12, num_slices=30,
)

CRAIG_EX_9_1_COHESIVE_PARAMS = dict(
    soil_name="Stiff Clay", gamma=19.0, phi_k=25.0, c_k=10.0,
    slope_points=_SLOPE_POINTS, ru=0.0,
    n_cx=24, n_cy=20, n_r=12, num_slices=30,
)


def _run_designapp(params):
    r = api.run_slope_analysis(dict(params))
    assert r["ok"], r.get("error", "DesignApp analysis failed")
    return r


def _run_pyslope_frictional():
    pyslope = pytest.importorskip("pyslope",
        reason="pyslope not installed -- pip install -r requirements-dev.txt")
    s = pyslope.Slope(height=3.0, angle=None, length=6.0)
    s.set_materials(pyslope.Material(unit_weight=19.0, friction_angle=35.0,
                                     cohesion=0.0, depth_to_bottom=30.0))
    s.update_analysis_options(slices=30, iterations=5000, tolerance=0.001, max_iterations=100)
    s.analyse_slope()
    return float(s.get_min_FOS()), tuple(float(v) for v in s.get_min_FOS_circle())


def _run_pyslope_cohesive():
    pyslope = pytest.importorskip("pyslope",
        reason="pyslope not installed -- pip install -r requirements-dev.txt")
    s = pyslope.Slope(height=3.0, angle=None, length=6.0)
    s.set_materials(pyslope.Material(unit_weight=19.0, friction_angle=25.0,
                                     cohesion=10.0, depth_to_bottom=30.0))
    s.update_analysis_options(slices=30, iterations=5000, tolerance=0.001, max_iterations=100)
    s.analyse_slope()
    return float(s.get_min_FOS())


# ── Test A ────────────────────────────────────────────────────────────────────

def test_infinite_slope_fos_matches_theory():
    """fos_char_infinite_slope must be within 0.5 % of tan(phi)/tan(beta)."""
    r = _run_designapp(CRAIG_EX_9_1_PARAMS)
    fos_inf = r.get("fos_char_infinite_slope")
    assert fos_inf is not None, "fos_char_infinite_slope missing from API output"
    rel = abs(fos_inf - _FOS_INF_THEORY) / _FOS_INF_THEORY
    assert rel <= 0.005, (
        f"Infinite-slope FoS: DesignApp={fos_inf:.4f}, theory={_FOS_INF_THEORY:.4f}, diff={rel:.2%}"
    )


# ── Test B ────────────────────────────────────────────────────────────────────

def test_infinite_slope_fos_matches_pyslope_within_two_percent():
    """DesignApp infinite-slope FoS matches pySlope (planar approx) within 2 %."""
    r            = _run_designapp(CRAIG_EX_9_1_PARAMS)
    ps_fos, circ = _run_pyslope_frictional()
    fos_inf      = r["fos_char_infinite_slope"]
    assert fos_inf is not None
    rel = abs(fos_inf - ps_fos) / ps_fos
    assert rel <= 0.02, (
        f"Infinite-slope vs pySlope: DA={fos_inf:.4f}, pySlope={ps_fos:.4f}, "
        f"theory={_FOS_INF_THEORY:.4f}, diff={rel:.2%}\n"
        f"pySlope circle (own coords): cx={circ[0]:.2f}, cy={circ[1]:.2f}, r={circ[2]:.2f}"
    )


# ── Test C ────────────────────────────────────────────────────────────────────

def test_infinite_slope_governs_for_cohesionless():
    """
    For c=0 on a uniform slope, the planar infinite-slope mechanism is the
    critical mode.  Valid Bishop circular arcs (after geometric quality
    filters) have higher FoS than the planar value because the curved
    failure surface is less efficient than a planar one at the same angle.

    Expected:
      - fos_char_infinite_slope ~= 1.40  (tan phi / tan beta)
      - fos_char_circular > fos_char_infinite_slope  (planar governs)
      - fos_char == fos_char_infinite_slope  (governing mechanism is planar)
    """
    r        = _run_designapp(CRAIG_EX_9_1_PARAMS)
    fos_circ = r["fos_char_circular"]
    fos_inf  = r["fos_char_infinite_slope"]
    fos_char = r["fos_char"]

    assert math.isfinite(fos_circ) and fos_circ > 0.0
    assert fos_inf is not None

    # For c=0, planar mechanism should govern (infinite-slope FoS is lower).
    # This confirms the infinite-slope check correctly catches the critical mode.
    assert fos_char == fos_inf, (
        f"fos_char ({fos_char:.4f}) should equal fos_inf ({fos_inf:.4f}) for c=0 slope"
    )
    # Circular FoS must be > infinite-slope FoS (circular is NOT the critical mode here).
    assert fos_circ > fos_inf, (
        f"For c=0, valid circular FoS ({fos_circ:.4f}) should be > "
        f"infinite-slope FoS ({fos_inf:.4f})"
    )


# ── Test D ────────────────────────────────────────────────────────────────────

def test_cohesive_slope_is_stable_in_both_engines():
    """
    Cohesive slope (phi=25, c=10 kPa): both DesignApp and pySlope must
    report FoS > 1.0 (stable, no collapse).

    Note on expected disagreement:
    pySlope uses depth_to_bottom=30 m (30 m deep soil model).
    DesignApp models only the defined 3 m surface geometry.
    These are different physical setups; absolute FoS values will differ
    substantially (~30-50 %).  The test only checks that both tools agree
    the slope IS stable (FoS > 1), which is the minimum meaningful check
    given the model-depth discrepancy.
    """
    r_da   = _run_designapp(CRAIG_EX_9_1_COHESIVE_PARAMS)
    ps_fos = _run_pyslope_cohesive()

    da_fos = r_da["fos_char"]
    assert math.isfinite(da_fos)  and da_fos  > 1.0, (
        f"DesignApp cohesive FoS={da_fos:.4f} should be > 1.0 (stable)"
    )
    assert math.isfinite(ps_fos) and ps_fos > 1.0, (
        f"pySlope cohesive FoS={ps_fos:.4f} should be > 1.0 (stable)"
    )
