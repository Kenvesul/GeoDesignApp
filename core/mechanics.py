"""
mechanics.py – Fundamental geotechnical physics.

All formulae follow Eurocode 7 (EN 1997-1) conventions unless noted.
"""


def calculate_vertical_effective_stress(
    depth: float,
    unit_weight: float,
    water_depth: float | None = None,
    gamma_w: float = 9.81,
) -> tuple[float, float]:
    """
    Calculates total vertical stress, pore water pressure, and effective stress
    at a given depth below the ground surface.

    Formula (EC7 §A.3):
        σ_v  = γ · z                        (total vertical stress)
        u    = γ_w · (z - z_w)   if z > z_w (hydrostatic pore pressure)
        σ'_v = σ_v − u                      (vertical effective stress)

    :param depth:       Depth from surface z (m). Must be ≥ 0.
    :param unit_weight: Soil total unit weight γ (kN/m³).
    :param water_depth: Depth to water table z_w (m).
                        Pass None for a dry soil profile (u = 0 everywhere).
    :param gamma_w:     Unit weight of water γ_w (kN/m³). Default 9.81.
    :return:            Tuple (effective_stress [kPa], pore_pressure [kPa]).
    """
    if depth < 0:
        raise ValueError(f"Depth must be ≥ 0, got {depth}")
    if unit_weight <= 0:
        raise ValueError(f"unit_weight must be positive, got {unit_weight}")

    total_stress = unit_weight * depth

    if water_depth is not None and depth > water_depth:
        pore_pressure = gamma_w * (depth - water_depth)
    else:
        pore_pressure = 0.0

    effective_stress = total_stress - pore_pressure
    return effective_stress, pore_pressure
