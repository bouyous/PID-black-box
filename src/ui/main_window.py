from pathlib import Path

import pandas as pd
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDropEvent
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSlider,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from analysis.analyzer import SessionAnalysis, analyze
from analysis.header_parser import FlightConfig, parse_header
from analysis.recommender import DiagnosticReport, FlightFeel, generate_report
from parser.blackbox_parser import BlackboxParser
from ui.comparison_widget import ComparisonWidget
from ui.fft_widget import FftWidget
from ui.plot_widget import GyroPlotWidget, MotorPlotWidget, PidPlotWidget
from ui.recommendation_panel import DiagnosticWidget

SUPPORTED_EXTS = {'.bbl', '.bfl'}
AXIS_NAMES = ['Roll', 'Pitch', 'Yaw']
DRONE_SIZES = ['3"', '5"', '6"', '7"', '10"']
FLYING_STYLES = ['Freestyle', 'Racing', 'Long Range', 'Bangers']
BATTERY_OPTIONS = ['Auto', '2S', '3S', '4S', '6S', '8S', '12S']

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
QPushButton {
    background: #252525;
    color: #e0e0e0;
    border: 1px solid #444;
    padding: 4px 10px;
    border-radius: 4px;
}
QPushButton:hover { background: #333; }
QPushButton:disabled { color: #555; border-color: #333; }
"""


class FeelSlidersBox(QFrame):
    """4 sliders 1..5 pour capter le ressenti du pilote.
    3 = neutre (respecte juste le style). S'écarter de 3 biaise les recos."""

    SLIDERS = [
        # (attr, title, left_label, right_label, tooltip)
        ('locked',          "Ressenti locké",
         "flou / libre", "ultra locké",
         "Comment vous vouliez que le drone se comporte sur les sticks.\n"
         "Plus vers 5 = FF et D poussés pour être « rivé »."),
        ('wind_stability',  "Stabilité au vent",
         "peu important", "imperturbable",
         "Plus vers 5 = I plus haut, dérive traquée de plus près.\n"
         "Utile en Long Range."),
        ('responsiveness',  "Réactivité sticks",
         "doux", "vif",
         "Plus vers 5 = temps de montée plus serré (P/FF poussés).\n"
         "Autorise un peu plus d'overshoot."),
        ('propwash_clean',  "Propreté post-manœuvre",
         "tolère", "impeccable",
         "Plus vers 5 = D_min remonté, cible prop wash resserrée."),
    ]

    def __init__(self):
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "FeelSlidersBox { background:#1f1f1f; border:1px solid #333; border-radius:4px; }"
            "QLabel { color:#bbb; font-size:11px; }"
            "QSlider::groove:horizontal { height:4px; background:#333; border-radius:2px; }"
            "QSlider::sub-page:horizontal { background:#4a9eff; border-radius:2px; }"
            "QSlider::handle:horizontal {"
            " background:#4a9eff; width:12px; margin:-5px 0; border-radius:6px; }"
        )
        grid = QGridLayout(self)
        grid.setContentsMargins(8, 4, 8, 4)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(2)

        title = QLabel("Ressenti en vol  (3 = neutre)")
        title.setStyleSheet("color:#888; font-size:10px;")
        grid.addWidget(title, 0, 0, 1, 4)

        self._sliders: dict[str, QSlider] = {}
        for row, (attr, label, lo_lbl, hi_lbl, tt) in enumerate(self.SLIDERS, start=1):
            name = QLabel(label)
            name.setToolTip(tt)
            name.setFixedWidth(150)
            grid.addWidget(name, row, 0)

            lo = QLabel(lo_lbl)
            lo.setStyleSheet("color:#666; font-size:10px;")
            lo.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            grid.addWidget(lo, row, 1)

            s = QSlider(Qt.Orientation.Horizontal)
            s.setMinimum(1)
            s.setMaximum(5)
            s.setValue(3)
            s.setFixedWidth(90)
            s.setToolTip(tt)
            s.setTickPosition(QSlider.TickPosition.TicksBelow)
            s.setTickInterval(1)
            grid.addWidget(s, row, 2)
            self._sliders[attr] = s

            hi = QLabel(hi_lbl)
            hi.setStyleSheet("color:#666; font-size:10px;")
            grid.addWidget(hi, row, 3)

    def current_feel(self) -> FlightFeel:
        return FlightFeel(
            locked=self._sliders['locked'].value(),
            wind_stability=self._sliders['wind_stability'].value(),
            responsiveness=self._sliders['responsiveness'].value(),
            propwash_clean=self._sliders['propwash_clean'].value(),
        )

    def reset(self):
        for s in self._sliders.values():
            s.setValue(3)


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

        # Référence pour comparaison avant/après
        self._reference: dict | None = None   # {file, sessions, analyses, reports, cfg, size, style}

        self.setWindowTitle("BlackBox Analyzer")
        self.resize(1280, 800)
        self.setStyleSheet(DARK_STYLE)
        self._build_ui()

        if not self.parser.is_ready():
            self.status.showMessage(
                "  blackbox_decode.exe introuvable — voir tools/README.md", 0
            )
        else:
            self.status.showMessage("Prêt — glissez un fichier blackbox pour commencer.")

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 6)
        root.setSpacing(6)

        # --- Barre supérieure ---
        top_bar = QHBoxLayout()

        self.drop_area = DropArea()
        self.drop_area.file_dropped.connect(self._on_file_dropped)
        top_bar.addWidget(self.drop_area, stretch=1)

        # Sélecteur taille drone (pas d'auto-refresh — on attend clic Appliquer)
        top_bar.addWidget(self._make_selector_box(
            "Taille drone", DRONE_SIZES, '5"',
            "3\" : ±45%\n5\" : ±25%\n6\" : ±35%\n7\" : ±45%\n10\" : ±55%",
            '_size_combo'
        ))

        # Sélecteur style de vol
        top_bar.addWidget(self._make_selector_box(
            "Style de vol", FLYING_STYLES, 'Freestyle',
            "Freestyle : drone hyper loqué, FF agressif\n"
            "Racing : réactivité max, tracking serré\n"
            "Long Range : souple, FF bas, insensible au vent\n"
            "Bangers : tolérant (indoor, crash probable)",
            '_style_combo'
        ))

        # Sélecteur batterie
        top_bar.addWidget(self._make_selector_box(
            "Batterie", BATTERY_OPTIONS, 'Auto',
            "Auto = détecté depuis la tension BBL\n"
            "Forcer si le vol de test n'était pas sur la batterie habituelle",
            '_battery_combo'
        ))

        # Bouton Appliquer sous les sélecteurs
        apply_box = QWidget()
        apply_lay = QVBoxLayout(apply_box)
        apply_lay.setContentsMargins(8, 0, 0, 0)
        apply_lay.setSpacing(4)
        apply_lay.addWidget(QLabel(" "))  # aligne verticalement avec les combos
        self._btn_apply = QPushButton("✓ Appliquer")
        self._btn_apply.setToolTip(
            "Recalcule le diagnostic avec le profil sélectionné.\n"
            "Comparez Freestyle et Long Range pour voir la différence."
        )
        self._btn_apply.setStyleSheet(
            "QPushButton { background:#2d5a3d; color:#fff; border:1px solid #3e7a55;"
            " padding:6px 14px; border-radius:4px; font-weight:bold; }"
            "QPushButton:hover { background:#3a7050; }"
            "QPushButton:disabled { background:#252525; color:#555; border-color:#333; }"
        )
        self._btn_apply.setEnabled(False)
        self._btn_apply.clicked.connect(self._on_profile_changed)
        apply_lay.addWidget(self._btn_apply)
        top_bar.addWidget(apply_box)

        root.addLayout(top_bar)

        # --- Ressenti pilote (sliders 1-5) ---
        feel_bar = QHBoxLayout()
        feel_bar.setContentsMargins(0, 0, 0, 0)
        self._feel_box = FeelSlidersBox()
        feel_bar.addWidget(self._feel_box, stretch=1)
        root.addLayout(feel_bar)

        # --- Bouton comparer ---
        cmp_bar = QHBoxLayout()
        self._btn_set_ref = QPushButton("💾  Définir comme référence")
        self._btn_set_ref.setToolTip(
            "Mémorise ce vol comme référence.\n"
            "Chargez ensuite un nouveau vol pour comparer avant/après."
        )
        self._btn_set_ref.setEnabled(False)
        self._btn_set_ref.clicked.connect(self._set_as_reference)
        cmp_bar.addWidget(self._btn_set_ref)

        self._ref_label = QLabel("")
        self._ref_label.setStyleSheet("color:#4a9eff; font-size:11px;")
        cmp_bar.addWidget(self._ref_label)
        cmp_bar.addStretch()

        self._btn_load_compare = QPushButton("📂  Ouvrir un fichier…")
        self._btn_load_compare.setToolTip("Ouvrir un fichier BBL via l'explorateur")
        self._btn_load_compare.clicked.connect(self._open_file_dialog)
        cmp_bar.addWidget(self._btn_load_compare)

        root.addLayout(cmp_bar)

        # --- Onglets sessions ---
        self.session_tabs = QTabWidget()
        self.session_tabs.setVisible(False)
        root.addWidget(self.session_tabs, stretch=1)

        self.status = QStatusBar()
        self.setStatusBar(self.status)

    def _make_selector_box(self, label_text, items, default, tooltip,
                           attr_name) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(8, 0, 0, 0)
        layout.setSpacing(4)
        layout.addWidget(QLabel(label_text))
        combo = QComboBox()
        combo.addItems(items)
        combo.setCurrentText(default)
        combo.setToolTip(tooltip)
        layout.addWidget(combo)
        setattr(self, attr_name, combo)
        return box

    # ------------------------------------------------------------------
    # Chargement fichier
    # ------------------------------------------------------------------

    def _open_file_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Ouvrir un fichier blackbox", "",
            "Blackbox files (*.bbl *.bfl);;All files (*)"
        )
        if path:
            self._on_file_dropped(path)

    def _on_file_dropped(self, path: str):
        name = Path(path).name
        self.status.showMessage(f"Décodage en cours : {name} …")
        self.session_tabs.clear()
        self.session_tabs.setVisible(False)

        try:
            self._last_cfg = parse_header(path)
        except Exception:
            self._last_cfg = FlightConfig()

        # Auto-suggestion taille
        hint = self._last_cfg.size_hint()
        if hint and hint in DRONE_SIZES:
            self._size_combo.blockSignals(True)
            self._size_combo.setCurrentText(hint)
            self._size_combo.blockSignals(False)

        try:
            sessions = self.parser.decode(path)
        except Exception as exc:
            self.status.showMessage(f"Erreur : {exc}")
            self.drop_area.setText(f"Échec du chargement de {name}")
            return

        # Calcule analyses + rapports
        size    = self._size_combo.currentText()
        style   = self._style_combo.currentText()
        battery = self._battery_combo.currentText()
        bat_cells = int(battery[:-1]) if battery != 'Auto' else 0

        feel = self._feel_box.current_feel()
        session_analyses = []
        session_reports  = []
        for i, df in enumerate(sessions):
            sa = analyze(df, self._last_cfg)
            rp = generate_report(sa, self._last_cfg, size, style, bat_cells, feel)
            session_analyses.append(sa)
            session_reports.append(rp)
            tab = self._build_session_tab(df, self._last_cfg, sa, rp)
            dur = self._duration(df)
            self.session_tabs.addTab(tab, f"Session {i + 1}  ({dur})")

        # Si référence disponible → ajouter un onglet de comparaison
        if self._reference is not None and session_analyses:
            cmp_tab = self._build_comparison_tab(
                session_analyses[0], session_reports[0],
                self._last_cfg, size, style, name
            )
            self.session_tabs.addTab(cmp_tab, "📊  Comparaison")
            self.session_tabs.setCurrentIndex(self.session_tabs.count() - 1)

        # Stocke le contexte courant pour usage futur
        self._current_context = {
            'file': name, 'sessions': sessions,
            'analyses': session_analyses, 'reports': session_reports,
            'cfg': self._last_cfg, 'size': size, 'style': style,
        }

        self.session_tabs.setVisible(True)
        total_rows = sum(len(s) for s in sessions)
        self.status.showMessage(
            f"  {name}  —  {len(sessions)} session(s), {total_rows:,} points"
        )
        self.drop_area.setText(
            f"  {name}  —  {len(sessions)} session(s)   "
            "(glissez un autre fichier pour remplacer)"
        )
        self._btn_set_ref.setEnabled(True)
        self._btn_apply.setEnabled(True)

    def _on_profile_changed(self, _=None):
        """Relance l'analyse si un fichier est déjà chargé."""
        if self._last_cfg is None or self.session_tabs.count() == 0:
            return
        size    = self._size_combo.currentText()
        style   = self._style_combo.currentText()
        battery = self._battery_combo.currentText()
        bat_cells = int(battery[:-1]) if battery != 'Auto' else 0

        for i in range(self.session_tabs.count()):
            if self.session_tabs.tabText(i).startswith("📊"):
                continue
            widget = self.session_tabs.widget(i)
            inner_tabs = widget.findChild(QTabWidget)
            if inner_tabs is None:
                continue
            diag_idx = None
            for j in range(inner_tabs.count()):
                if 'Diag' in inner_tabs.tabText(j):
                    diag_idx = j
                    break
            if diag_idx is None:
                continue
            sa = getattr(widget, '_sa', None)
            if sa is None:
                continue
            feel = self._feel_box.current_feel()
            rp = generate_report(sa, self._last_cfg, size, style, bat_cells, feel)
            new_diag = DiagnosticWidget(self._last_cfg, rp, size)
            inner_tabs.removeTab(diag_idx)
            inner_tabs.insertTab(diag_idx, new_diag, "Diagnostic")
            inner_tabs.setCurrentIndex(diag_idx)
        self.status.showMessage(
            f"Profil appliqué : {size} / {style}"
            + (f" / {battery}" if battery != 'Auto' else "")
        )

    # ------------------------------------------------------------------
    # Référence pour comparaison
    # ------------------------------------------------------------------

    def _set_as_reference(self):
        if not hasattr(self, '_current_context'):
            return
        ctx = self._current_context
        self._reference = dict(ctx)
        self._ref_label.setText(
            f"Référence : {ctx['file']}  ({ctx['size']} / {ctx['style']})"
        )
        self.status.showMessage(
            f"Référence mémorisée : {ctx['file']}. "
            "Chargez un nouveau vol pour comparer."
        )

    def _build_comparison_tab(self, new_sa: SessionAnalysis, new_rp: DiagnosticReport,
                              new_cfg: FlightConfig, size: str, style: str,
                              new_name: str) -> QWidget:
        ref = self._reference
        ref_sa = ref['analyses'][0] if ref['analyses'] else None
        ref_rp = ref['reports'][0] if ref['reports'] else None
        if ref_sa is None or ref_rp is None:
            w = QWidget()
            QVBoxLayout(w).addWidget(QLabel("Données de référence incomplètes."))
            return w
        return ComparisonWidget(
            ref_sa, ref_rp, ref['cfg'], ref['file'],
            new_sa, new_rp, new_cfg, new_name,
            size, style
        )

    # ------------------------------------------------------------------
    # Construction des onglets par session
    # ------------------------------------------------------------------

    def _build_session_tab(self, df: pd.DataFrame, cfg: FlightConfig,
                            sa: SessionAnalysis, rp: DiagnosticReport) -> QWidget:
        widget = QWidget()
        widget._df = df
        widget._sa = sa
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 2, 0, 0)

        inner = QTabWidget()
        inner.addTab(GyroPlotWidget(df), "Gyroscope")
        for i, axis_name in enumerate(AXIS_NAMES):
            if f'axisP[{i}]' in df.columns:
                inner.addTab(PidPlotWidget(df, i, axis_name), f"PID {axis_name}")
        if 'motor[0]' in df.columns:
            inner.addTab(MotorPlotWidget(df), "Moteurs")
        inner.addTab(FftWidget(df, cfg), "FFT")
        inner.addTab(DiagnosticWidget(cfg, rp, self._size_combo.currentText()), "Diagnostic")

        layout.addWidget(inner)
        return widget

    @staticmethod
    def _duration(df: pd.DataFrame) -> str:
        if 'time_s' not in df.columns or df.empty:
            return "?"
        secs = float(df['time_s'].iloc[-1] - df['time_s'].iloc[0])
        return f"{int(secs//60)}m{int(secs%60):02d}s" if secs >= 60 else f"{secs:.1f}s"
