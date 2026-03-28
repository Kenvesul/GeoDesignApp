from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow, QTabWidget

from desktop.pages.foundation_page import FoundationPage
from desktop.pages.pile_page import PilePage
from desktop.pages.project_dashboard import ProjectDashboard
from desktop.pages.sheet_pile_page import SheetPilePage
from desktop.pages.slope_page import SlopePage
from desktop.pages.wall_page import WallPage
from desktop.theme import build_palette


def _prefs_path() -> Path:
    return Path.home() / ".designapp" / "prefs.json"


def _load_prefs() -> dict:
    try:
        return json.loads(_prefs_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _save_prefs(data: dict) -> None:
    path = _prefs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


class MainWindow(QMainWindow):
    """Top-level DesignApp desktop shell."""

    def __init__(self, app):
        super().__init__()
        self._app = app
        self._prefs = _load_prefs()
        self._dark_mode = bool(self._prefs.get("dark_mode", False))

        self.setWindowTitle("DesignApp Desktop")
        self.resize(1380, 860)
        self._app.setPalette(build_palette(dark=self._dark_mode))

        self.tabs = QTabWidget()
        self.setCentralWidget(self.tabs)

        self.dashboard_page = ProjectDashboard()
        updater = self.dashboard_page.update_analysis
        self.slope_page = SlopePage(updater)
        self.foundation_page = FoundationPage(updater)
        self.wall_page = WallPage(updater)
        self.pile_page = PilePage()
        self.sheet_pile_page = SheetPilePage(updater)

        self.tabs.addTab(self.dashboard_page, "Dashboard")
        self.tabs.addTab(self.slope_page, "Slope")
        self.tabs.addTab(self.foundation_page, "Foundation")
        self.tabs.addTab(self.wall_page, "Wall")
        self.tabs.addTab(self.pile_page, "Pile")
        self.tabs.addTab(self.sheet_pile_page, "Sheet Pile")

        self.dashboard_page.update_analysis("Pile", {
            "status": "Scaffolded",
            "summary": "Pile tab is still a placeholder in this pass.",
            "passes": None,
        })

        self._build_menu()

    def _build_menu(self) -> None:
        view_menu = self.menuBar().addMenu("View")

        self.theme_action = QAction("Dark Mode", self)
        self.theme_action.setCheckable(True)
        self.theme_action.setChecked(self._dark_mode)
        self.theme_action.toggled.connect(self._toggle_theme)
        view_menu.addAction(self.theme_action)

    def _toggle_theme(self, checked: bool) -> None:
        self._dark_mode = checked
        self._app.setPalette(build_palette(dark=checked))
        self._prefs["dark_mode"] = checked
        _save_prefs(self._prefs)
