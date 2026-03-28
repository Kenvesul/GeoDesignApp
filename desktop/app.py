from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from desktop.main_window import MainWindow
from desktop.theme import build_palette


def main() -> int:
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("DesignApp")
    app.setOrganizationName("DesignApp")
    app.setStyle("Fusion")
    app.setPalette(build_palette(dark=False))

    window = MainWindow(app)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

