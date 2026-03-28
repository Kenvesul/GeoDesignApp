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


class FoundationPage(QWidget):
    """Functional desktop page for foundation bearing analysis."""

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

        heading = QLabel("Foundation Bearing")
        heading.setStyleSheet("font-size: 22px; font-weight: 700;")
        left_layout.addWidget(heading)

        self.soil_picker = SoilPicker()
        self.soil_picker.currentIndexChanged.connect(self._apply_selected_soil)
        left_layout.addWidget(self.soil_picker)

        self.inputs = InputPanel()
        self.gamma_field = self.inputs.add_line_edit("Gamma (kN/m3)", "18.0")
        self.phi_field = self.inputs.add_line_edit("Phi k (deg)", "30.0")
        self.c_field = self.inputs.add_line_edit("c k (kPa)", "0.0")
        self.b_field = self.inputs.add_line_edit("B (m)", "2.0")
        self.df_field = self.inputs.add_line_edit("Df (m)", "1.0")
        self.gk_field = self.inputs.add_line_edit("Gk (kN/m)", "200.0")
        self.qk_field = self.inputs.add_line_edit("Qk (kN/m)", "80.0")
        self.es_field = self.inputs.add_line_edit("Es (kPa)", "10000")
        self.nu_field = self.inputs.add_line_edit("nu", "0.3")
        self.s_lim_field = self.inputs.add_line_edit("Settlement limit (m)", "0.025")
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
        self.uls_label = QLabel("ULS: -")
        self.sls_label = QLabel("SLS: -")
        self.settlement_label = QLabel("Total settlement: -")

        summary_layout.addWidget(QLabel("Status"), 0, 0)
        summary_layout.addWidget(self.result_badge, 0, 1)
        summary_layout.addWidget(QLabel("ULS"), 1, 0)
        summary_layout.addWidget(self.uls_label, 1, 1)
        summary_layout.addWidget(QLabel("SLS"), 2, 0)
        summary_layout.addWidget(self.sls_label, 2, 1)
        summary_layout.addWidget(QLabel("Settlement"), 3, 0)
        summary_layout.addWidget(self.settlement_label, 3, 1)
        right_layout.addLayout(summary_layout)

        self.plot_canvas = PlotCanvas()
        right_layout.addWidget(self.plot_canvas, 1)

        self.results_table = QTableWidget(2, 5)
        self.results_table.setHorizontalHeaderLabels(
            ["Combination", "Vd", "Rd", "Utilisation", "Pass"]
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

        self._push_status("Idle", "No foundation run yet.", None)

    def _push_status(self, status: str, summary: str, passes: bool | None) -> None:
        if self._status_callback:
            self._status_callback("Foundation", {"status": status, "summary": summary, "passes": passes})

    def _apply_selected_soil(self) -> None:
        soil = self.soil_picker.selected_soil()
        if not soil:
            return
        self.gamma_field.setText(str(soil.get("gamma", "")))
        self.phi_field.setText(str(soil.get("phi_k", "")))
        self.c_field.setText(str(soil.get("c_k", 0)))

    def _build_payload(self) -> dict:
        return {
            "soil_name": self.soil_picker.currentText() or "Soil",
            "gamma": float(self.gamma_field.text()),
            "phi_k": float(self.phi_field.text()),
            "c_k": float(self.c_field.text() or 0.0),
            "B": float(self.b_field.text()),
            "Df": float(self.df_field.text()),
            "Gk": float(self.gk_field.text()),
            "Qk": float(self.qk_field.text() or 0.0),
            "Es_kpa": float(self.es_field.text() or 10000.0),
            "nu": float(self.nu_field.text() or 0.3),
            "s_lim": float(self.s_lim_field.text() or 0.025),
            "project": self.project_field.text() or "DesignApp",
            "job_ref": self.job_ref_field.text(),
            "calc_by": self.calc_by_field.text(),
            "checked_by": self.checked_by_field.text(),
        }

    def _run_request(self, payload: dict) -> dict:
        result = api.run_foundation_analysis(payload)
        if result.get("ok"):
            result["plot_png"] = api.export_foundation_plot_png(result, dpi=120)
        return result

    def run_analysis(self) -> None:
        try:
            payload = self._build_payload()
            errors = api.validate_foundation_params(payload)
            if errors:
                raise ValueError("\n".join(errors))
        except Exception as exc:
            self._push_status("Input Error", str(exc), False)
            QMessageBox.warning(self, "Invalid input", str(exc))
            return

        self.run_button.setEnabled(False)
        self.plot_canvas.show_message("Running foundation analysis...")
        self._push_status("Running", "Bearing and settlement checks in progress.", None)

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
        self.uls_label.setText("PASS" if result.get("uls_passes") else "FAIL")
        sls_value = result.get("sls_passes")
        self.sls_label.setText("-" if sls_value is None else ("PASS" if sls_value else "FAIL"))
        settlement = result.get("s_total_mm")
        self.settlement_label.setText("-" if settlement is None else f"{settlement} mm")

        if self.last_plot_png:
            self.plot_canvas.show_png_bytes(self.last_plot_png)
        else:
            self.plot_canvas.show_message("Plot unavailable for this result.")

        for row, key in enumerate(["comb1", "comb2"]):
            comb = result.get(key, {})
            values = [
                comb.get("label", key.upper()),
                str(comb.get("Vd", "-")),
                str(comb.get("Rd", "-")),
                str(comb.get("utilisation", "-")),
                "PASS" if comb.get("passes") else "FAIL",
            ]
            for col, value in enumerate(values):
                self.results_table.setItem(row, col, QTableWidgetItem(value))

        self.export_bar.set_enabled_state(True)
        self._push_status(
            "PASS" if result.get("passes") else "FAIL",
            f"ULS={'PASS' if result.get('uls_passes') else 'FAIL'}, settlement={result.get('s_total_mm', '-')}",
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
        path, _ = QFileDialog.getSaveFileName(self, "Save PDF", "foundation_bearing.pdf", "PDF Files (*.pdf)")
        if not path:
            return
        api.export_foundation_pdf(self.last_result, path, **self._meta())

    def export_docx(self) -> None:
        if not self.last_result:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save DOCX", "foundation_bearing.docx", "Word Files (*.docx)")
        if not path:
            return
        api.export_foundation_docx(self.last_result, path, **self._meta())

    def export_png(self) -> None:
        if not self.last_plot_png:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save PNG", "foundation_section.png", "PNG Files (*.png)")
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
