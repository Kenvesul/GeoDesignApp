"""
materials.py -- Pre-defined structural material grades.

Provides named concrete and reinforcing steel grade objects for use in
retaining wall self-weight calculations and future structural design checks.
No geotechnical calculations are performed here.

Concrete grades follow EN 206 / Eurocode 2 (EN 1992-1-1) notation:
    C25/30 means fck_cylinder = 25 MPa, fck_cube = 30 MPa.

Steel reinforcement grades follow EN 10080:
    B500B: characteristic yield strength fyk = 500 MPa, ductility class B.

Reference:
    EN 206:2013+A2:2021 (Concrete specification).
    EN 1992-1-1:2004 (Eurocode 2, Table 3.1).
    EN 10080:2005 (Steel for reinforcement).

Units:
    Strengths in MPa (= N/mm^2).  Unit weights in kN/m^3.
    Partial factors (gamma_c, gamma_s) are dimensionless.
"""

from dataclasses import dataclass


# ============================================================
#  Data containers
# ============================================================

@dataclass(frozen=True)
class Concrete:
    """
    Eurocode 2 concrete grade (EN 1992-1-1 Table 3.1).

    Attributes
    ----------
    grade       : Grade label, e.g. 'C25/30'.
    fck         : Characteristic cylinder compressive strength (MPa).
    fck_cube    : Characteristic cube compressive strength (MPa).
    fctm        : Mean tensile strength (MPa).
    Ecm         : Mean elastic modulus (GPa).
    gamma_c     : Partial factor for concrete (persistent/transient: 1.5).
    unit_weight : Unit weight of reinforced concrete (kN/m^3). Default 25.0.
    """
    grade       : str
    fck         : float
    fck_cube    : float
    fctm        : float
    Ecm         : float
    gamma_c     : float = 1.5
    unit_weight : float = 25.0   # kN/m^3 (unreinforced: 24.0, reinforced: 25.0)

    def fcd(self) -> float:
        """Design compressive strength fcd = fck / gamma_c (MPa)."""
        return self.fck / self.gamma_c

    def __repr__(self) -> str:
        return (
            f"Concrete({self.grade}: fck={self.fck} MPa, "
            f"Ecm={self.Ecm} GPa, gamma={self.unit_weight} kN/m3)"
        )


@dataclass(frozen=True)
class ReinforcingSteel:
    """
    Reinforcing steel grade (EN 10080 / EC2 Section 3.2).

    Attributes
    ----------
    grade    : Grade label, e.g. 'B500B'.
    fyk      : Characteristic yield strength (MPa).
    Es       : Elastic modulus (GPa). Typically 200 GPa.
    gamma_s  : Partial factor for steel (persistent/transient: 1.15).
    ductility: Ductility class ('A', 'B', or 'C').
    """
    grade    : str
    fyk      : float
    Es       : float = 200.0
    gamma_s  : float = 1.15
    ductility: str   = 'B'

    def fyd(self) -> float:
        """Design yield strength fyd = fyk / gamma_s (MPa)."""
        return self.fyk / self.gamma_s

    def __repr__(self) -> str:
        return (
            f"ReinforcingSteel({self.grade}: fyk={self.fyk} MPa, "
            f"Es={self.Es} GPa, class {self.ductility})"
        )


# ============================================================
#  Pre-defined concrete grades (EC2 Table 3.1)
# ============================================================
# fctm formula: EC2 §3.1.2
#   fctm = 0.30 * fck^(2/3)   for fck <= 50 MPa
# Ecm formula:  EC2 §3.1.3
#   Ecm = 22 * (fcm/10)^0.3   where fcm = fck + 8 MPa

C20_25  = Concrete("C20/25",  fck=20.0, fck_cube=25.0, fctm=2.21, Ecm=29.0)
C25_30  = Concrete("C25/30",  fck=25.0, fck_cube=30.0, fctm=2.56, Ecm=30.5)
C30_37  = Concrete("C30/37",  fck=30.0, fck_cube=37.0, fctm=2.90, Ecm=32.0)
C35_45  = Concrete("C35/45",  fck=35.0, fck_cube=45.0, fctm=3.21, Ecm=33.5)
C40_50  = Concrete("C40/50",  fck=40.0, fck_cube=50.0, fctm=3.51, Ecm=35.0)

CONCRETE_GRADES: dict[str, Concrete] = {
    c.grade: c for c in (C20_25, C25_30, C30_37, C35_45, C40_50)
}


# ============================================================
#  Pre-defined reinforcing steel grades (EN 10080)
# ============================================================

B500A = ReinforcingSteel("B500A", fyk=500.0, ductility='A')
B500B = ReinforcingSteel("B500B", fyk=500.0, ductility='B')
B500C = ReinforcingSteel("B500C", fyk=500.0, ductility='C')

STEEL_GRADES: dict[str, ReinforcingSteel] = {
    s.grade: s for s in (B500A, B500B, B500C)
}


# ============================================================
#  Convenience accessor
# ============================================================

def get_concrete(grade: str) -> Concrete:
    """
    Returns a pre-defined Concrete object by grade label.

    :param grade: Grade string, e.g. 'C25/30'.
    :return:      Concrete object.
    :raises KeyError: If grade not found in CONCRETE_GRADES.
    """
    if grade not in CONCRETE_GRADES:
        available = list(CONCRETE_GRADES.keys())
        raise KeyError(f"Unknown concrete grade '{grade}'. Available: {available}")
    return CONCRETE_GRADES[grade]


def get_steel(grade: str) -> ReinforcingSteel:
    """
    Returns a pre-defined ReinforcingSteel object by grade label.

    :param grade: Grade string, e.g. 'B500B'.
    :return:      ReinforcingSteel object.
    :raises KeyError: If grade not found in STEEL_GRADES.
    """
    if grade not in STEEL_GRADES:
        available = list(STEEL_GRADES.keys())
        raise KeyError(f"Unknown steel grade '{grade}'. Available: {available}")
    return STEEL_GRADES[grade]
