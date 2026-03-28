from __future__ import annotations

from desktop.pages.placeholder_page import PlaceholderPage


class PilePage(PlaceholderPage):
    def __init__(self):
        super().__init__(
            "Pile Capacity",
            "PilePage is scaffolded for Phase 6. Next pass: add layered input rows, "
            "DA1 results, and export actions through api.run_pile_analysis().",
        )

