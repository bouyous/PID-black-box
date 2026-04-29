"""
MotorTempBar — bandeau persistant en haut de la zone principale.

Élément CRITIQUE pour le pilote terrain : reste TOUJOURS visible quel que soit
l'onglet sélectionné. Le pilote peut toucher les cloches moteur juste après
l'atterrissage et cliquer sur le bon état sans devoir naviguer.

Affiche :
  - Nom du fichier chargé (ou message d'accueil)
  - Combo de sélection de session (caché s'il n'y en a qu'une)
  - 3 boutons "❄ Froids / 🌡 Tièdes / 🔥 Chauds"

Émet :
  - temp_changed(MotorTemp) chaque fois que l'utilisateur clique sur un état.
  - session_changed(int) quand le combo de session change.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
)

from analysis.recommender import MotorTemp


# Palette
BAR_BG_NEUTRAL = "#1f1f1f"
BAR_BG_COLD    = "#1a3550"      # bleu foncé — marge thermique
BAR_BG_WARM    = "#1f3d1f"      # vert sombre — état nominal
BAR_BG_HOT     = "#5a1f15"      # rouge foncé — danger thermique
BORDER_DIM     = "#333"
TEXT_BRIGHT    = "#e0e0e0"
TEXT_DIM       = "#888"


class MotorTempBar(QFrame):
    """Bandeau horizontal persistant.

    NE DOIT PAS être placé dans un QScrollArea — la température doit toujours
    être accessible au pilote, même quand il scroll dans une vue.
    """

    temp_changed     = pyqtSignal(object)   # MotorTemp
    session_changed  = pyqtSignal(int)
    profile_clicked  = pyqtSignal()         # bouton "🎯 Profil & Ressenti"

    OPTIONS = [
        (MotorTemp.COLD, "❄  Froids", "Ambiant + 0–5 °C — marge thermique disponible",  "#3a6ea5"),
        (MotorTemp.WARM, "🌡  Tièdes", "Ambiant + 5–10 °C — état nominal",               "#3d6e3d"),
        (MotorTemp.HOT,  "🔥  Chauds", "Limite avant destruction — bloque toute reco "
                                        "qui aggraverait la chauffe",                    "#a04030"),
    ]

    def __init__(self):
        super().__init__()
        self._selected: MotorTemp = MotorTemp.UNKNOWN
        self.setFixedHeight(64)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._refresh_bg()

        outer = QHBoxLayout(self)
        outer.setContentsMargins(16, 6, 16, 6)
        outer.setSpacing(20)

        # ---- Bloc gauche : nom du fichier + session ----
        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        left.setSpacing(2)

        self._file_label = QLabel("Aucun fichier chargé")
        self._file_label.setStyleSheet(
            f"color:{TEXT_BRIGHT}; font-size:14px; font-weight:bold;"
        )
        left.addWidget(self._file_label)

        self._session_combo = QComboBox()
        self._session_combo.setMinimumWidth(180)
        self._session_combo.setStyleSheet("""
            QComboBox {
                background:#2a2a2a; color:#ddd;
                border:1px solid #444; border-radius:3px;
                padding:2px 8px; font-size:12px;
            }
            QComboBox:disabled { color:#555; }
            QComboBox::drop-down { border:none; }
            QComboBox QAbstractItemView { background:#2a2a2a; color:#ddd; }
        """)
        self._session_combo.setVisible(False)
        self._session_combo.currentIndexChanged.connect(
            lambda i: self.session_changed.emit(i) if i >= 0 else None
        )
        left.addWidget(self._session_combo)

        outer.addLayout(left)
        outer.addStretch()

        # ---- Bouton "Profil & Ressenti" (mis en évidence) ----
        # À gauche de la température moteurs : c'est l'autre bouton critique.
        self.btn_profile = QPushButton("🎯  Profil & Ressenti")
        self.btn_profile.setMinimumHeight(40)
        self.btn_profile.setMinimumWidth(180)
        self.btn_profile.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_profile.setToolTip(
            "Configurer la taille du drone, le style de vol, et le ressenti pilote.\n"
            "Un clic ouvre la vue Profil ; les changements régénèrent le diagnostic."
        )
        self.btn_profile.setStyleSheet("""
            QPushButton {
                background: rgba(74, 158, 255, 0.15);
                color: #ddd;
                border: 1px solid #4a9eff;
                border-radius: 4px;
                padding: 4px 14px;
                font-size: 14px;
                font-weight: bold;
                letter-spacing: 1px;
            }
            QPushButton:hover {
                background: rgba(74, 158, 255, 0.30);
                color: #fff;
            }
            QPushButton:pressed {
                background: rgba(74, 158, 255, 0.45);
            }
            QPushButton:disabled {
                color: #555;
                border-color: #2d2d2d;
            }
        """)
        self.btn_profile.clicked.connect(self.profile_clicked.emit)
        outer.addWidget(self.btn_profile)

        # Petit séparateur visuel
        sep = QLabel(" │ ")
        sep.setStyleSheet(f"color:{BORDER_DIM}; font-size:18px;")
        outer.addWidget(sep)

        # ---- Bloc droit : titre + 3 boutons temp ----
        title = QLabel("🔧  TEMPÉRATURE  MOTEURS")
        title.setStyleSheet(
            f"color:{TEXT_DIM}; font-size:11px; font-weight:bold; letter-spacing:2px;"
        )
        outer.addWidget(title)

        self._buttons: dict[MotorTemp, QPushButton] = {}
        for state, label, tip, color in self.OPTIONS:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setToolTip(tip)
            btn.setMinimumHeight(40)
            btn.setMinimumWidth(120)
            btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setStyleSheet(self._style_for(color, checked=False))
            btn.clicked.connect(lambda _checked, s=state: self._select(s))
            self._buttons[state] = btn
            outer.addWidget(btn)

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def set_file_label(self, name: str | None, session_count: int = 0):
        if not name:
            self._file_label.setText("Aucun fichier chargé — glissez un .bbl/.bfl")
        elif session_count <= 0:
            self._file_label.setText(name)
        else:
            self._file_label.setText(f"{name}  ·  {session_count} session(s)")

    def set_sessions(self, labels: list[str]):
        """Peuple le combo de session. Si <=1, le combo reste caché."""
        self._session_combo.blockSignals(True)
        self._session_combo.clear()
        if len(labels) > 1:
            self._session_combo.addItems(labels)
            self._session_combo.setCurrentIndex(0)
            self._session_combo.setVisible(True)
            self._session_combo.setEnabled(True)
        else:
            self._session_combo.setVisible(False)
        self._session_combo.blockSignals(False)

    def current_session_index(self) -> int:
        return max(0, self._session_combo.currentIndex())

    def current(self) -> MotorTemp:
        return self._selected

    def reset(self):
        self._selected = MotorTemp.UNKNOWN
        self._refresh_bg()
        for s, btn in self._buttons.items():
            color = next(c for st, _, _, c in self.OPTIONS if st == s)
            btn.setChecked(False)
            btn.setStyleSheet(self._style_for(color, checked=False))

    # ------------------------------------------------------------------
    # Internes
    # ------------------------------------------------------------------

    def _select(self, state: MotorTemp):
        # Toggle off si on reclique sur l'état déjà actif
        if self._selected == state:
            self._selected = MotorTemp.UNKNOWN
        else:
            self._selected = state

        for s, btn in self._buttons.items():
            color = next(c for st, _, _, c in self.OPTIONS if st == s)
            is_checked = (s == self._selected)
            btn.setChecked(is_checked)
            btn.setStyleSheet(self._style_for(color, checked=is_checked))

        self._refresh_bg()
        self.temp_changed.emit(self._selected)

    def _refresh_bg(self):
        bg = BAR_BG_NEUTRAL
        border = BORDER_DIM
        if self._selected == MotorTemp.COLD:
            bg = BAR_BG_COLD;  border = "#3a6ea5"
        elif self._selected == MotorTemp.WARM:
            bg = BAR_BG_WARM;  border = "#3d6e3d"
        elif self._selected == MotorTemp.HOT:
            bg = BAR_BG_HOT;   border = "#a04030"
        self.setStyleSheet(
            f"MotorTempBar {{ background:{bg}; border-bottom:2px solid {border}; }}"
        )

    @staticmethod
    def _style_for(color: str, checked: bool) -> str:
        if checked:
            return (f"QPushButton {{ background:{color}; color:#fff;"
                    f" border:2px solid #fff; border-radius:4px;"
                    f" padding:4px 14px; font-weight:bold; font-size:14px; }}")
        return (f"QPushButton {{ background:rgba(0,0,0,0.35); color:#ddd;"
                f" border:1px solid {color}; border-radius:4px;"
                f" padding:4px 14px; font-size:14px; }}"
                f" QPushButton:hover {{ background:rgba(255,255,255,0.08); color:#fff; }}")
