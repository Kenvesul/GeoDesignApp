from __future__ import annotations

from PySide6.QtWidgets import QFormLayout, QPlainTextEdit, QWidget, QLineEdit


class InputPanel(QWidget):
    """Small helper for consistent form layouts in analysis pages."""

    def __init__(self):
        super().__init__()
        self.form = QFormLayout(self)
        self.form.setContentsMargins(0, 0, 0, 0)
        self.form.setSpacing(10)

    def add_line_edit(self, label: str, value: str = "") -> QLineEdit:
        field = QLineEdit()
        field.setText(value)
        self.form.addRow(label, field)
        return field

    def add_plain_text(self, label: str, value: str = "") -> QPlainTextEdit:
        field = QPlainTextEdit()
        field.setPlainText(value)
        field.setMinimumHeight(110)
        self.form.addRow(label, field)
        return field

