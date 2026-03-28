import math


class SlopeGeometry:
    """
    Defines the ground surface profile as a polyline of (x, y) coordinates.
    Coordinates are in metres; x increases to the right, y increases upward.
    """

    def __init__(self, points: list[tuple[float, float]]):
        """
        :param points: Ordered list of (x, y) tuples defining the surface.
                       At least two points are required.
        """
        if len(points) < 2:
            raise ValueError("SlopeGeometry requires at least two points.")
        self.points = sorted(points, key=lambda p: p[0])

    def get_y_at_x(self, x: float) -> float | None:
        """
        Returns the surface elevation at horizontal position x via linear interpolation.
        Returns None if x is outside the defined range.
        """
        for i in range(len(self.points) - 1):
            x1, y1 = self.points[i]
            x2, y2 = self.points[i + 1]
            if x1 <= x <= x2:
                # Linear interpolation: y = y1 + (x - x1) * (y2 - y1) / (x2 - x1)
                return y1 + (x - x1) * (y2 - y1) / (x2 - x1)
        return None

    @property
    def x_min(self) -> float:
        return self.points[0][0]

    @property
    def x_max(self) -> float:
        return self.points[-1][0]


class SlipCircle:
    """
    Defines a trial circular failure surface for the Method of Slices.
    Convention: the slip arc is the LOWER arc of the circle (y = cy - sqrt(...)).
    """

    def __init__(self, center_x: float, center_y: float, radius: float):
        """
        :param center_x: x-coordinate of the circle centre (m).
        :param center_y: y-coordinate of the circle centre (m).
        :param radius:   Circle radius R (m).
        """
        if radius <= 0:
            raise ValueError(f"Radius must be positive, got {radius}")
        self.cx = center_x
        self.cy = center_y
        self.r  = radius

    def get_y_at_x(self, x: float) -> float | None:
        """
        y-coordinate of the slip arc at position x.
        Uses the lower arc:  y = cy - sqrt(R² - (x - cx)²)
        Returns None when x is outside the circle's horizontal extent.
        """
        term = self.r ** 2 - (x - self.cx) ** 2   # FIX: added missing import math
        if term < 0:
            return None
        return self.cy - math.sqrt(term)           # FIX: math.sqrt now resolvable

    @property
    def x_left(self) -> float:
        """Leftmost x of the full circle."""
        return self.cx - self.r

    @property
    def x_right(self) -> float:
        """Rightmost x of the full circle."""
        return self.cx + self.r
