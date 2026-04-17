from pathlib import Path

import pandas as pd
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from analysis.analyzer import analyze
from analysis.header_parser import FlightConfig, parse_header
from analysis.recommender import generate_report
from parser.blackbox_parser import BlackboxParser
from ui.plot_widget import GyroPlotWidget, MotorPlotWidget, PidPlotWidget
from ui.recommendation_panel import DiagnosticWidget

SUPPORTED_EXTS = {'.bbl', '.bfl'}
AXIS_NAMES = ['Roll', 'Pitch', 'Yaw']
DRONE_SIZES = ['3"', '5"', '6"', '7"', '10"']

DARK_STYLE = """
QMainWindow, QWidget {
    background: #1a1a1a;
    color: #e0e0e0;
}
QTabWidget::pane {
    border: 1px solid #333;
    background: #1a1a1a;
}
QTabBar::tab {
    background: #252525;
    color: #bbb;
    padding: 6px 14px;
    border: 1px solid #333;
    border-bottom: none;
}
QTabBar::tab:selected {
    background: #1a1a1a;
    color: #fff;
    border-bottom: 2px solid #4a9eff;
}
QTabBar::tab:hover { background: #333; }
QStatusBar { background: #111; color: #777; font-size: 12px; }
QComboBox {
    background: #252525;
    color: #e0e0e0;
    border: 1px solid #444;
    padding: 4px 8px;
    border-radius: 4px;
}
QComboBox::drop-down { border: none; }
QComboBox QAbstractItemView {
    background: #252525;
    color: #e0e0e0;
    selection-background-color: #3a3a3a;
}
QGroupBox {
    color: #888;
    border: 1px solid #333;
    border-radius: 4px;
    margin-top: 8px;
    padding: 8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
}
"""


class DropArea(QLabel):
    file_dropped = pyqtSignal(str)
    _BASE = ("border: 2px dashed {color}; border-radius: 8px; "
             "color: #888; font-size: 13px; background: #222; padding: 14px;")

    def __init__(self):
        super().__init__()
        self.setText("Glissez un fichier .bbl / .bfl ici")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAcceptDrops(True)
        self.setMinimumHeight(60)
        self._set('#444')

    def _set(self, color: str):
        self.setStyleSheet(f"QLabel {{ {self._BASE.format(color=color)} }}")

    def dragEnterEvent(self, event: QDragEnterEvent):
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        if any(Path(u.toLocalFile()).suffix.lower() in SUPPORTED_EXTS for u in urls):
            event.acceptProposedAction()
            self._set('#4a9eff')
        else:
            event.ignore()

    def dragLeaveEvent(self, event): self._set('#444')

    def dropEvent(self, event: QDropEvent):
        self._set('#444')
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if Path(path).suffix.lower() in SUPPORTED_EXTS:
                self.file_dropped.emit(path)
                break


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.parser = BlackboxParser()
        self._last_cfg: FlightConfig | None = None
        self.setWindowTitle("BlackBox Analyzer")
        self.resize(1280, 800)
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
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 6)
        root.setSpacing(6)

        # --- Barre supérieure : drop + profil ---
        top_bar = QHBoxLayout()

        self.drop_area = DropArea()
        self.drop_area.file_dropped.connect(self._on_file_dropped)
        top_bar.addWidget(self.drop_area, stretch=1)

        # Sélecteur de profil drone
        profile_box = QWidget()
        profile_layout = QVBoxLayout(profile_box)
        profile_layout.setContentsMargins(8, 0, 0, 0)
        profile_layout.setSpacing(4)
        profile_layout.addWidget(QLabel("Profil drone"))
        self.size_combo = QComboBox()
        self.size_combo.addItems(DRONE_SIZES)
        self.size_combo.setCurrentText('5"')
        self.size_combo.setToolTip(
            "Taille du drone — détermine les limites de changement PID\n"
            "3\" : jusqu'à ±45%\n5\" : ±25%\n6\" : ±35%\n7\" : ±45%\n10\" : ±55%"
        )
        self.size_combo.currentTextChanged.connect(self._on_profile_changed)
        profile_layout.addWidget(self.size_combo)
        top_bar.addWidget(profile_box)
        root.addLayout(top_bar)

        # --- Onglets principaux (sessions) ---
        self.session_tabs = QTabWidget()
        self.session_tabs.setVisible(False)
        root.addWidget(self.session_tabs, stretch=1)

        self.status = QStatusBar()
        self.setStatusBar(self.status)

    # ------------------------------------------------------------------
    # Chargement fichier
    # ------------------------------------------------------------------

    def _on_file_dropped(self, path: str):
        name = Path(path).name
        self.status.showMessage(f"Décodage en cours : {name} …")
        self.session_tabs.clear()
        self.session_tabs.setVisible(False)

        # Lecture en-tête BBL
        try:
            self._last_cfg = parse_header(path)
        except Exception:
            self._last_cfg = FlightConfig()

        # Auto-suggestion de taille depuis le nom du craft/board
        hint = self._last_cfg.size_hint()
        if hint and hint in DRONE_SIZES:
            self.size_combo.blockSignals(True)
            self.size_combo.setCurrentText(hint)
            self.size_combo.blockSignals(False)

        # Décodage CSV
        try:
            sessions = self.parser.decode(path)
        except Exception as exc:
            self.status.showMessage(f"Erreur : {exc}")
            self.drop_area.setText(f"✗  Échec du chargement de {name}")
            return

        for i, df in enumerate(sessions):
            tab = self._build_session_tab(df, self._last_cfg)
            dur = self._duration(df)
            self.session_tabs.addTab(tab, f"Session {i + 1}  ({dur})")

        self.session_tabs.setVisible(True)
        total_rows = sum(len(s) for s in sessions)
        self.status.showMessage(
            f"✓  {name}  —  {len(sessions)} session(s), {total_rows:,} points"
        )
        self.drop_area.setText(
            f"✓  {name}  —  {len(sessions)} session(s)   "
            "(glissez un autre fichier pour remplacer)"
        )

    def _on_profile_changed(self, size: str):
        """Relance l'analyse si un fichier est déjà chargé."""
        if self._last_cfg is None or self.session_tabs.count() == 0:
            return
        # Reconstruit les onglets de diagnostic pour chaque session
        for i in range(self.session_tabs.count()):
            widget = self.session_tabs.widget(i)
            inner_tabs = widget.findChild(QTabWidget)
            if inner_tabs is None:
                continue
            # Cherche l'onglet "Diagnostic" existant (index connu)
            diag_idx = None
            for j in range(inner_tabs.count()):
                if 'Diag' in inner_tabs.tabText(j):
                    diag_idx = j
                    break
            if diag_idx is None:
                continue
            # Récupère la DataFrame stockée dans le widget
            df = widget.property('df')
            if df is None:
                continue
            new_diag = self._build_diagnostic(df, self._last_cfg, size)
            inner_tabs.removeTab(diag_idx)
            inner_tabs.insertTab(diag_idx, new_diag, "🔍 Diagnostic")
            inner_tabs.setCurrentIndex(diag_idx)

    # ------------------------------------------------------------------
    # Construction des onglets par session
    # ------------------------------------------------------------------

    def _build_session_tab(self, df: pd.DataFrame, cfg: FlightConfig) -> QWidget:
        widget = QWidget()
        widget.setProperty('df', df)  # stocke la df pour pouvoir relancer l'analyse
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 2, 0, 0)

        inner = QTabWidget()

        inner.addTab(GyroPlotWidget(df), "〰 Gyroscope")

        for i, axis_name in enumerate(AXIS_NAMES):
            if f'axisP[{i}]' in df.columns:
                inner.addTab(PidPlotWidget(df, i, axis_name), f"PID {axis_name}")

        if 'motor[0]' in df.columns:
            inner.addTab(MotorPlotWidget(df), "⚙ Moteurs")

        diag = self._build_diagnostic(df, cfg, self.size_combo.currentText())
        inner.addTab(diag, "🔍 Diagnostic")

        layout.addWidget(inner)
        return widget

    def _build_diagnostic(self, df: pd.DataFrame, cfg: FlightConfig,
                           drone_size: str) -> DiagnosticWidget:
        session_analysis = analyze(df, cfg)
        report = generate_report(session_analysis, cfg, drone_size)
        return DiagnosticWidget(cfg, report, drone_size)

    @staticmethod
    def _duration(df: pd.DataFrame) -> str:
        if 'time_s' not in df.columns or df.empty:
            return "?"
        secs = float(df['time_s'].iloc[-1] - df['time_s'].iloc[0])
        return f"{int(secs//60)}m{int(secs%60):02d}s" if secs >= 60 else f"{secs:.1f}s"
