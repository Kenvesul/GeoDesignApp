from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QPushButton, QWidget


class ExportBar(QWidget):
    """Button row for PDF/DOCX/PNG export actions."""

    def __init__(self, show_png: bool = True):
        super().__init__()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self.pdf_button = QPushButton("Export PDF")
        self.docx_button = QPushButton("Export DOCX")
        self.png_button = QPushButton("Export PNG")

        layout.addWidget(self.pdf_button)
        layout.addWidget(self.docx_button)
        if show_png:
            layout.addWidget(self.png_button)
        else:
            self.png_button.hide()

    def set_handlers(self, *, on_pdf=None, on_docx=None, on_png=None) -> None:
        if on_pdf is not None:
            self.pdf_button.clicked.connect(on_pdf)
        if on_docx is not None:
            self.docx_button.clicked.connect(on_docx)
        if on_png is not None:
            self.png_button.clicked.connect(on_png)

    def set_enabled_state(self, enabled: bool) -> None:
        self.pdf_button.setEnabled(enabled)
        self.docx_button.setEnabled(enabled)
        self.png_button.setEnabled(enabled)

