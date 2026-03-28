from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class PlaceholderPage(QWidget):
    """Temporary page used while the Phase 6 desktop tabs are scaffolded."""

    def __init__(self, title: str, body: str):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)

        heading = QLabel(title)
        heading.setStyleSheet("font-size: 22px; font-weight: 700;")

        copy = QLabel(body)
        copy.setWordWrap(True)
        copy.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        copy.setStyleSheet("font-size: 14px; color: #4b5563;")

        layout.addWidget(heading)
        layout.addWidget(copy)
        layout.addStretch(1)

