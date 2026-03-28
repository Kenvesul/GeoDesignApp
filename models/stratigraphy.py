"""
stratigraphy.py -- Multi-layer soil profile.

Maps a stack of soil layers (each defined by a depth boundary and a Soil
object) to queries such as:
    - Which soil occupies a given depth?
    - What are the strength parameters at the base of a slice?

This module enhances both wall analysis (assign soil to retained / foundation
zones) and slope stability (per-slice soil assignment for multi-layer slopes).

Reference:
    Craig's Soil Mechanics, 9th ed., Chapters 9 and 11 (layered profiles).
    Eurocode 7 -- EN 1997-1:2004, S3 (Geotechnical data, layered ground).

Sign conventions:
    Depth z is measured vertically downward from the ground surface (z >= 0).
    Layer boundaries are expressed as depth-to-bottom-of-layer values.
    The final layer extends to infinite depth.

Units:
    All depths in metres (m).
"""

from __future__ import annotations
from dataclasses import dataclass, field

from models.soil import Soil


# ============================================================
#  SoilLayer -- single layer within a stratigraphy
# ============================================================

@dataclass
class SoilLayer:
    """
    One layer in a stratigraphic profile.

    Attributes
    ----------
    soil         : Soil object with characteristic strength parameters.
    depth_bottom : Depth to the bottom of this layer (m).
                   Use float('inf') for the lowest (infinite-depth) layer.
    """
    soil         : Soil
    depth_bottom : float

    def __post_init__(self):
        if self.depth_bottom <= 0:
            raise ValueError(
                f"depth_bottom must be > 0, got {self.depth_bottom}.  "
                "Layers are defined top-down; the first layer starts at z=0."
            )

    def __repr__(self) -> str:
        bottom = f"{self.depth_bottom:.2f} m" if self.depth_bottom != float("inf") else "inf"
        return f"SoilLayer({self.soil.name!r}, bottom={bottom})"


# ============================================================
#  Stratigraphy -- ordered stack of soil layers
# ============================================================

class Stratigraphy:
    """
    An ordered stack of soil layers covering the full depth range.

    Layers are stored top-to-bottom (increasing depth).  The deepest layer
    must extend to infinite depth (depth_bottom = float('inf')) to guarantee
    that get_soil_at_depth() always returns a valid Soil.

    Construction example (3-layer profile):
        layers = [
            SoilLayer(Soil("Fill",     18.0, 22, 0),    depth_bottom=2.0),
            SoilLayer(Soil("Sand",     20.0, 32, 0),    depth_bottom=8.0),
            SoilLayer(Soil("Clay",     19.5, 25, 10.0), depth_bottom=float('inf')),
        ]
        strat = Stratigraphy(layers)
    """

    def __init__(self, layers: list[SoilLayer]):
        """
        :param layers: Ordered list of SoilLayer objects, top layer first.
                       Must contain at least one layer.
                       The deepest layer must have depth_bottom == float('inf').
        :raises ValueError: If layers is empty, not sorted, or last layer
                            does not extend to infinity.
        """
        if not layers:
            raise ValueError("Stratigraphy requires at least one SoilLayer.")

        # Validate ordering
        prev_bottom = 0.0
        for i, layer in enumerate(layers):
            if layer.depth_bottom <= prev_bottom:
                raise ValueError(
                    f"Layer {i} depth_bottom ({layer.depth_bottom}) must be "
                    f"greater than the previous boundary ({prev_bottom})."
                )
            prev_bottom = layer.depth_bottom

        if layers[-1].depth_bottom != float("inf"):
            raise ValueError(
                f"The deepest layer must have depth_bottom = float('inf') "
                f"to cover all depths.  Got {layers[-1].depth_bottom}."
            )

        self._layers = list(layers)

    # ── Queries ──────────────────────────────────────────────────────────

    def get_soil_at_depth(self, z: float) -> Soil:
        """
        Returns the Soil object at depth z below the surface.

        :param z:  Depth (m), z >= 0.
        :return:   Soil occupying that depth.
        :raises ValueError: If z < 0.
        """
        if z < 0:
            raise ValueError(f"Depth z must be >= 0, got {z}")
        depth_top = 0.0
        for layer in self._layers:
            if z <= layer.depth_bottom:
                return layer.soil
            depth_top = layer.depth_bottom
        # Should never reach here because last layer has depth_bottom = inf
        return self._layers[-1].soil

    def layer_boundaries(self) -> list[float]:
        """
        Returns a list of layer boundary depths (m), top boundary (0.0) first.

        Useful for drawing the stratigraphic column in a plot.
        """
        bounds = [0.0]
        for layer in self._layers[:-1]:   # exclude infinite last boundary
            bounds.append(layer.depth_bottom)
        return bounds

    @property
    def n_layers(self) -> int:
        """Number of soil layers in the profile."""
        return len(self._layers)

    @property
    def layers(self) -> list[SoilLayer]:
        """Read-only copy of the layer list."""
        return list(self._layers)

    # ── Convenience constructors ──────────────────────────────────────────

    @classmethod
    def single_layer(cls, soil: Soil) -> "Stratigraphy":
        """
        Creates a uniform (single-layer) stratigraphy.

        :param soil: Soil occupying the full depth profile.
        :return:     Stratigraphy instance.
        """
        return cls([SoilLayer(soil, float("inf"))])

    # ── Representation ────────────────────────────────────────────────────

    def __repr__(self) -> str:
        parts = []
        prev = 0.0
        for layer in self._layers:
            bottom = f"{layer.depth_bottom:.2f} m" if layer.depth_bottom != float("inf") else "inf"
            parts.append(f"  {prev:.2f}–{bottom}: {layer.soil.name}")
            prev = layer.depth_bottom
        return "Stratigraphy(\n" + "\n".join(parts) + "\n)"
