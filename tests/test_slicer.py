"""
tests/test_slicer.py

Integration test for the slice geometry engine.
Reference geometry is manually verified against textbook values.

Run from the DesignApp root:
    python -m pytest tests/
  or:
    python tests/test_slicer.py
"""
import sys
import os
import math

# ---------------------------------------------------------------------------
# Path setup – makes 'core' and 'models' importable from anywhere
# ---------------------------------------------------------------------------
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from models.soil     import Soil
from models.geometry import SlopeGeometry, SlipCircle
from core.slicer     import create_slices


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------

def test_slicer_geometry():
    """
    Known geometry:
        Slope profile : (0,10) → (10,10) → (20,0) → (30,0)
        Slip circle   : centre (15, 15), R = 10 m
        Soil          : γ = 20 kN/m³, φ' = 25°, c' = 10 kPa

    Manual check for a slice near x = 13 m:
        y_surface  = 10 + (13-10)*(0-10)/(20-10) = 10 - 3  = 7.00 m
        y_circle   = 15 - sqrt(10² - (13-15)²)
                   = 15 - sqrt(96) = 15 - 9.798 = 5.202 m
        h          = 7.00 - 5.202 = 1.798 m
        b          ≈ (x_end - x_start) / num_slices
    """
    # 1. Define soil
    clay = Soil("Stiff Clay", unit_weight=20.0, friction_angle=25, cohesion=10)

    # 2. Define slope surface
    slope = SlopeGeometry([(0, 10), (10, 10), (20, 0), (30, 0)])

    # 3. Define trial slip circle
    circle = SlipCircle(center_x=15, center_y=15, radius=10)

    # 4. Generate slices
    num_slices = 10
    slices = create_slices(slope, circle, clay, num_slices=num_slices)

    # ---- Assertions -------------------------------------------------------

    assert len(slices) > 0, "FAIL: No slices were generated."

    total_weight = sum(s.weight for s in slices)
    assert total_weight > 0, "FAIL: Total weight must be positive."

    # Every slice must have a positive height and weight
    for s in slices:
        assert s.height > 0,  f"FAIL: Non-positive height in slice at x={s.x:.2f}"
        assert s.weight > 0,  f"FAIL: Non-positive weight in slice at x={s.x:.2f}"
        assert -math.pi/2 < s.alpha < math.pi/2, (
            f"FAIL: α={math.degrees(s.alpha):.1f}° out of valid range for slice at x={s.x:.2f}"
        )

    # Left-half slices should have negative α, right-half positive α
    mid_x = circle.cx
    for s in slices:
        if s.x < mid_x:
            assert s.alpha < 0, f"FAIL: Left slice at x={s.x:.2f} should have α < 0"
        elif s.x > mid_x:
            assert s.alpha > 0, f"FAIL: Right slice at x={s.x:.2f} should have α > 0"

    # ---- Report -----------------------------------------------------------
    print(f"\n{'─'*55}")
    print(f"  Slicer Test  ({len(slices)} valid slices from {num_slices} requested)")
    print(f"{'─'*55}")
    print(f"  {'x (m)':>7}  {'h (m)':>6}  {'W (kN)':>8}  {'α (°)':>7}")
    print(f"{'─'*55}")
    for s in slices:
        print(f"  {s.x:7.2f}  {s.height:6.3f}  {s.weight:8.2f}  {math.degrees(s.alpha):7.2f}")
    print(f"{'─'*55}")
    print(f"  Total weight: {total_weight:.2f} kN/m")
    print(f"\n✅  All assertions passed.\n")


if __name__ == "__main__":
    test_slicer_geometry()
