from pathlib import Path

import pandas as pd
from PyQt6.QtCore import Qt, QThread, pyqtSignal
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
    QSplitter,
    QStatusBar,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from analysis.analyzer import SessionAnalysis, analyze
from analysis.header_parser import FlightConfig, parse_header
from analysis.recommender import (
    DiagnosticReport, FlightFeel, MotorTemp, PilotFeedback, generate_report,
)
from parser.blackbox_parser import BlackboxParser
from ui.comparison_widget import ComparisonWidget
from ui.fft_widget import FftWidget
from ui.plot_widget import GyroPlotWidget, MotorPlotWidget, PidPlotWidget
from ui.recommendation_panel import DiagnosticWidget

SUPPORTED_EXTS = {'.bbl', '.bfl'}
AXIS_NAMES = ['Roll', 'Pitch', 'Yaw']
DRONE_SIZES = ['2.5"', '3"', '5"', '6"', '7"', '10"']
FLYING_STYLES = ['Freestyle', 'Racing', 'Long Range', 'Bangers', 'Ciné Whoop']
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
    """4 sliders 1..5 pour capter le ressenti du pilote. 3 = neutre."""

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
        title.setStyleSheet(
            "color:#bbb; font-size:14px; font-weight:bold; letter-spacing:1px;"
        )
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
            s.setMinimum(1)
            s.setMaximum(5)
            s.setValue(3)
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
    """5 questions oui/non posées au pilote après le vol de test.
    Le bloc CLI final n'est généré qu'une fois les 5 réponses fournies."""

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
        title.setStyleSheet(
            "color:#bbb; font-size:13px; font-weight:bold; letter-spacing:1px;"
        )
        grid.addWidget(title, 0, 0, 1, 4)

        for row, (key, label_text) in enumerate(self.QUESTIONS, start=1):
            lbl = QLabel(label_text)
            lbl.setStyleSheet("color:#e0e0e0; font-size:13px;")
            lbl.setMinimumWidth(330)
            grid.addWidget(lbl, row, 0)

            btn_yes = QPushButton("Oui")
            btn_no  = QPushButton("Non")
            btn_yes.setCheckable(True)
            btn_no.setCheckable(True)
            btn_yes.setMinimumWidth(60)
            btn_no.setMinimumWidth(60)
            self._restyle(btn_yes, None, True)
            self._restyle(btn_no,  None, False)
            btn_yes.clicked.connect(lambda _c, k=key: self._set(k, True))
            btn_no.clicked.connect(lambda _c, k=key: self._set(k, False))
            grid.addWidget(btn_yes, row, 1)
            grid.addWidget(btn_no,  row, 2)
            self._buttons[key] = (btn_yes, btn_no)

        # Statut + bouton "Réinitialiser"
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
        """Style un bouton selon l'état de la question."""
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
        # Toggle off si on reclique sur la même réponse
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


class MotorTempBox(QFrame):
    """3 boutons : froids / tièdes / chauds. Saisi par le pilote après le vol,
    en touchant les cloches moteur. État HOT bloque toute reco qui aggraverait
    la chauffe (sécurité)."""

    OPTIONS = [
        (MotorTemp.COLD, "❄  Froids",
         "Ambiant + 0-5 °C — à peine tièdes",
         "#3a6ea5"),
        (MotorTemp.WARM, "🌡  Tièdes",
         "Ambiant + 5-10 °C — niveau normal",
         "#3d6e3d"),
        (MotorTemp.HOT,  "🔥  Chauds",
         "On a du mal à tenir les doigts dessus — limite avant destruction",
         "#a04030"),
    ]

    def __init__(self):
        super().__init__()
        self._selected: MotorTemp = MotorTemp.UNKNOWN
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setStyleSheet(
            "MotorTempBox { background:#1f1f1f; border:1px solid #333; border-radius:4px; }"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(10)

        title = QLabel("🔧  Température moteurs (touche après le vol)")
        title.setStyleSheet(
            "color:#bbb; font-size:13px; font-weight:bold; letter-spacing:1px;"
        )
        title.setMinimumWidth(280)
        layout.addWidget(title)

        self._buttons: dict[MotorTemp, QPushButton] = {}
        for state, label, tip, color in self.OPTIONS:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setToolTip(tip)
            btn.setMinimumHeight(34)
            btn.setMinimumWidth(110)
            btn.setStyleSheet(self._style_for(color, checked=False))
            btn.clicked.connect(lambda _checked, s=state: self._select(s))
            self._buttons[state] = btn
            layout.addWidget(btn)
        layout.addStretch()

    @staticmethod
    def _style_for(color: str, checked: bool) -> str:
        if checked:
            return (f"QPushButton {{ background:{color}; color:#fff;"
                    f" border:2px solid #fff; border-radius:4px;"
                    f" padding:4px 12px; font-weight:bold; font-size:13px; }}")
        return (f"QPushButton {{ background:#252525; color:#ccc;"
                f" border:1px solid {color}; border-radius:4px;"
                f" padding:4px 12px; font-size:13px; }}"
                f" QPushButton:hover {{ background:#333; color:#fff; }}")

    def _select(self, state: MotorTemp):
        self._selected = state
        for s, btn in self._buttons.items():
            color = next(c for st, _, _, c in self.OPTIONS if st == s)
            btn.setChecked(s == state)
            btn.setStyleSheet(self._style_for(color, checked=(s == state)))

    def current(self) -> MotorTemp:
        return self._selected

    def reset(self):
        self._selected = MotorTemp.UNKNOWN
        for s, btn in self._buttons.items():
            color = next(c for st, _, _, c in self.OPTIONS if st == s)
            btn.setChecked(False)
            btn.setStyleSheet(self._style_for(color, checked=False))


class DecodeWorker(QThread):
    """Décode un fichier BBL dans un thread séparé — évite de bloquer l'UI."""
    done  = pyqtSignal(list)   # list[pd.DataFrame]
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
        self._worker:  DecodeWorker | None = None   # thread en cours
        self._has_loaded = False  # premier chargement réussi → affiche les contrôles

        # Référence pour comparaison avant/après
        self._reference: dict | None = None   # {file, sessions, analyses, reports, cfg, size, style}
        self._score_history: list[int] = []   # scores dans l'ordre : ref puis sessions comparées

        self.setWindowTitle("BlackBox Analyzer")
        self.resize(1280, 800)
        self.setStyleSheet(DARK_STYLE)
        self._build_ui()

        if not self.parser.is_ready():
            import platform
            sys_name = platform.system()
            hint = {
                'Darwin': "blackbox_decode_mac introuvable — voir tools/README.md (section Mac)",
                'Linux':  "blackbox_decode introuvable — voir tools/README.md",
            }.get(sys_name, "blackbox_decode.exe introuvable — voir tools/README.md")
            self.status.showMessage(f"  ⚠️  {hint}", 0)
        else:
            self.status.showMessage("✅  Prêt — glissez un fichier blackbox pour commencer.")

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 6)
        root.setSpacing(0)

        # --- Splitter vertical : zone contrôles | onglets sessions ---
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setHandleWidth(5)
        splitter.setStyleSheet("QSplitter::handle { background:#2a2a2a; }")

        # ---- Zone contrôles (panneau haut) ----
        ctrl_widget = QWidget()
        ctrl_layout = QVBoxLayout(ctrl_widget)
        ctrl_layout.setContentsMargins(0, 0, 0, 6)
        ctrl_layout.setSpacing(5)

        # Ligne 1 : drop area + sélecteurs (sélecteurs cachés avant load)
        top_bar = QHBoxLayout()
        self.drop_area = DropArea()
        self.drop_area.file_dropped.connect(self._on_file_dropped)
        top_bar.addWidget(self.drop_area, stretch=1)

        self._selectors_widget = QWidget()
        sel_layout = QHBoxLayout(self._selectors_widget)
        sel_layout.setContentsMargins(0, 0, 0, 0)
        sel_layout.setSpacing(0)
        sel_layout.addWidget(self._make_selector_box(
            "Taille drone", DRONE_SIZES, '5"',
            "3\" : ±45%\n5\" : ±25%\n6\" : ±35%\n7\" : ±45%\n10\" : ±55%",
            '_size_combo'
        ))
        sel_layout.addWidget(self._make_selector_box(
            "Style de vol", FLYING_STYLES, 'Freestyle',
            "Freestyle : drone hyper loqué, FF agressif\n"
            "Racing : réactivité max, tracking serré\n"
            "Long Range : souple, FF bas, insensible au vent\n"
            "Bangers : tolérant (indoor, crash probable)",
            '_style_combo'
        ))
        sel_layout.addWidget(self._make_selector_box(
            "Batterie", BATTERY_OPTIONS, 'Auto',
            "Auto = détecté depuis la tension BBL\n"
            "Forcer si le vol de test n'était pas sur la batterie habituelle",
            '_battery_combo'
        ))
        self._selectors_widget.setVisible(False)
        top_bar.addWidget(self._selectors_widget)
        ctrl_layout.addLayout(top_bar)

        # Ressenti en vol (caché avant load + caché pour styles non concernés)
        self._feel_box = FeelSlidersBox()
        self._feel_box.setVisible(False)
        ctrl_layout.addWidget(self._feel_box)
        # Le ressenti pilote n'a un intérêt qu'en Ciné Whoop et Long Range
        # (vol cinématique / endurance — fluidité et stabilité fines).
        # Pour Freestyle/Racing/Bangers les sliders prennent de la place
        # visuelle pour rien : on les masque dynamiquement.
        self._style_combo.currentTextChanged.connect(
            lambda _: self._update_feel_visibility()
        )

        # Température moteurs (caché avant load)
        self._motor_temp_box = MotorTempBox()
        self._motor_temp_box.setVisible(False)
        ctrl_layout.addWidget(self._motor_temp_box)

        # Ressenti pilote 5 Y/N (caché avant load)
        self._pilot_fb_box = PilotFeedbackBox()
        self._pilot_fb_box.setVisible(False)
        ctrl_layout.addWidget(self._pilot_fb_box)

        # Bouton Appliquer (caché avant load)
        self._btn_apply = QPushButton("✓  Appliquer le profil et le ressenti")
        self._btn_apply.setToolTip(
            "Recalcule le diagnostic en combinant :\n"
            "  • Taille / Style / Batterie ci-dessus\n"
            "  • Les 4 boutons de ressenti en vol\n"
            "Chaque changement produit au moins un ajustement."
        )
        self._btn_apply.setMinimumHeight(38)
        self._btn_apply.setStyleSheet(
            "QPushButton { background:#2d5a3d; color:#fff;"
            " border:1px solid #3e7a55; border-radius:4px;"
            " padding:6px 18px; font-weight:bold; font-size:13px; }"
            "QPushButton:hover { background:#3a7050; border-color:#5aa078; }"
            "QPushButton:pressed { background:#245033; }"
            "QPushButton:disabled { background:#252525; color:#555; border-color:#333; }"
        )
        self._btn_apply.setEnabled(False)
        self._btn_apply.clicked.connect(self._on_profile_changed)
        self._btn_apply.setVisible(False)
        ctrl_layout.addWidget(self._btn_apply)

        # Barre inférieure : référence + ouvrir
        cmp_bar = QHBoxLayout()
        self._btn_set_ref = QPushButton("💾  Définir comme référence")
        self._btn_set_ref.setToolTip(
            "Mémorise ce vol comme référence.\n"
            "Chargez ensuite un nouveau vol pour comparer avant/après."
        )
        self._btn_set_ref.setEnabled(False)
        self._btn_set_ref.setVisible(False)
        self._btn_set_ref.clicked.connect(self._set_as_reference)
        cmp_bar.addWidget(self._btn_set_ref)

        self._ref_label = QLabel("")
        self._ref_label.setStyleSheet("color:#4a9eff; font-size:11px;")
        self._ref_label.setVisible(False)
        cmp_bar.addWidget(self._ref_label)
        cmp_bar.addStretch()

        self._btn_load_compare = QPushButton("📂  Ouvrir un fichier…")
        self._btn_load_compare.setToolTip("Ouvrir un fichier BBL via l'explorateur")
        self._btn_load_compare.clicked.connect(self._open_file_dialog)
        cmp_bar.addWidget(self._btn_load_compare)
        ctrl_layout.addLayout(cmp_bar)

        splitter.addWidget(ctrl_widget)

        # ---- Onglets sessions (panneau bas) ----
        self.session_tabs = QTabWidget()
        self.session_tabs.setVisible(False)
        splitter.addWidget(self.session_tabs)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        root.addWidget(splitter)

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
        # Si un décodage est déjà en cours, on l'ignore
        if self._worker is not None and self._worker.isRunning():
            self.status.showMessage("⏳  Décodage déjà en cours — attendez la fin.", 3000)
            return

        name = Path(path).name
        self.status.showMessage(f"⏳  Décodage en cours : {name} …")
        self.drop_area.setText(f"⏳  Décodage de {name}…")
        self.session_tabs.clear()
        self.session_tabs.setVisible(False)
        self._btn_set_ref.setEnabled(False)

        # Parse l'en-tête (rapide, pas besoin de thread)
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

        # Lance le décodage dans un thread séparé (évite le freeze UI)
        self._pending_path = path
        self._worker = DecodeWorker(self.parser, path)
        self._worker.done.connect(lambda sessions: self._on_decode_done(sessions, path))
        self._worker.error.connect(self._on_decode_error)
        self._worker.start()

    def _on_decode_error(self, msg: str):
        name = Path(getattr(self, '_pending_path', '')).name
        self.status.showMessage(f"❌  Erreur : {msg}")
        self.drop_area.setText(
            f"❌  Échec du chargement de {name}\n"
            "Glissez un fichier .bbl / .bfl ici"
        )

    def _on_decode_done(self, sessions: list, path: str):
        name = Path(path).name

        # Calcule analyses + rapports
        size    = self._size_combo.currentText()
        style   = self._style_combo.currentText()
        battery = self._battery_combo.currentText()
        bat_cells = int(battery[:-1]) if battery != 'Auto' else 0

        feel = self._feel_box.current_feel()
        motor_temp = self._motor_temp_box.current()
        feedback = self._pilot_fb_box.current()
        session_analyses = []
        session_reports  = []
        try:
            for i, df in enumerate(sessions):
                sa = analyze(df, self._last_cfg)
                rp = generate_report(sa, self._last_cfg, size, style, bat_cells,
                                     feel, motor_temp, feedback)
                session_analyses.append(sa)
                session_reports.append(rp)
                tab = self._build_session_tab(df, self._last_cfg, sa, rp)
                dur = self._duration(df)
                self.session_tabs.addTab(tab, f"Session {i + 1}  ({dur})")
        except Exception as exc:
            self._on_decode_error(f"Erreur lors de la construction de l'interface : {exc}")
            return

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
            f"✅  {name}  —  {len(sessions)} session(s), {total_rows:,} points"
        )
        self.drop_area.setText(
            f"✅  {name}  —  {len(sessions)} session(s)   "
            "(glissez un autre fichier pour remplacer)"
        )
        self._btn_set_ref.setEnabled(True)
        self._btn_apply.setEnabled(True)

        # Premier chargement réussi → révèle les contrôles masqués
        if not self._has_loaded:
            self._has_loaded = True
            self._selectors_widget.setVisible(True)
            self._feel_box.setVisible(True)
            self._motor_temp_box.setVisible(True)
            self._pilot_fb_box.setVisible(True)
            self._btn_apply.setVisible(True)
            self._btn_set_ref.setVisible(True)
            self._ref_label.setVisible(True)

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
            motor_temp = self._motor_temp_box.current()
            feedback = self._pilot_fb_box.current()
            rp = generate_report(sa, self._last_cfg, size, style, bat_cells,
                                 feel, motor_temp, feedback)
            new_diag = DiagnosticWidget(self._last_cfg, rp, size,
                                        flight_type=getattr(sa, 'flight_type', None),
                                        sa=sa)
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
        ref_score = ctx['reports'][0].health_score if ctx['reports'] else 0
        self._score_history = [ref_score]   # réinitialise l'historique à chaque nouvelle référence
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

        # Mise à jour de l'historique des scores et détection d'oscillation
        self._score_history.append(new_rp.health_score)
        is_oscillating = self._detect_oscillation()

        return ComparisonWidget(
            ref_sa, ref_rp, ref['cfg'], ref['file'],
            new_sa, new_rp, new_cfg, new_name,
            size, style,
            is_oscillating=is_oscillating
        )

    def _detect_oscillation(self) -> bool:
        h = self._score_history
        if len(h) < 3:
            return False
        a, b, c = h[-3], h[-2], h[-1]
        # Monte puis descend, ou descend puis monte (rebond de ≥3 pts)
        return (b - a >= 3 and b - c >= 3) or (a - b >= 3 and c - b >= 3)

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
        inner.addTab(DiagnosticWidget(cfg, rp, self._size_combo.currentText(),
                                      flight_type=sa.flight_type, sa=sa), "Diagnostic")

        layout.addWidget(inner)
        return widget

    @staticmethod
    def _duration(df: pd.DataFrame) -> str:
        if 'time_s' not in df.columns or df.empty:
            return "?"
        secs = float(df['time_s'].iloc[-1] - df['time_s'].iloc[0])
        return f"{int(secs//60)}m{int(secs%60):02d}s" if secs >= 60 else f"{secs:.1f}s"
