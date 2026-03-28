from __future__ import annotations

import io
from pathlib import Path

from PySide6.QtCore import QThreadPool
from PySide6.QtWidgets import (
    QFileDialog,
    QComboBox,
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


class SheetPilePage(QWidget):
    """Functional desktop page for sheet pile analysis."""

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

        heading = QLabel("Sheet Pile")
        heading.setStyleSheet("font-size: 22px; font-weight: 700;")
        left_layout.addWidget(heading)

        self.soil_picker = SoilPicker()
        self.soil_picker.currentIndexChanged.connect(self._apply_selected_soil)
        left_layout.addWidget(self.soil_picker)

        self.inputs = InputPanel()
        self.gamma_field = self.inputs.add_line_edit("Gamma (kN/m3)", "20.0")
        self.phi_field = self.inputs.add_line_edit("Phi k (deg)", "38.0")
        self.c_field = self.inputs.add_line_edit("c k (kPa)", "0.0")
        self.h_field = self.inputs.add_line_edit("Retained height (m)", "6.0")
        self.q_field = self.inputs.add_line_edit("Surcharge q (kPa)", "0.0")
        self.water_field = self.inputs.add_line_edit("Water table z_w (m)", "")
        self.project_field = self.inputs.add_line_edit("Project", "DesignApp")
        self.job_ref_field = self.inputs.add_line_edit("Job ref", "")
        self.calc_by_field = self.inputs.add_line_edit("Calc by", "")
        self.checked_by_field = self.inputs.add_line_edit("Checked by", "")
        left_layout.addWidget(self.inputs)

        support_row = QHBoxLayout()
        support_row.addWidget(QLabel("Support type"))
        self.support_combo = QComboBox()
        self.support_combo.addItem("Propped at top", "propped_top")
        self.support_combo.addItem("Cantilever", "cantilever")
        self.support_combo.addItem("Propped at mid-height", "propped_mid")
        support_row.addWidget(self.support_combo, 1)
        left_layout.addLayout(support_row)

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
        self.governing_label = QLabel("Governing: -")
        self.d_label = QLabel("Embedment: -")
        self.t_label = QLabel("Prop force: -")

        summary_layout.addWidget(QLabel("Status"), 0, 0)
        summary_layout.addWidget(self.result_badge, 0, 1)
        summary_layout.addWidget(QLabel("Governing"), 1, 0)
        summary_layout.addWidget(self.governing_label, 1, 1)
        summary_layout.addWidget(QLabel("d design"), 2, 0)
        summary_layout.addWidget(self.d_label, 2, 1)
        summary_layout.addWidget(QLabel("T design"), 3, 0)
        summary_layout.addWidget(self.t_label, 3, 1)
        right_layout.addLayout(summary_layout)

        self.plot_canvas = PlotCanvas()
        right_layout.addWidget(self.plot_canvas, 1)

        self.results_table = QTableWidget(2, 6)
        self.results_table.setHorizontalHeaderLabels(
            ["Combination", "Ka_d", "Kp_d", "d_min", "T_k", "M_max"]
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

        self._push_status("Idle", "No sheet pile run yet.", None)

    def _push_status(self, status: str, summary: str, passes: bool | None) -> None:
        if self._status_callback:
            self._status_callback("Sheet Pile", {"status": status, "summary": summary, "passes": passes})

    def _apply_selected_soil(self) -> None:
        soil = self.soil_picker.selected_soil()
        if not soil:
            return
        self.gamma_field.setText(str(soil.get("gamma", "")))
        self.phi_field.setText(str(soil.get("phi_k", "")))
        self.c_field.setText(str(soil.get("c_k", 0)))

    def _build_payload(self) -> dict:
        water_raw = self.water_field.text().strip()
        payload = {
            "label": self.soil_picker.currentText() or "Sheet Pile",
            "gamma": float(self.gamma_field.text()),
            "phi_k": float(self.phi_field.text()),
            "c_k": float(self.c_field.text() or 0.0),
            "h_retained": float(self.h_field.text()),
            "q": float(self.q_field.text() or 0.0),
            "prop_type": self.support_combo.currentData(),
            "project": self.project_field.text() or "DesignApp",
            "job_ref": self.job_ref_field.text(),
            "calc_by": self.calc_by_field.text(),
            "checked_by": self.checked_by_field.text(),
        }
        if water_raw:
            payload["z_w"] = float(water_raw)
        return payload

    def _build_plot_png(self, result: dict) -> bytes:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        diagram = result.get("pressure_diagram", [])
        fig, ax = plt.subplots(figsize=(6, 4))
        if diagram:
            depth = [point.get("z_datum", point.get("z", 0.0)) for point in diagram]
            net = [point.get("p_net", 0.0) for point in diagram]
            ax.plot(net, depth, color="#0f766e", linewidth=2.0, label="Net pressure")
            ax.axvline(0.0, color="#94a3b8", linewidth=1.0)
            ax.fill_betweenx(depth, 0.0, net, color="#99f6e4", alpha=0.45)
        ax.invert_yaxis()
        ax.set_xlabel("Pressure (kPa)")
        ax.set_ylabel("Depth datum (m)")
        ax.set_title("Sheet Pile Pressure Diagram")
        ax.grid(True, linestyle="--", alpha=0.35)
        if diagram:
            ax.legend(loc="best")
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    def _run_request(self, payload: dict) -> dict:
        result = api.run_sheet_pile_analysis(payload)
        if result.get("ok"):
            result["plot_png"] = self._build_plot_png(result)
        return result

    def run_analysis(self) -> None:
        try:
            payload = self._build_payload()
            errors = api.validate_sheet_pile_params(payload)
            if errors:
                raise ValueError("\n".join(errors))
        except Exception as exc:
            self._push_status("Input Error", str(exc), False)
            QMessageBox.warning(self, "Invalid input", str(exc))
            return

        self.run_button.setEnabled(False)
        self.plot_canvas.show_message("Running sheet pile analysis...")
        self._push_status("Running", "Sheet pile embedment search in progress.", None)

        worker = AnalysisWorker(self._run_request, payload)
        worker.signals.finished.connect(self._on_result)
        worker.signals.failed.connect(self._on_failure)
        self.thread_pool.start(worker)

    def _on_result(self, result: dict) -> None:
        self.run_button.setEnabled(True)
        if not result.get("ok"):
            self._on_failure("; ".join(result.get("errors") or [result.get("error", "Analysis failed")]))
            return

        self.last_result = dict(result)
        self.last_plot_png = self.last_result.pop("plot_png", None)
        self.result_badge.set_pass_state(result.get("passes"))
        self.governing_label.setText(str(result.get("governing_combination") or result.get("governing") or "-"))
        self.d_label.setText(f"{result.get('d_design', '-')} m")
        self.t_label.setText(f"{result.get('T_design', '-')} kN/m")

        if self.last_plot_png:
            self.plot_canvas.show_png_bytes(self.last_plot_png)
        else:
            self.plot_canvas.show_message("Plot unavailable for this result.")

        for row, key in enumerate(["comb1", "comb2"]):
            comb = result.get(key, {})
            values = [
                comb.get("label", key.upper()),
                str(comb.get("Ka_d", "-")),
                str(comb.get("Kp_d", "-")),
                str(comb.get("d_min", "-")),
                str(comb.get("T_k", "-")),
                str(comb.get("M_max", "-")),
            ]
            for col, value in enumerate(values):
                self.results_table.setItem(row, col, QTableWidgetItem(value))

        self.export_bar.set_enabled_state(True)
        self._push_status(
            "PASS" if result.get("passes") else "FAIL",
            f"d={result.get('d_design', '-')}, T={result.get('T_design', '-')}",
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
        path, _ = QFileDialog.getSaveFileName(self, "Save PDF", "sheet_pile.pdf", "PDF Files (*.pdf)")
        if not path:
            return
        api.export_sheet_pile_pdf(self.last_result, path, **self._meta())

    def export_docx(self) -> None:
        if not self.last_result:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save DOCX", "sheet_pile.docx", "Word Files (*.docx)")
        if not path:
            return
        api.export_sheet_pile_docx(self.last_result, path, **self._meta())

    def export_png(self) -> None:
        if not self.last_plot_png:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Save PNG", "sheet_pile_pressure.png", "PNG Files (*.png)")
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
