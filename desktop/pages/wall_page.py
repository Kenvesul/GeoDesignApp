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


class WallPage(QWidget):
    """Functional desktop page for retaining wall analysis."""

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

        heading = QLabel("Retaining Wall")
        heading.setStyleSheet("font-size: 22px; font-weight: 700;")
        left_layout.addWidget(heading)

        self.soil_picker = SoilPicker()
        self.soil_picker.currentIndexChanged.connect(self._apply_selected_soil)
        left_layout.addWidget(self.soil_picker)

        self.inputs = InputPanel()
        self.gamma_field = self.inputs.add_line_edit("Gamma (kN/m3)", "18.0")
        self.phi_field = self.inputs.add_line_edit("Phi k (deg)", "30.0")
        self.c_field = self.inputs.add_line_edit("c k (kPa)", "0.0")
        self.h_field = self.inputs.add_line_edit("Wall height H (m)", "4.0")
        self.base_field = self.inputs.add_line_edit("Base width B (m)", "3.0")
        self.toe_field = self.inputs.add_line_edit("Toe width (m)", "0.8")
        self.stem_base_field = self.inputs.add_line_edit("Stem base thickness (m)", "0.4")
        self.stem_top_field = self.inputs.add_line_edit("Stem top thickness (m)", "0.3")
        self.t_base_field = self.inputs.add_line_edit("Base slab thickness (m)", "0.5")
        self.q_field = self.inputs.add_line_edit("Surcharge q (kPa)", "0.0")
        self.project_field = self.inputs.add_line_edit("Project", "DesignApp")
        self.job_ref_field = self.inputs.add_line_edit("Job ref", "")
        self.calc_by_field = self.inputs.add_line_edit("Calc by", "")
        self.checked_by_field = self.inputs.add_line_edit("Checked by", "")
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
        self.ka_label = QLabel("Ka: -")
        self.kp_label = QLabel("Kp: -")
        self.slide_label = QLabel("Sliding: -")

        summary_layout.addWidget(QLabel("Status"), 0, 0)
        summary_layout.addWidget(self.result_badge, 0, 1)
        summary_layout.addWidget(QLabel("Ka"), 1, 0)
        summary_layout.addWidget(self.ka_label, 1, 1)
        summary_layout.addWidget(QLabel("Kp"), 2, 0)
        summary_layout.addWidget(self.kp_label, 2, 1)
        summary_layout.addWidget(QLabel("C2 sliding"), 3, 0)
        summary_layout.addWidget(self.slide_label, 3, 1)
        right_layout.addLayout(summary_layout)

        self.plot_canvas = PlotCanvas()
        right_layout.addWidget(self.plot_canvas, 1)

        self.results_table = QTableWidget(2, 5)
        self.results_table.setHorizontalHeaderLabels(
            ["Combination", "Slide FoS", "Overturn FoS", "Bearing Util.", "Pass"]
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

        self._push_status("Idle", "No wall run yet.", None)

    def _push_status(self, status: str, summary: str, passes: bool | None) -> None:
        if self._status_callback:
            self._status_callback("Wall", {"status": status, "summary": summary, "passes": passes})

    def _apply_selected_soil(self) -> None:
        soil = self.soil_picker.selected_soil()
        if not soil:
            return
        self.gamma_field.setText(str(soil.get("gamma", "")))
        self.phi_field.setText(str(soil.get("phi_k", "")))
        self.c_field.setText(str(soil.get("c_k", 0)))

    def _build_payload(self) -> dict:
        return {
            "soil_name": self.soil_picker.currentText() or "Backfill",
            "gamma": float(self.gamma_field.text()),
            "phi_k": float(self.phi_field.text()),
            "c_k": float(self.c_field.text() or 0.0),
            "H_wall": float(self.h_field.text()),
            "B_base": float(self.base_field.text()),
            "B_toe": float(self.toe_field.text()),
            "t_stem_base": float(self.stem_base_field.text()),
            "t_stem_top": float(self.stem_top_field.text()),
            "t_base": float(self.t_base_field.text()),
            "surcharge_kpa": float(self.q_field.text() or 0.0),
            "project": self.project_field.text() or "DesignApp",
            "job_ref": self.job_ref_field.text(),
            "calc_by": self.calc_by_field.text(),
            "checked_by": self.checked_by_field.text(),
        }

    def _run_request(self, payload: dict) -> dict:
        result = api.run_wall_analysis(payload)
        if result.get("ok"):
            result["plot_png"] = api.export_wall_plot_png(result, dpi=120)
        return result

    def run_analysis(self) -> None:
        try:
            payload = self._build_payload()
            errors = api.validate_wall_params(payload)
            if errors:
                raise ValueError("\n".join(errors))
        except Exception as exc:
            self._push_status("Input Error", str(exc), False)
            QMessageBox.warning(self, "Invalid input", str(exc))
            return

        self.run_button.setEnabled(False)
        self.plot_canvas.show_message("Running retaining wall analysis...")
        self._push_status("Running", "Wall stability checks in progress.", None)

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
        self.ka_label.setText(str(result.get("Ka", "-")))
        self.kp_label.setText(str(result.get("Kp", "-")))
        self.slide_label.setText(str(result.get("comb2", {}).get("sliding", {}).get("fos_d", "-")))

        if self.last_plot_png:
            self.plot_canvas.show_png_bytes(self.last_plot_png)
        else:
            self.plot_canvas.show_message("Plot unavailable for this result.")

        for row, key in enumerate(["comb1", "comb2"]):
            comb = result.get(key, {})
            values = [
                comb.get("label", key.upper()),
                str(comb.get("sliding", {}).get("fos_d", "-")),
                str(comb.get("overturn", {}).get("fos_d", "-")),
                str(comb.get("bearing", {}).get("utilisation", "-")),
                "PASS" if comb.get("passes") else "FAIL",
            ]
            for col, value in enumerate(values):
                self.results_table.setItem(row, col, QTableWidgetItem(value))

        self.export_bar.set_enabled_state(True)
        self._push_status(
            "PASS" if result.get("passes") else "FAIL",
            f"Ka={result.get('Ka', '-')}, C2 slide={result.get('comb2', {}).get('sliding', {}).get('fos_d', '-')}",
            result.get("passes"),
        )

    def _on_failure(self, message: str) -> None:
        self.run_button.setEnabled(True)
        self.result_badge.set_pass_state(False)
        self.plot_canvas.show_message("Analysis failed.")
        self._push_status("Error", message, False)
        QMessageBox.critical(self, "Analysis error", message)

    def export_pdf(self) -> None:
        if not self.last_result:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save PDF", "retaining_wall.pdf", "PDF Files (*.pdf)")
        if not path:
            return
        api.export_wall_pdf(self.last_result, path, **self._meta())

    def export_docx(self) -> None:
        if not self.last_result:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save DOCX", "retaining_wall.docx", "Word Files (*.docx)")
        if not path:
            return
        api.export_wall_docx(self.last_result, path, **self._meta())

    def export_png(self) -> None:
        if not self.last_plot_png:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save PNG", "retaining_wall.png", "PNG Files (*.png)")
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
