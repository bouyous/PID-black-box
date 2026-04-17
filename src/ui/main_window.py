from pathlib import Path

import pandas as pd
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QLabel,
    QMainWindow,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from parser.blackbox_parser import BlackboxParser
from ui.plot_widget import GyroPlotWidget, PidPlotWidget

SUPPORTED_EXTS = {'.bbl', '.bfl'}
AXIS_NAMES = ['Roll', 'Pitch', 'Yaw']

DARK_STYLE = """
QMainWindow, QWidget {
    background: #1e1e1e;
    color: #e0e0e0;
}
QTabWidget::pane {
    border: 1px solid #333;
    background: #1e1e1e;
}
QTabBar::tab {
    background: #2d2d2d;
    color: #bbb;
    padding: 6px 16px;
    border: 1px solid #333;
    border-bottom: none;
}
QTabBar::tab:selected {
    background: #1e1e1e;
    color: #fff;
    border-bottom: 2px solid #4a9eff;
}
QTabBar::tab:hover {
    background: #3a3a3a;
}
QStatusBar {
    background: #161616;
    color: #888;
    font-size: 12px;
}
QCheckBox {
    spacing: 6px;
}
"""


class DropArea(QLabel):
    file_dropped = pyqtSignal(str)

    _BASE_STYLE = """
        border: 2px dashed {color};
        border-radius: 8px;
        color: #aaa;
        font-size: 14px;
        background: #252525;
        padding: 20px;
    """

    def __init__(self):
        super().__init__()
        self.setText("Glissez un fichier .bbl / .bfl ici")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAcceptDrops(True)
        self.setMinimumHeight(70)
        self._set_color('#555')

    def _set_color(self, color: str):
        self.setStyleSheet(f"QLabel {{ {self._BASE_STYLE.format(color=color)} }}")

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            paths = [Path(u.toLocalFile()) for u in event.mimeData().urls()]
            if any(p.suffix.lower() in SUPPORTED_EXTS for p in paths):
                event.acceptProposedAction()
                self._set_color('#4a9eff')
                return
        event.ignore()

    def dragLeaveEvent(self, event):
        self._set_color('#555')

    def dropEvent(self, event: QDropEvent):
        self._set_color('#555')
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if Path(path).suffix.lower() in SUPPORTED_EXTS:
                self.file_dropped.emit(path)
                break


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.parser = BlackboxParser()
        self.setWindowTitle("BlackBox Analyzer")
        self.resize(1200, 750)
        self.setStyleSheet(DARK_STYLE)
        self._build_ui()

        if not self.parser.is_ready():
            self.status.showMessage(
                "⚠  blackbox_decode.exe introuvable — voir tools/README.md", 0
            )
        else:
            self.status.showMessage("Prêt — glissez un fichier blackbox pour commencer.")

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.drop_area = DropArea()
        self.drop_area.file_dropped.connect(self._on_file_dropped)
        layout.addWidget(self.drop_area)

        self.session_tabs = QTabWidget()
        self.session_tabs.setVisible(False)
        layout.addWidget(self.session_tabs, stretch=1)

        self.status = QStatusBar()
        self.setStatusBar(self.status)

    def _on_file_dropped(self, path: str):
        name = Path(path).name
        self.status.showMessage(f"Décodage en cours : {name} …")
        self.session_tabs.clear()
        self.session_tabs.setVisible(False)

        try:
            sessions = self.parser.decode(path)
        except Exception as exc:
            self.status.showMessage(f"Erreur : {exc}")
            self.drop_area.setText(f"✗  Échec du chargement de {name}")
            return

        for i, df in enumerate(sessions):
            tab = self._build_session_tab(df)
            label = f"Session {i + 1}  ({self._duration(df)})"
            self.session_tabs.addTab(tab, label)

        self.session_tabs.setVisible(True)
        total_rows = sum(len(s) for s in sessions)
        self.status.showMessage(
            f"✓  {name}  —  {len(sessions)} session(s), {total_rows:,} points"
        )
        self.drop_area.setText(
            f"✓  {name}  —  {len(sessions)} session(s)   "
            "(glissez un autre fichier pour remplacer)"
        )

    def _build_session_tab(self, df: pd.DataFrame) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 2, 0, 0)

        inner = QTabWidget()
        inner.addTab(GyroPlotWidget(df), "Gyroscope")

        for i, axis_name in enumerate(AXIS_NAMES):
            field = f'axisP[{i}]'
            if field in df.columns:
                inner.addTab(PidPlotWidget(df, i, axis_name), f"PID {axis_name}")

        layout.addWidget(inner)
        return widget

    @staticmethod
    def _duration(df: pd.DataFrame) -> str:
        if 'time_s' not in df.columns or df.empty:
            return "?"
        secs = df['time_s'].iloc[-1] - df['time_s'].iloc[0]
        if secs < 60:
            return f"{secs:.1f}s"
        return f"{int(secs // 60)}m{int(secs % 60):02d}s"
