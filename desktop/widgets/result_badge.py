from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel


class ResultBadge(QLabel):
    """Simple pass/fail badge used across desktop pages."""

    def __init__(self, text: str = "Idle"):
        super().__init__(text)
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumWidth(110)
        self.set_pass_state(None)

    def set_pass_state(self, passes: bool | None) -> None:
        if passes is None:
            self.setText("Idle")
            self.setStyleSheet(
                "padding: 8px 12px; border-radius: 12px; "
                "background: #e5e7eb; color: #374151; font-weight: 600;"
            )
            return

        self.setText("PASS" if passes else "FAIL")
        bg = "#dff4de" if passes else "#fde2e1"
        fg = "#166534" if passes else "#991b1b"
        self.setStyleSheet(
            f"padding: 8px 12px; border-radius: 12px; "
            f"background: {bg}; color: {fg}; font-weight: 700;"
        )

