"""
Published slope-verification benchmarks grounded in local PDF manuals.

These tests are intentionally narrow: they only cover benchmark families that
the current solver can represent faithfully with its present modelling
capabilities (homogeneous circular slip search with Bishop slices).

Primary local references:
    - documents/Geostudio-Slope Stability Verification Manual-Oct2022.pdf
    - documents/RS2_SlopeStabilityVerification_Part1.pdf

ACADS simple slope values cited in those manuals:
    GeoStudio Bishop: 0.963
    RS2/Slide2 Bishop: 0.987
    Referee / survey mean: ~0.99 to 1.00

The ACADS simple-slope figure includes a vertical bench step at the toe. The
current ``SlopeGeometry`` model only accepts a single-valued ``y(x)`` polyline,
so the fixture below uses the closest equivalent surface profile that preserves
the main crest / face / toe dimensions while staying inside the solver's
supported geometry class.
"""

from __future__ import annotations

import math
import os
import sys


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.search import grid_search
from models.geometry import SlopeGeometry
from models.soil import Soil


def test_acads_simple_slope_matches_published_bishop_band():
    """
    ACADS simple slope should land in the published Bishop range.

    Source data:
    - GeoStudio verification manual: Bishop = 0.963
    - RS2 verification manual: Bishop = 0.987

    We use a modest tolerance band around those published values because the
    search strategy here is a regular grid, while the manuals used entry-exit
    style searches and different implementations.
    """
    soil = Soil(
        "ACADS simple slope",
        unit_weight=20.0,
        friction_angle=19.6,
        cohesion=3.0,
    )

    # Polyline approximation of the published ACADS section for the current
    # geometry model:
    # - preserves the 10 m height difference
    # - preserves the 1V:2H slope face
    # - replaces the non-function vertical step with a short toe bench
    slope = SlopeGeometry([(0.0, 0.0), (20.0, 0.0), (40.0, 10.0), (50.0, 10.0)])

    result = grid_search(
        slope,
        soil,
        ru=0.0,
        n_cx=20,
        n_cy=18,
        n_r=12,
        num_slices=30,
    )

    assert math.isfinite(result.fos_min)
    assert 0.95 <= result.fos_min <= 1.02, (
        "ACADS simple slope drifted outside the published Bishop band:\n"
        f"  DesignApp FoS = {result.fos_min:.4f}\n"
        "  GeoStudio Bishop = 0.9630\n"
        "  RS2/Slide2 Bishop = 0.9870\n"
        f"  Critical circle = (cx={result.critical_circle.cx:.3f}, "
        f"cy={result.critical_circle.cy:.3f}, r={result.critical_circle.r:.3f})\n"
        f"  Boundary warning = {result.boundary_warning or 'none'}"
    )
