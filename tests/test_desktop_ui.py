import pytest

pytest.importorskip("PySide6")
pytest.importorskip("matplotlib")

from PySide6.QtWidgets import QApplication

from desktop.main_window import MainWindow
from desktop.pages.slope_page import SlopePage


def test_main_window_has_expected_tabs():
    app = QApplication.instance() or QApplication([])
    window = MainWindow(app)
    labels = [window.tabs.tabText(i) for i in range(window.tabs.count())]
    assert labels == ["Dashboard", "Slope", "Foundation", "Wall", "Pile", "Sheet Pile"]


def test_dark_mode_action_is_checkable():
    app = QApplication.instance() or QApplication([])
    window = MainWindow(app)
    assert window.theme_action.isCheckable()


def test_dashboard_updates_analysis_card():
    app = QApplication.instance() or QApplication([])
    window = MainWindow(app)
    window.dashboard_page.update_analysis(
        "Wall",
        {"status": "PASS", "summary": "Ka=0.333, C2 slide=1.81", "passes": True},
    )
    assert window.dashboard_page.cards["Wall"]["status"].text() == "PASS"
    assert "Ka=0.333" in window.dashboard_page.cards["Wall"]["summary"].text()


def test_slope_page_build_payload_includes_search_zone():
    app = QApplication.instance() or QApplication([])
    page = SlopePage()
    page.xc_min_field.setText("0.0")
    page.xc_max_field.setText("9.0")
    page.yc_min_field.setText("4.5")
    page.yc_max_field.setText("9.0")
    page.r_min_field.setText("2.0")
    page.r_max_field.setText("10.0")
    page.n_cx_field.setText("16")
    page.n_cy_field.setText("14")
    page.n_r_field.setText("7")
    page.num_slices_field.setText("24")

    payload = page._build_payload()

    assert payload["xc_min"] == 0.0
    assert payload["xc_max"] == 9.0
    assert payload["yc_min"] == 4.5
    assert payload["yc_max"] == 9.0
    assert payload["r_min"] == 2.0
    assert payload["r_max"] == 10.0
    assert payload["n_cx"] == 16
    assert payload["n_cy"] == 14
    assert payload["n_r"] == 7
    assert payload["num_slices"] == 24


def test_slope_page_surfaces_boundary_warning():
    app = QApplication.instance() or QApplication([])
    page = SlopePage()
    page._on_result({
        "ok": True,
        "passes": True,
        "fos_char": 1.72,
        "method": "Bishop's Simplified",
        "governing_combination": "DA1-C2",
        "boundary_warning": "Critical circle center is near the search boundary - expand the zone to confirm the global minimum.",
        "comb1": {"label": "DA1-C1", "fos_d": 1.9, "target": 1.0, "passes": True},
        "comb2": {"label": "DA1-C2", "fos_d": 1.7, "target": 1.0, "passes": True},
        "plot_png": None,
    })

    assert "near the search boundary" in page.warning_label.text()
