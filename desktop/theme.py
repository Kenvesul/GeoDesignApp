from __future__ import annotations

from PySide6.QtGui import QColor, QPalette


def build_palette(dark: bool) -> QPalette:
    """Return a simple light or dark palette for the desktop app."""
    palette = QPalette()
    if not dark:
        return palette

    palette.setColor(QPalette.Window, QColor(36, 39, 46))
    palette.setColor(QPalette.WindowText, QColor(235, 237, 240))
    palette.setColor(QPalette.Base, QColor(28, 31, 37))
    palette.setColor(QPalette.AlternateBase, QColor(45, 49, 58))
    palette.setColor(QPalette.ToolTipBase, QColor(255, 255, 255))
    palette.setColor(QPalette.ToolTipText, QColor(24, 24, 24))
    palette.setColor(QPalette.Text, QColor(235, 237, 240))
    palette.setColor(QPalette.Button, QColor(45, 49, 58))
    palette.setColor(QPalette.ButtonText, QColor(235, 237, 240))
    palette.setColor(QPalette.Highlight, QColor(56, 132, 255))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    return palette

