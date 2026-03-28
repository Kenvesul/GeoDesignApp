from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import (
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

import api
from desktop.widgets.export_bar import ExportBar
from desktop.widgets.input_panel import InputPanel
from desktop.widgets.plot_canvas import PlotCanvas
from desktop.widgets.result_badge import ResultBadge
from desktop.widgets.soil_picker import SoilPicker
from desktop.workers import AnalysisWorker


class SlopePage(QWidget):
    """Functional PySide6 slope page wired through api.py."""

    def __init__(self, status_callback=None):
        super().__init__()
        self.thread_pool = QThreadPool.globalInstance()
        self.last_result = None
        self.last_plot_png = None
        self._status_callback = status_callback

        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        splitter = QSplitter()
        root.addWidget(splitter, 1)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(12)

        heading = QLabel("Slope Stability")
        heading.setStyleSheet("font-size: 22px; font-weight: 700;")
        left_layout.addWidget(heading)

        self.soil_picker = SoilPicker()
        self.soil_picker.currentIndexChanged.connect(self._apply_selected_soil)
        left_layout.addWidget(self.soil_picker)

        self.inputs = InputPanel()
        self.gamma_field = self.inputs.add_line_edit("Gamma (kN/m3)", "19.0")
        self.phi_field = self.inputs.add_line_edit("Phi k (deg)", "35.0")
        self.c_field = self.inputs.add_line_edit("c k (kPa)", "0.0")
        self.ru_field = self.inputs.add_line_edit("ru", "0.0")
        self.points_field = self.inputs.add_plain_text(
            "Slope points",
            "0,3\n6,3\n12,0\n18,0",
        )
        self.xc_min_field = self.inputs.add_line_edit("xc min (m)", "")
        self.xc_max_field = self.inputs.add_line_edit("xc max (m)", "")
        self.yc_min_field = self.inputs.add_line_edit("yc min (m)", "")
        self.yc_max_field = self.inputs.add_line_edit("yc max (m)", "")
        self.r_min_field = self.inputs.add_line_edit("r min (m)", "")
        self.r_max_field = self.inputs.add_line_edit("r max (m)", "")
        self.n_cx_field = self.inputs.add_line_edit("Grid cols (n_cx)", "12")
        self.n_cy_field = self.inputs.add_line_edit("Grid rows (n_cy)", "12")
        self.n_r_field = self.inputs.add_line_edit("Radii per cell (n_r)", "8")
        self.num_slices_field = self.inputs.add_line_edit("Slices per circle", "20")
        self.project_field = self.inputs.add_line_edit("Project", "DesignApp")
        self.job_ref_field = self.inputs.add_line_edit("Job ref", "")
        self.calc_by_field = self.inputs.add_line_edit("Calc by", "")
        self.checked_by_field = self.inputs.add_line_edit("Checked by", "")
        for field in (
            self.xc_min_field,
            self.xc_max_field,
            self.yc_min_field,
            self.yc_max_field,
            self.r_min_field,
            self.r_max_field,
        ):
            field.setPlaceholderText("Auto")
        left_layout.addWidget(self.inputs)

        run_row = QHBoxLayout()
        self.run_button = QPushButton("Run Analysis")
        self.run_button.clicked.connect(self.run_analysis)
        run_row.addWidget(self.run_button)
        run_row.addStretch(1)
        left_layout.addLayout(run_row)
        left_layout.addStretch(1)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(12)

        summary_layout = QGridLayout()
        summary_layout.setHorizontalSpacing(12)
        summary_layout.setVerticalSpacing(8)

        self.result_badge = ResultBadge()
        self.fos_label = QLabel("FoS: -")
        self.method_label = QLabel("Method: -")
        self.governing_label = QLabel("Governing: -")
        self.warning_label = QLabel("None")
        self.warning_label.setWordWrap(True)

        summary_layout.addWidget(QLabel("Status"), 0, 0)
        summary_layout.addWidget(self.result_badge, 0, 1)
        summary_layout.addWidget(QLabel("Characteristic FoS"), 1, 0)
        summary_layout.addWidget(self.fos_label, 1, 1)
        summary_layout.addWidget(QLabel("Method"), 2, 0)
        summary_layout.addWidget(self.method_label, 2, 1)
        summary_layout.addWidget(QLabel("Governing"), 3, 0)
        summary_layout.addWidget(self.governing_label, 3, 1)
        summary_layout.addWidget(QLabel("Boundary warning"), 4, 0)
        summary_layout.addWidget(self.warning_label, 4, 1)
        right_layout.addLayout(summary_layout)

        self.plot_canvas = PlotCanvas()
        right_layout.addWidget(self.plot_canvas, 1)

        self.results_table = QTableWidget(2, 4)
        self.results_table.setHorizontalHeaderLabels(
            ["Combination", "FoS d", "Target", "Pass"]
        )
        right_layout.addWidget(self.results_table)

        self.export_bar = ExportBar(show_png=True)
        self.export_bar.set_enabled_state(False)
        self.export_bar.set_handlers(
            on_pdf=self.export_pdf,
            on_docx=self.export_docx,
            on_png=self.export_png,
        )
        right_layout.addWidget(self.export_bar)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setSizes([420, 820])

        self._push_status("Idle", "No slope run yet.", None)

    def _push_status(self, status: str, summary: str, passes: bool | None) -> None:
        if self._status_callback:
            self._status_callback("Slope", {"status": status, "summary": summary, "passes": passes})

    def _apply_selected_soil(self) -> None:
        soil = self.soil_picker.selected_soil()
        if not soil:
            return
        self.gamma_field.setText(str(soil.get("gamma", "")))
        self.phi_field.setText(str(soil.get("phi_k", "")))
        self.c_field.setText(str(soil.get("c_k", 0)))

    def _build_payload(self) -> dict:
        points = []
        for line in self.points_field.toPlainText().splitlines():
            line = line.strip()
            if not line:
                continue
            x_raw, y_raw = [part.strip() for part in line.replace(";", ",").split(",")[:2]]
            points.append([float(x_raw), float(y_raw)])

        payload = {
            "soil_name": self.soil_picker.currentText() or "Soil",
            "gamma": float(self.gamma_field.text()),
            "phi_k": float(self.phi_field.text()),
            "c_k": float(self.c_field.text() or 0.0),
            "ru": float(self.ru_field.text() or 0.0),
            "slope_points": points,
            "n_cx": int(self.n_cx_field.text() or 12),
            "n_cy": int(self.n_cy_field.text() or 12),
            "n_r": int(self.n_r_field.text() or 8),
            "num_slices": int(self.num_slices_field.text() or 20),
            "project": self.project_field.text() or "DesignApp",
            "job_ref": self.job_ref_field.text(),
            "calc_by": self.calc_by_field.text(),
            "checked_by": self.checked_by_field.text(),
        }
        for key, field in (
            ("xc_min", self.xc_min_field),
            ("xc_max", self.xc_max_field),
            ("yc_min", self.yc_min_field),
            ("yc_max", self.yc_max_field),
            ("r_min", self.r_min_field),
            ("r_max", self.r_max_field),
        ):
            if field.text().strip():
                payload[key] = float(field.text())
        return payload

    def _run_request(self, payload: dict) -> dict:
        result = api.run_slope_analysis(payload)
        if result.get("ok"):
            result["plot_png"] = api.export_slope_plot_png(result, dpi=120)
        return result

    def run_analysis(self) -> None:
        try:
            payload = self._build_payload()
            errors = api.validate_slope_params(payload)
            if errors:
                raise ValueError("\n".join(errors))
        except Exception as exc:
            self._push_status("Input Error", str(exc), False)
            QMessageBox.warning(self, "Invalid input", str(exc))
            return

        self.run_button.setEnabled(False)
        self.plot_canvas.show_message("Running slope analysis...")
        self._push_status("Running", "Slope search in progress.", None)

        worker = AnalysisWorker(self._run_request, payload)
        worker.signals.finished.connect(self._on_result)
        worker.signals.failed.connect(self._on_failure)
        self.thread_pool.start(worker)

    def _on_result(self, result: dict) -> None:
        self.run_button.setEnabled(True)
        if not result.get("ok"):
            self._on_failure(result.get("error", "Analysis failed"))
            return

        self.last_result = dict(result)
        self.last_plot_png = self.last_result.pop("plot_png", None)
        self.result_badge.set_pass_state(result.get("passes"))
        self.fos_label.setText(str(result.get("fos_char", "-")))
        self.method_label.setText(str(result.get("method", "-")))
        self.governing_label.setText(str(result.get("governing_combination", "-")))
        self.warning_label.setText(result.get("boundary_warning") or "None")

        if self.last_plot_png:
            self.plot_canvas.show_png_bytes(self.last_plot_png)
        else:
            self.plot_canvas.show_message("Plot unavailable for this result.")

        for row, key in enumerate(["comb1", "comb2"]):
            comb = result.get(key, {})
            values = [
                comb.get("label", key.upper()),
                str(comb.get("fos_d", "-")),
                str(comb.get("target", "-")),
                "PASS" if comb.get("passes") else "FAIL",
            ]
            for col, value in enumerate(values):
                self.results_table.setItem(row, col, QTableWidgetItem(value))

        self.export_bar.set_enabled_state(True)
        summary = f"FoS={result.get('fos_char', '-')}, method={result.get('method', '-')}"
        if result.get("boundary_warning"):
            summary += f", warning={result['boundary_warning']}"
        self._push_status(
            "PASS" if result.get("passes") else "FAIL",
            summary,
            result.get("passes"),
        )

    def _on_failure(self, message: str) -> None:
        self.run_button.setEnabled(True)
        self.result_badge.set_pass_state(False)
        self.warning_label.setText("None")
        self.plot_canvas.show_message("Analysis failed.")
        self._push_status("Error", message, False)
        QMessageBox.critical(self, "Analysis error", message)

    def export_pdf(self) -> None:
        if not self.last_result:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save PDF", "slope_stability.pdf", "PDF Files (*.pdf)")
        if not path:
            return
        api.export_pdf(self.last_result, path, **self._meta())

    def export_docx(self) -> None:
        if not self.last_result:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save DOCX", "slope_stability.docx", "Word Files (*.docx)")
        if not path:
            return
        api.export_docx(self.last_result, path, **self._meta())

    def export_png(self) -> None:
        if not self.last_plot_png:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save PNG", "slope_section.png", "PNG Files (*.png)")
        if not path:
            return
        Path(path).write_bytes(self.last_plot_png)

    def _meta(self) -> dict:
        return {
            "project": self.project_field.text() or "DesignApp",
            "job_ref": self.job_ref_field.text(),
            "calc_by": self.calc_by_field.text(),
            "checked_by": self.checked_by_field.text(),
        }
