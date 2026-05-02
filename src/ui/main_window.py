"""
Fenêtre principale BlackBox Analyzer (refonte v1.9.0).

Architecture inspirée Betaflight Configurator + Task Manager Windows :
  ┌──────────┬───────────────────────────────────────────────┐
  │ rail     │ MotorTempBar (toujours visible, non scrollée) │
  │ sidebar  ├───────────────────────────────────────────────┤
  │ + burger │ QStackedWidget (vue sélectionnée plein écran) │
  │ + nav    │   - welcome / diagnostic / gyroscope / ...    │
  │          │                                               │
  │ apply    │                                               │
  │ ref      │                                               │
  └──────────┴───────────────────────────────────────────────┘

Drag & drop : la fenêtre entière est drop target — pas de zone dédiée.
Overlay semi-transparent affiché pendant le drag.

Adaptive sizing : showMaximized() au démarrage + minimumSize 1024x600.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
from PyQt6.QtCore import Qt, QThread, QTimer, pyqtSignal
from PyQt6.QtGui import QDragEnterEvent, QDragLeaveEvent, QDropEvent
from PyQt6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSlider,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from analysis.analyzer import SessionAnalysis, analyze
from analysis.header_parser import FlightConfig, parse_header
from analysis.recommender import (
    DiagnosticReport, FlightFeel, FrameType, MotorTemp, PilotFeedback,
    generate_report,
)
from parser.blackbox_parser import BlackboxParser
from ui.comparison_widget import ComparisonWidget
from ui.drop_overlay import DropOverlay
from ui.fft_widget import FftWidget
from ui.motor_temp_bar import MotorTempBar
from ui.plot_widget import GyroPlotWidget, MotorPlotWidget, PidPlotWidget
from ui.recommendation_panel import DiagnosticWidget
from ui.sidebar import RailSidebar


SUPPORTED_EXTS  = {'.bbl', '.bfl'}
AXIS_NAMES      = ['Roll', 'Pitch', 'Yaw']
DRONE_SIZES     = ['2.5"', '3"', '5"', '6"', '7"', '10"']
FLYING_STYLES   = ['Freestyle', 'Racing', 'Long Range', 'Bangers', 'Ciné Whoop']
BATTERY_OPTIONS = ['Auto', '2S', '3S', '4S', '6S', '8S', '12S']
FRAME_TYPES = [
    'Standard',
    'Unibody (Marmotte, etc.)',
    'Souple / Ancien (Lumenier 4-5 ans, copie)',
]
FRAME_TYPE_MAP = {
    'Standard':                                  FrameType.STANDARD,
    'Unibody (Marmotte, etc.)':                  FrameType.UNIBODY,
    'Souple / Ancien (Lumenier 4-5 ans, copie)': FrameType.SOFT,
}


# --------------------------------------------------------------------------
# Style global
# --------------------------------------------------------------------------

DARK_STYLE = """
QMainWindow, QWidget { background:#1e1e1e; color:#e0e0e0; }
QStatusBar           { background:#111;   color:#999; font-size:12px; }

QTabWidget::pane     { border:1px solid #2d2d2d; background:#1e1e1e; }
QTabBar::tab         { background:#252525; color:#bbb; padding:6px 14px;
                       border:1px solid #2d2d2d; border-bottom:none; }
QTabBar::tab:selected{ background:#1e1e1e; color:#fff; border-bottom:2px solid #4a9eff; }
QTabBar::tab:hover   { background:#2f2f2f; }

QComboBox            { background:#2a2a2a; color:#e0e0e0; border:1px solid #444;
                       padding:4px 8px; border-radius:3px; }
QComboBox::drop-down { border:none; }
QComboBox QAbstractItemView { background:#2a2a2a; color:#e0e0e0;
                              selection-background-color:#3a3a3a; }

QPushButton          { background:#2a2a2a; color:#e0e0e0; border:1px solid #444;
                       padding:5px 12px; border-radius:3px; }
QPushButton:hover    { background:#333; border-color:#555; }
QPushButton:disabled { color:#555; border-color:#2d2d2d; }

QGroupBox            { color:#888; border:1px solid #2d2d2d; border-radius:3px;
                       margin-top:10px; padding:8px; }
QGroupBox::title     { subcontrol-origin: margin; left:8px; }

QSplitter::handle    { background:#2d2d2d; width:4px; }
QSplitter::handle:hover { background:#4a9eff; }

QScrollBar:vertical  { background:#1e1e1e; width:10px; margin:0; }
QScrollBar::handle:vertical { background:#3a3a3a; min-height:30px; border-radius:5px; }
QScrollBar::handle:vertical:hover { background:#4a9eff; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { background:transparent; height:0; }
"""


# --------------------------------------------------------------------------
# Widgets de saisie pilote (sliders / 5 Y/N) — repris de l'ancienne UI
# --------------------------------------------------------------------------

class FeelSlidersBox(QFrame):
    """4 sliders 1..5 pour capter le ressenti pilote. 3 = neutre."""

    SLIDERS = [
        ('locked',         "🔒  Locké",          "flou",    "rivé",
         "Plus vers 5 = FF et D poussés — drone vissé aux sticks."),
        ('wind_stability', "💨  Stabilité vent",  "peu",     "imperturbable",
         "Plus vers 5 = I plus haut, dérive traquée de plus près. Utile en LR."),
        ('responsiveness', "⚡  Réactivité",      "doux",    "vif",
         "Plus vers 5 = temps de montée plus court (P/FF poussés)."),
        ('propwash_clean', "✨  Propreté",        "tolère",  "impeccable",
         "Plus vers 5 = D_min remonté, prop wash resserré."),
    ]

    def __init__(self):
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "FeelSlidersBox { background:#1f1f1f; border:1px solid #333; border-radius:4px; }"
            "QSlider::groove:horizontal { height:6px; background:#333; border-radius:3px; }"
            "QSlider::sub-page:horizontal { background:#4a9eff; border-radius:3px; }"
            "QSlider::add-page:horizontal { background:#2a2a2a; border-radius:3px; }"
            "QSlider::handle:horizontal {"
            " background:#4a9eff; width:16px; margin:-6px 0; border-radius:8px;"
            " border:2px solid #1f1f1f; }"
            "QSlider::handle:horizontal:hover { background:#6cb0ff; }"
        )
        grid = QGridLayout(self)
        grid.setContentsMargins(12, 8, 12, 8)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)

        title = QLabel("Ressenti en vol  (3 = neutre)")
        title.setStyleSheet("color:#bbb; font-size:14px; font-weight:bold; letter-spacing:1px;")
        grid.addWidget(title, 0, 0, 1, 5)

        self._sliders: dict[str, QSlider] = {}
        self._value_labels: dict[str, QLabel] = {}
        for row, (attr, label, lo_lbl, hi_lbl, tt) in enumerate(self.SLIDERS, start=1):
            name = QLabel(label)
            name.setToolTip(tt)
            name.setMinimumWidth(160)
            name.setStyleSheet("color:#e0e0e0; font-size:13px; font-weight:600;")
            grid.addWidget(name, row, 0)

            lo = QLabel(lo_lbl)
            lo.setStyleSheet("color:#888; font-size:12px;")
            lo.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            lo.setMinimumWidth(80)
            grid.addWidget(lo, row, 1)

            s = QSlider(Qt.Orientation.Horizontal)
            s.setMinimum(1); s.setMaximum(5); s.setValue(3)
            s.setMinimumWidth(160)
            s.setToolTip(tt)
            s.setTickPosition(QSlider.TickPosition.TicksBelow)
            s.setTickInterval(1)
            s.valueChanged.connect(lambda v, a=attr: self._on_changed(a, v))
            grid.addWidget(s, row, 2)
            self._sliders[attr] = s

            hi = QLabel(hi_lbl)
            hi.setStyleSheet("color:#888; font-size:12px;")
            hi.setMinimumWidth(110)
            grid.addWidget(hi, row, 3)

            val = QLabel("3")
            val.setStyleSheet(
                "color:#4a9eff; font-size:16px; font-weight:bold;"
                " background:#2a2a2a; border:1px solid #444; border-radius:4px;"
                " padding:2px 10px; min-width:24px;"
            )
            val.setAlignment(Qt.AlignmentFlag.AlignCenter)
            grid.addWidget(val, row, 4)
            self._value_labels[attr] = val

        grid.setColumnStretch(2, 1)

    def _on_changed(self, attr: str, value: int):
        self._value_labels[attr].setText(str(value))

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


class PilotFeedbackBox(QFrame):
    """5 questions oui/non posées au pilote après le vol de test."""

    QUESTIONS = [
        ('improved',        "Y a-t-il eu une amélioration ?"),
        ('has_rebounds',    "Y a-t-il des rebonds (gaz / sortie virage) ?"),
        ('has_propwash',    "Y a-t-il encore du propwash ?"),
        ('locked_enough',   "Le drone est-il suffisamment locké ?"),
        ('reactive_enough', "Le drone est-il suffisamment réactif ?"),
    ]

    feedback_changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self._answers: dict[str, bool | None] = {q: None for q, _ in self.QUESTIONS}
        self._buttons: dict[str, tuple[QPushButton, QPushButton]] = {}

        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "PilotFeedbackBox { background:#1f1f1f; border:1px solid #333; border-radius:4px; }"
        )
        grid = QGridLayout(self)
        grid.setContentsMargins(12, 8, 12, 8)
        grid.setHorizontalSpacing(10)
        grid.setVerticalSpacing(5)

        title = QLabel("📝  Ressenti après le vol de test")
        title.setStyleSheet("color:#bbb; font-size:13px; font-weight:bold; letter-spacing:1px;")
        grid.addWidget(title, 0, 0, 1, 4)

        for row, (key, label_text) in enumerate(self.QUESTIONS, start=1):
            lbl = QLabel(label_text)
            lbl.setStyleSheet("color:#e0e0e0; font-size:13px;")
            lbl.setMinimumWidth(330)
            grid.addWidget(lbl, row, 0)

            btn_yes = QPushButton("Oui")
            btn_no  = QPushButton("Non")
            btn_yes.setCheckable(True); btn_no.setCheckable(True)
            btn_yes.setMinimumWidth(60); btn_no.setMinimumWidth(60)
            self._restyle(btn_yes, None, True)
            self._restyle(btn_no,  None, False)
            btn_yes.clicked.connect(lambda _c, k=key: self._set(k, True))
            btn_no.clicked.connect(lambda _c, k=key: self._set(k, False))
            grid.addWidget(btn_yes, row, 1)
            grid.addWidget(btn_no,  row, 2)
            self._buttons[key] = (btn_yes, btn_no)

        self._status = QLabel("0/5 réponses — réponds aux 5 questions pour générer le CLI.")
        self._status.setStyleSheet("color:#888; font-size:12px; font-style:italic;")
        grid.addWidget(self._status, len(self.QUESTIONS) + 1, 0, 1, 3)

        btn_reset = QPushButton("↺ Réinitialiser")
        btn_reset.setToolTip("Efface toutes les réponses")
        btn_reset.clicked.connect(self.reset)
        grid.addWidget(btn_reset, len(self.QUESTIONS) + 1, 3)

        grid.setColumnStretch(0, 1)

    @staticmethod
    def _restyle(btn: QPushButton, current: bool | None, is_yes_btn: bool):
        is_selected = (current is True and is_yes_btn) or (current is False and not is_yes_btn)
        accent = "#3d6e3d" if is_yes_btn else "#a04030"
        if is_selected:
            btn.setStyleSheet(
                f"QPushButton {{ background:{accent}; color:#fff;"
                f" border:2px solid #fff; border-radius:4px;"
                f" padding:4px 10px; font-weight:bold; font-size:13px; }}"
            )
            btn.setChecked(True)
        else:
            btn.setStyleSheet(
                f"QPushButton {{ background:#252525; color:#ccc;"
                f" border:1px solid {accent}; border-radius:4px;"
                f" padding:4px 10px; font-size:13px; }}"
                f" QPushButton:hover {{ background:#333; color:#fff; }}"
            )
            btn.setChecked(False)

    def _set(self, key: str, value: bool):
        if self._answers[key] == value:
            self._answers[key] = None
        else:
            self._answers[key] = value
        btn_yes, btn_no = self._buttons[key]
        self._restyle(btn_yes, self._answers[key], True)
        self._restyle(btn_no,  self._answers[key], False)
        self._refresh_status()
        self.feedback_changed.emit()

    def _refresh_status(self):
        answered = sum(1 for v in self._answers.values() if v is not None)
        if answered == 5:
            self._status.setText("✅ 5/5 réponses — clique « Appliquer » pour générer le CLI.")
            self._status.setStyleSheet("color:#5fc46e; font-size:12px; font-weight:bold;")
        else:
            self._status.setText(
                f"{answered}/5 réponses — réponds aux 5 questions pour générer le CLI."
            )
            self._status.setStyleSheet("color:#888; font-size:12px; font-style:italic;")

    def current(self) -> PilotFeedback:
        return PilotFeedback(**self._answers)

    def is_complete(self) -> bool:
        return all(v is not None for v in self._answers.values())

    def reset(self):
        for k in self._answers:
            self._answers[k] = None
            btn_yes, btn_no = self._buttons[k]
            self._restyle(btn_yes, None, True)
            self._restyle(btn_no,  None, False)
        self._refresh_status()
        self.feedback_changed.emit()


# --------------------------------------------------------------------------
# DecodeWorker
# --------------------------------------------------------------------------

class DecodeWorker(QThread):
    """Décode un fichier BBL dans un thread séparé — évite de bloquer l'UI."""
    done  = pyqtSignal(list)
    error = pyqtSignal(str)

    def __init__(self, parser, path: str):
        super().__init__()
        self._parser = parser
        self._path   = path

    def run(self):
        try:
            sessions = self._parser.decode(self._path)
            self.done.emit(sessions)
        except Exception as exc:
            self.error.emit(str(exc))


# --------------------------------------------------------------------------
# Vue d'accueil (affichée tant qu'aucun fichier n'est chargé)
# --------------------------------------------------------------------------

class WelcomeView(QWidget):
    open_file_clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(20)

        icon = QLabel("✈")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("color:#4a9eff; font-size:96px;")
        layout.addWidget(icon)

        title = QLabel("BlackBox Analyzer")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "color:#fff; font-size:28px; font-weight:bold; letter-spacing:2px;"
        )
        layout.addWidget(title)

        subtitle = QLabel(
            "Glissez un fichier .bbl ou .bfl n'importe où sur la fenêtre\n"
            "ou utilisez le bouton ci-dessous"
        )
        subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        subtitle.setStyleSheet("color:#888; font-size:14px; line-height:1.5;")
        layout.addWidget(subtitle)

        btn = QPushButton("📂   Ouvrir un fichier blackbox…")
        btn.setMinimumHeight(44)
        btn.setMinimumWidth(280)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                background:#2d5a3d; color:#fff; border:1px solid #3e7a55;
                border-radius:4px; padding:8px 24px; font-size:14px; font-weight:bold;
            }
            QPushButton:hover { background:#3a7050; border-color:#5aa078; }
        """)
        btn.clicked.connect(self.open_file_clicked.emit)
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_row.addWidget(btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Tip
        tip = QLabel(
            "💡  Compatible Betaflight 4.5+   ·   Multi-plateformes   ·   "
            "Gratuit et libre"
        )
        tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        tip.setStyleSheet("color:#555; font-size:11px; padding-top:24px;")
        layout.addWidget(tip)


# --------------------------------------------------------------------------
# Vue Profil & Ressenti (paramètres + sliders + 5 Y/N)
# --------------------------------------------------------------------------

class ProfileView(QScrollArea):
    """Vue plein écran pour configurer profil + ressenti.
    Scrollable verticalement si l'écran est petit."""

    profile_changed = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        content = QWidget()
        self.setWidget(content)
        layout = QVBoxLayout(content)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        # Titre
        title = QLabel("🎯  Profil de vol & ressenti pilote")
        title.setStyleSheet("color:#fff; font-size:18px; font-weight:bold; letter-spacing:1px;")
        layout.addWidget(title)

        # ---- Sélecteurs ----
        sel_box = QFrame()
        sel_box.setFrameShape(QFrame.Shape.StyledPanel)
        sel_box.setStyleSheet(
            "QFrame { background:#1f1f1f; border:1px solid #333; border-radius:4px; }"
        )
        sel_lay = QHBoxLayout(sel_box)
        sel_lay.setContentsMargins(12, 12, 12, 12)
        sel_lay.setSpacing(20)

        self.size_combo  = self._make_combo("Taille drone", DRONE_SIZES,     '5"',
                                             "Taille des hélices — calibre tous les seuils.")
        self.style_combo = self._make_combo("Style de vol",  FLYING_STYLES,   'Freestyle',
                                             "Freestyle / Racing / Long Range / Bangers / Ciné Whoop")
        self.batt_combo  = self._make_combo("Batterie",     BATTERY_OPTIONS, 'Auto',
                                             "Auto = détectée depuis la BBL")
        self.frame_combo = self._make_combo(
            "Type de châssis", FRAME_TYPES, 'Standard',
            "Standard = châssis FPV moderne 5 mm bras détachés.\n"
            "Unibody = monobloc taillé masse (Armattan Marmotte, Source One v5).\n"
            "  Si vis moteur OK, vibration ≠ problème de visserie.\n"
            "Souple / Ancien = Lumenier 4-5 ans, copie chinoise, frame fatigué.\n"
            "  Vibrations structurelles à filtrer plutôt qu'à serrer."
        )
        for w in (self.size_combo, self.style_combo, self.batt_combo,
                  self.frame_combo):
            sel_lay.addWidget(w)
        sel_lay.addStretch()

        layout.addWidget(sel_box)

        # ---- Ressenti sliders ----
        self.feel_box = FeelSlidersBox()
        layout.addWidget(self.feel_box)

        # ---- 5 questions ----
        self.pilot_fb = PilotFeedbackBox()
        layout.addWidget(self.pilot_fb)

        layout.addStretch()

        # Émet le signal quand le profil change (pour update auto)
        self.size_combo.findChild(QComboBox).currentTextChanged.connect(
            lambda _t: self.profile_changed.emit()
        )
        self.style_combo.findChild(QComboBox).currentTextChanged.connect(
            lambda _t: self.profile_changed.emit()
        )
        self.batt_combo.findChild(QComboBox).currentTextChanged.connect(
            lambda _t: self.profile_changed.emit()
        )
        self.frame_combo.findChild(QComboBox).currentTextChanged.connect(
            lambda _t: self.profile_changed.emit()
        )

    def _make_combo(self, label_text: str, items: list[str], default: str,
                    tooltip: str) -> QWidget:
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(4)
        lbl = QLabel(label_text)
        lbl.setStyleSheet("color:#aaa; font-size:12px; font-weight:bold;")
        lay.addWidget(lbl)
        cb = QComboBox()
        cb.addItems(items); cb.setCurrentText(default)
        cb.setMinimumWidth(140)
        cb.setToolTip(tooltip)
        lay.addWidget(cb)
        return box

    def get_size(self) -> str:    return self.size_combo.findChild(QComboBox).currentText()
    def get_style(self) -> str:   return self.style_combo.findChild(QComboBox).currentText()
    def get_battery(self) -> str: return self.batt_combo.findChild(QComboBox).currentText()
    def get_frame_type(self) -> FrameType:
        label = self.frame_combo.findChild(QComboBox).currentText()
        return FRAME_TYPE_MAP.get(label, FrameType.STANDARD)


# --------------------------------------------------------------------------
# MainWindow
# --------------------------------------------------------------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.parser = BlackboxParser()
        self._last_cfg: FlightConfig | None = None
        self._worker:  DecodeWorker | None = None
        self._has_loaded = False

        # État courant après chargement
        self._sessions:  list[pd.DataFrame] = []
        self._analyses:  list[SessionAnalysis] = []
        self._reports:   list[DiagnosticReport] = []
        self._current_session_idx: int = 0
        self._current_path: str | None = None

        # Référence pour comparaison
        self._reference: dict | None = None
        self._score_history: list[int] = []

        self.setWindowTitle("BlackBox Analyzer")
        self.setMinimumSize(1024, 600)            # netbook OK
        self.setStyleSheet(DARK_STYLE)
        self.setAcceptDrops(True)                 # drop sur toute la fenêtre

        self._build_ui()

        # Plein écran maximisé au démarrage (pas fullscreen — laisse barre de titre)
        QTimer.singleShot(0, self.showMaximized)

        # Vérifie la dispo du décodeur
        if not self.parser.is_ready():
            import platform
            sys_name = platform.system()
            hint = {
                'Darwin': "blackbox_decode introuvable — installez via brew install blackbox-tools",
                'Linux':  "blackbox_decode introuvable — voir tools/README.md",
            }.get(sys_name, "blackbox_decode.exe introuvable — voir tools/README.md")
            self.status.showMessage(f"⚠️  {hint}", 0)
        else:
            self.status.showMessage("✅  Prêt — glissez un fichier blackbox n'importe où.")

    # ------------------------------------------------------------------
    # Construction de l'UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        # Layout horizontal : sidebar | (top bar + content stack)
        central = QWidget()
        self.setCentralWidget(central)
        outer = QHBoxLayout(central)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # ---- Sidebar gauche ----
        self.sidebar = RailSidebar()
        self.sidebar.view_requested.connect(self._on_view_requested)
        self.sidebar.open_file_clicked.connect(self._open_file_dialog)
        self.sidebar.apply_clicked.connect(self._on_apply)
        self.sidebar.set_reference_clicked.connect(self._set_as_reference)
        outer.addWidget(self.sidebar)

        # ---- Zone droite : top bar + stacked content ----
        right = QWidget()
        right_lay = QVBoxLayout(right)
        right_lay.setContentsMargins(0, 0, 0, 0)
        right_lay.setSpacing(0)

        # Bandeau température moteurs (PERSISTANT, non scrollé)
        self.temp_bar = MotorTempBar()
        self.temp_bar.temp_changed.connect(self._on_motor_temp_changed)
        self.temp_bar.session_changed.connect(self._on_session_changed)
        self.temp_bar.profile_clicked.connect(lambda: self._on_view_requested('profile'))
        right_lay.addWidget(self.temp_bar)

        # Stack des vues (plein espace restant)
        self.stack = QStackedWidget()
        self.stack.setStyleSheet("QStackedWidget { background:#1e1e1e; }")
        right_lay.addWidget(self.stack, stretch=1)

        outer.addWidget(right, stretch=1)

        # Construit les vues
        self._build_views()

        # Status bar
        self.status = QStatusBar()
        self.setStatusBar(self.status)

        # Drop overlay (par-dessus tout)
        self.overlay = DropOverlay(self)

        # État initial : welcome + boutons désactivés sauf "Ouvrir" et "Profil"
        # (le profil reste accessible avant le 1er chargement pour pré-config).
        self.sidebar.set_buttons_enabled(False)
        self.sidebar.set_view_visible('comparison', False)
        self.stack.setCurrentWidget(self.welcome_view)

    def _build_views(self):
        """Construit (ou re-construit) les vues du QStackedWidget."""
        # Welcome (toujours présente, même après chargement — utile si on charge un autre fichier)
        self.welcome_view = WelcomeView()
        self.welcome_view.open_file_clicked.connect(self._open_file_dialog)
        self.stack.addWidget(self.welcome_view)

        # Diagnostic / Gyro / PID R/P/Y / FFT / Moteurs / Comparaison / Profil
        # Les vues "données" sont des placeholders au démarrage (remplacés au chargement BBL).
        self._view_placeholders: dict[str, QWidget] = {}
        for view_id, label in [
            ('diagnostic', "Aucun diagnostic — chargez un fichier blackbox."),
            ('gyroscope',  "Glissez un .bbl pour voir les courbes gyro."),
            ('pid_roll',   "Glissez un .bbl pour voir la réponse PID Roll."),
            ('pid_pitch',  "Glissez un .bbl pour voir la réponse PID Pitch."),
            ('pid_yaw',    "Glissez un .bbl pour voir la réponse PID Yaw."),
            ('fft',        "Glissez un .bbl pour voir le spectre FFT."),
            ('motors',     "Glissez un .bbl pour voir les courbes moteurs."),
            ('comparison', "Définissez une référence puis chargez un nouveau vol."),
        ]:
            ph = self._make_placeholder(label)
            self._view_placeholders[view_id] = ph
            self.stack.addWidget(ph)

        # Profil & ressenti — vue à part, pas un placeholder
        self.profile_view = ProfileView()
        self.profile_view.profile_changed.connect(self._on_apply)   # tout changement re-applique
        self.profile_view.pilot_fb.feedback_changed.connect(self._on_apply)
        self.stack.addWidget(self.profile_view)

    @staticmethod
    def _make_placeholder(text: str) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl = QLabel(text)
        lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl.setStyleSheet("color:#666; font-size:14px; font-style:italic;")
        lay.addWidget(lbl)
        return w

    # ------------------------------------------------------------------
    # Drag & drop sur la fenêtre entière
    # ------------------------------------------------------------------

    def dragEnterEvent(self, event: QDragEnterEvent):
        urls = event.mimeData().urls() if event.mimeData().hasUrls() else []
        if any(Path(u.toLocalFile()).suffix.lower() in SUPPORTED_EXTS for u in urls):
            event.acceptProposedAction()
            self.overlay.show_overlay()
        else:
            event.ignore()

    def dragLeaveEvent(self, event: QDragLeaveEvent):
        self.overlay.hide_overlay()
        event.accept()

    def dropEvent(self, event: QDropEvent):
        self.overlay.hide_overlay()
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if Path(path).suffix.lower() in SUPPORTED_EXTS:
                self._on_file_dropped(path)
                event.acceptProposedAction()
                return
        event.ignore()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'overlay'):
            self.overlay.update_geometry()

    # ------------------------------------------------------------------
    # Sidebar : navigation & actions
    # ------------------------------------------------------------------

    def _on_view_requested(self, view_id: str):
        """Switch dans le QStackedWidget."""
        if view_id == 'profile':
            self.stack.setCurrentWidget(self.profile_view)
        else:
            target = self._view_placeholders.get(view_id)
            if target is not None:
                self.stack.setCurrentWidget(target)
        self.sidebar.set_active(view_id)

    def _open_file_dialog(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Ouvrir un fichier blackbox", "",
            "Blackbox files (*.bbl *.bfl);;All files (*)"
        )
        if path:
            self._on_file_dropped(path)

    # ------------------------------------------------------------------
    # Chargement fichier
    # ------------------------------------------------------------------

    def _on_file_dropped(self, path: str):
        if self._worker is not None and self._worker.isRunning():
            self.status.showMessage("⏳  Décodage déjà en cours — attendez la fin.", 3000)
            return

        name = Path(path).name
        self._current_path = path
        self.status.showMessage(f"⏳  Décodage en cours : {name} …")
        self.temp_bar.set_file_label(f"⏳  {name}", 0)

        # Affiche un placeholder "chargement" pendant le décodage
        for ph in self._view_placeholders.values():
            ph_lbl = ph.findChild(QLabel)
            if ph_lbl is not None:
                ph_lbl.setText(f"⏳  Décodage de {name}…")

        # Parse l'en-tête (rapide)
        try:
            self._last_cfg = parse_header(path)
        except Exception:
            self._last_cfg = FlightConfig()

        # Auto-suggestion taille
        hint = self._last_cfg.size_hint() if self._last_cfg else None
        if hint and hint in DRONE_SIZES:
            cb = self.profile_view.size_combo.findChild(QComboBox)
            cb.blockSignals(True); cb.setCurrentText(hint); cb.blockSignals(False)

        # Lance le décodage dans un thread
        self._worker = DecodeWorker(self.parser, path)
        self._worker.done.connect(lambda sessions: self._on_decode_done(sessions, path))
        self._worker.error.connect(self._on_decode_error)
        self._worker.start()

    def _on_decode_error(self, msg: str):
        name = Path(self._current_path or "").name
        self.status.showMessage(f"❌  Erreur : {msg}")
        self.temp_bar.set_file_label(f"❌  {name}", 0)
        for ph in self._view_placeholders.values():
            ph_lbl = ph.findChild(QLabel)
            if ph_lbl is not None:
                ph_lbl.setText(f"❌  Échec du chargement\n{msg}")

    def _on_decode_done(self, sessions: list, path: str):
        try:
            self._sessions = sessions
            name = Path(path).name

            size    = self.profile_view.get_size()
            style   = self.profile_view.get_style()
            battery = self.profile_view.get_battery()
            bat_cells = int(battery[:-1]) if battery != 'Auto' else 0
            feel    = self.profile_view.feel_box.current_feel()
            mtemp   = self.temp_bar.current()
            fb      = self.profile_view.pilot_fb.current()
            frame   = self.profile_view.get_frame_type()

            self._analyses = []
            self._reports  = []
            for df in sessions:
                sa = analyze(df, self._last_cfg)
                rp = generate_report(sa, self._last_cfg, size, style, bat_cells,
                                     feel, mtemp, fb, frame)
                self._analyses.append(sa)
                self._reports.append(rp)

            # Met à jour la barre top (file + sessions)
            self.temp_bar.set_file_label(name, len(sessions))
            session_labels = [
                f"Session {i+1}  ({self._duration(df)})" for i, df in enumerate(sessions)
            ]
            self.temp_bar.set_sessions(session_labels)
            self._current_session_idx = 0

            # Si référence : injecte la vue de comparaison
            if self._reference is not None:
                self.sidebar.set_view_visible('comparison', True)

            # Construit toutes les vues à partir de la session courante
            self._rebuild_session_views()

            # Première fois : active toute la nav
            if not self._has_loaded:
                self._has_loaded = True
                self.sidebar.set_buttons_enabled(True)
                self.sidebar.set_apply_enabled(True)
                self.sidebar.set_reference_enabled(True)
                # Switch direct vers le diagnostic
                self.sidebar.set_active('diagnostic')
                self._on_view_requested('diagnostic')

            total_rows = sum(len(s) for s in sessions)
            self.status.showMessage(
                f"✅  {name}  —  {len(sessions)} session(s), {total_rows:,} points"
            )
        except Exception as exc:
            self._on_decode_error(f"Construction de l'interface : {exc}")

    def _rebuild_session_views(self):
        """Reconstruit les vues à partir de la session courante."""
        if not self._sessions:
            return
        idx = self._current_session_idx
        df  = self._sessions[idx]
        sa  = self._analyses[idx]
        rp  = self._reports[idx]
        cfg = self._last_cfg
        size = self.profile_view.get_size()

        # Helper : remplace un placeholder dans le stack par un vrai widget
        def _replace(view_id: str, new_widget: QWidget):
            old = self._view_placeholders.get(view_id)
            if old is None:
                self.stack.addWidget(new_widget)
                self._view_placeholders[view_id] = new_widget
                return
            current = (self.stack.currentWidget() is old)
            self.stack.removeWidget(old)
            old.deleteLater()
            self.stack.addWidget(new_widget)
            self._view_placeholders[view_id] = new_widget
            if current:
                self.stack.setCurrentWidget(new_widget)

        _replace('diagnostic', DiagnosticWidget(
            cfg, rp, size, flight_type=getattr(sa, 'flight_type', None), sa=sa,
            analyses=self._analyses, current_session_idx=idx
        ))
        _replace('gyroscope',  GyroPlotWidget(df))
        for i, axis_name in enumerate(AXIS_NAMES):
            view_id = f'pid_{axis_name.lower()}'
            if f'axisP[{i}]' in df.columns:
                _replace(view_id, PidPlotWidget(df, i, axis_name))
        if 'motor[0]' in df.columns:
            _replace('motors', MotorPlotWidget(df))
        _replace('fft', FftWidget(df, cfg))

        # Comparaison
        if self._reference is not None:
            cmp_widget = self._build_comparison_widget(sa, rp, cfg, Path(self._current_path).name)
            _replace('comparison', cmp_widget)

    # ------------------------------------------------------------------
    # Application du profil & ressenti
    # ------------------------------------------------------------------

    def _on_apply(self, *_args):
        """Régénère le diagnostic avec le profil + ressenti courants."""
        if not self._sessions:
            return
        size    = self.profile_view.get_size()
        style   = self.profile_view.get_style()
        battery = self.profile_view.get_battery()
        bat_cells = int(battery[:-1]) if battery != 'Auto' else 0
        feel    = self.profile_view.feel_box.current_feel()
        mtemp   = self.temp_bar.current()
        fb      = self.profile_view.pilot_fb.current()
        frame   = self.profile_view.get_frame_type()

        # Régénère les rapports pour TOUTES les sessions
        self._reports = []
        for sa in self._analyses:
            rp = generate_report(sa, self._last_cfg, size, style, bat_cells,
                                 feel, mtemp, fb, frame)
            self._reports.append(rp)

        # Reconstruit les vues de la session courante
        self._rebuild_session_views()

        # Message contextuel
        bits = [size, style]
        if battery != 'Auto':
            bits.append(battery)
        if mtemp == MotorTemp.HOT:
            bits.append("🔥 moteurs chauds")
        elif mtemp == MotorTemp.COLD:
            bits.append("❄ moteurs froids")
        elif mtemp == MotorTemp.WARM:
            bits.append("🌡 moteurs tièdes")
        self.status.showMessage("Profil appliqué : " + " / ".join(bits))

    def _on_motor_temp_changed(self, _temp):
        """Le pilote vient de cliquer sur un état de température — ré-applique direct."""
        if self._has_loaded:
            self._on_apply()

    def _on_session_changed(self, idx: int):
        if 0 <= idx < len(self._sessions):
            self._current_session_idx = idx
            self._rebuild_session_views()

    # ------------------------------------------------------------------
    # Référence pour comparaison
    # ------------------------------------------------------------------

    def _set_as_reference(self):
        if not self._sessions:
            return
        idx = self._current_session_idx
        size  = self.profile_view.get_size()
        style = self.profile_view.get_style()
        self._reference = {
            'file':     Path(self._current_path).name if self._current_path else "?",
            'sessions': self._sessions,
            'analyses': self._analyses,
            'reports':  self._reports,
            'cfg':      self._last_cfg,
            'size':     size,
            'style':    style,
            'idx':      idx,
        }
        ref_score = self._reports[idx].health_score if self._reports else 0
        self._score_history = [ref_score]
        self.sidebar.set_view_visible('comparison', True)
        name = self._reference['file']
        self.status.showMessage(
            f"💾  Référence mémorisée : {name}. Chargez un autre vol pour comparer."
        )

    def _build_comparison_widget(
        self, new_sa: SessionAnalysis, new_rp: DiagnosticReport,
        new_cfg: FlightConfig, new_name: str,
    ) -> QWidget:
        ref = self._reference
        if ref is None:
            return self._make_placeholder("Pas de référence définie.")
        ref_idx = ref['idx']
        ref_sa = ref['analyses'][ref_idx] if ref_idx < len(ref['analyses']) else None
        ref_rp = ref['reports'][ref_idx]  if ref_idx < len(ref['reports'])  else None
        if ref_sa is None or ref_rp is None:
            return self._make_placeholder("Données de référence incomplètes.")

        self._score_history.append(new_rp.health_score)
        is_oscillating = self._detect_oscillation()

        return ComparisonWidget(
            ref_sa, ref_rp, ref['cfg'], ref['file'],
            new_sa, new_rp, new_cfg, new_name,
            self.profile_view.get_size(), self.profile_view.get_style(),
            is_oscillating=is_oscillating,
        )

    def _detect_oscillation(self) -> bool:
        h = self._score_history
        if len(h) < 3:
            return False
        a, b, c = h[-3], h[-2], h[-1]
        return (b - a >= 3 and b - c >= 3) or (a - b >= 3 and c - b >= 3)

    # ------------------------------------------------------------------
    # Utils
    # ------------------------------------------------------------------

    @staticmethod
    def _duration(df: pd.DataFrame) -> str:
        if 'time_s' not in df.columns or df.empty:
            return "?"
        secs = float(df['time_s'].iloc[-1] - df['time_s'].iloc[0])
        return f"{int(secs//60)}m{int(secs%60):02d}s" if secs >= 60 else f"{secs:.1f}s"
