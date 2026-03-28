from __future__ import annotations

import io

import matplotlib.image as mpimg
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtWidgets import QVBoxLayout, QWidget


class PlotCanvas(QWidget):
    """Minimal matplotlib canvas wrapper for embedded analysis plots."""

    def __init__(self):
        super().__init__()
        self.figure = Figure(figsize=(6, 4))
        self.canvas = FigureCanvasQTAgg(self.figure)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.canvas)

        self.show_message("Run an analysis to view the plot.")

    def show_message(self, message: str) -> None:
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        ax.text(0.5, 0.5, message, ha="center", va="center")
        ax.set_axis_off()
        self.canvas.draw_idle()

    def show_png_bytes(self, png_bytes: bytes) -> None:
        self.figure.clear()
        ax = self.figure.add_subplot(111)
        image = mpimg.imread(io.BytesIO(png_bytes), format="png")
        ax.imshow(image)
        ax.set_axis_off()
        self.canvas.draw_idle()

