from __future__ import annotations

from PySide6.QtWidgets import QComboBox

import api


class SoilPicker(QComboBox):
    """Combo box backed by the shared soil library from api.py."""

    def __init__(self):
        super().__init__()
        self._soils = api.get_soil_library()
        self.addItem("Select soil...", None)
        for soil in self._soils:
            self.addItem(soil["name"], soil)

    def selected_soil(self) -> dict | None:
        return self.currentData()

