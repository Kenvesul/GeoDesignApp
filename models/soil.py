import math


class Soil:
    """
    Represents a soil layer with geotechnical properties.
    Supports conversion from characteristic to design values per Eurocode 7 (EN 1997-1).

    Design value derivation follows EC7 §2.4.6.2 (Material Approach, Set M2):
        tan(phi_d) = tan(phi_k) / gamma_phi
        c_d        = c_k        / gamma_c
    """

    def __init__(self, name: str, unit_weight: float, friction_angle: float,
                 cohesion: float = 0.0, gamma_s: float = 2.65):
        """
        :param name:           Identifier for the soil layer.
        :param unit_weight:    Total unit weight γ (kN/m³).
        :param friction_angle: Characteristic effective friction angle φ'_k (degrees).
        :param cohesion:       Characteristic effective cohesion c'_k (kN/m²).
        :param gamma_s:        Specific gravity of soil particles Gs (-). Default 2.65.
        """
        if unit_weight <= 0:
            raise ValueError(f"unit_weight must be positive, got {unit_weight}")
        if not (0 <= friction_angle < 90):
            raise ValueError(f"friction_angle must be in [0, 90), got {friction_angle}")
        if cohesion < 0:
            raise ValueError(f"cohesion must be non-negative, got {cohesion}")

        self.name    = name
        self.gamma   = unit_weight
        self.phi_k   = friction_angle
        self.c_k     = cohesion
        self.gamma_s = gamma_s          # FIX: was accepted but never stored

    # ------------------------------------------------------------------
    # EC7 Design Values
    # ------------------------------------------------------------------

    def get_design_phi(self, partial_factor: float = 1.25) -> float:
        """
        Design friction angle per EC7 M2.
        tan(φ'_d) = tan(φ'_k) / γ_φ  →  φ'_d = arctan(tan(φ'_k) / γ_φ)

        :param partial_factor: γ_φ  (EC7 Table A.4: M2 = 1.25).
        :return: Design friction angle (degrees).
        """
        phi_rad = math.radians(self.phi_k)
        return math.degrees(math.atan(math.tan(phi_rad) / partial_factor))

    def get_design_cohesion(self, partial_factor: float = 1.25) -> float:
        """
        Design cohesion per EC7 M2.
        c'_d = c'_k / γ_c

        :param partial_factor: γ_c  (EC7 Table A.4: M2 = 1.25).
        :return: Design cohesion (kN/m²).
        """
        return self.c_k / partial_factor

    def __repr__(self) -> str:
        return f"Soil('{self.name}', γ={self.gamma}kN/m³, φ'={self.phi_k}°, c'={self.c_k}kPa)"
