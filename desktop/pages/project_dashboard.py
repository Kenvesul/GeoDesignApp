from __future__ import annotations

from PySide6.QtWidgets import QFrame, QGridLayout, QLabel, QVBoxLayout, QWidget


class ProjectDashboard(QWidget):
    """Desktop landing page with live analysis status cards."""

    def __init__(self):
        super().__init__()
        self.cards = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        heading = QLabel("DesignApp Desktop")
        heading.setStyleSheet("font-size: 26px; font-weight: 700;")

        intro = QLabel(
            "Phase 6 desktop scaffold is active. Slope and Foundation are wired "
            "through api.py, and the dashboard now reflects live page state as "
            "analyses run across the desktop shell."
        )
        intro.setWordWrap(True)

        notes = QLabel(
            "Architecture rules:\n"
            "- Desktop pages call api.py only.\n"
            "- Long-running analysis work goes through QThreadPool.\n"
            "- Export actions write directly to user-selected files."
        )
        notes.setWordWrap(True)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(14)

        for idx, name in enumerate(["Slope", "Foundation", "Wall", "Pile", "Sheet Pile"]):
            card = self._build_card(name)
            row, col = divmod(idx, 2)
            if idx == 4:
                row, col = 2, 0
            grid.addWidget(card, row, col)

        layout.addWidget(heading)
        layout.addWidget(intro)
        layout.addWidget(notes)
        layout.addLayout(grid)
        layout.addStretch(1)

    def _build_card(self, name: str) -> QFrame:
        frame = QFrame()
        frame.setFrameShape(QFrame.StyledPanel)
        frame.setStyleSheet(
            "QFrame { background: #f8fafc; border: 1px solid #dbe4ee; border-radius: 12px; }"
        )

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        title = QLabel(name)
        title.setStyleSheet("font-size: 16px; font-weight: 700;")

        status = QLabel("Idle")
        status.setStyleSheet("font-size: 13px; font-weight: 700; color: #475569;")

        summary = QLabel("No desktop run yet.")
        summary.setWordWrap(True)
        summary.setStyleSheet("font-size: 12px; color: #64748b;")

        layout.addWidget(title)
        layout.addWidget(status)
        layout.addWidget(summary)

        self.cards[name] = {"status": status, "summary": summary}
        return frame

    def update_analysis(self, name: str, state: dict) -> None:
        card = self.cards.get(name)
        if not card:
            return

        status_text = state.get("status", "Idle")
        summary_text = state.get("summary", "No details yet.")
        passes = state.get("passes")

        card["status"].setText(status_text)
        card["summary"].setText(summary_text)

        if passes is True:
            colour = "#166534"
        elif passes is False:
            colour = "#991b1b"
        else:
            colour = "#475569"
        card["status"].setStyleSheet(f"font-size: 13px; font-weight: 700; color: {colour};")
