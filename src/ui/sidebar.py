"""
RailSidebar — barre de navigation latérale style Task Manager Windows / VS Code.

Deux états :
  - "rail"     : ~64 px de large, icônes seules empilées verticalement.
  - "expanded" : ~280 px, icône + label.

Le bouton burger en haut bascule entre les deux. Chaque bouton de navigation
émet view_requested(view_id) lorsque cliqué — le MainWindow swap le QStackedWidget.

Conçue pour rester lisible de 720p à 4K : pas de hauteurs fixes, les éléments
s'empilent dans un QScrollArea si l'écran est trop petit.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QVBoxLayout,
    QWidget,
)


# --------------------------------------------------------------------------
# Styles (palette inspirée Betaflight Configurator + VS Code)
# --------------------------------------------------------------------------

SIDEBAR_BG       = "#252525"
SIDEBAR_HOVER    = "#2f2f2f"
SIDEBAR_ACTIVE   = "#1e1e1e"
SIDEBAR_ACCENT   = "#4a9eff"
SIDEBAR_DIVIDER  = "#333"
SIDEBAR_TEXT     = "#e0e0e0"
SIDEBAR_TEXT_DIM = "#888"

RAIL_WIDTH      = 64
EXPANDED_WIDTH  = 260


# --------------------------------------------------------------------------
# Bouton de navigation (icône + label, fonctionne en rail et expanded)
# --------------------------------------------------------------------------

class NavButton(QPushButton):
    """Bouton de la sidebar. Affiche icône seule en mode rail, icône+label en expanded."""

    def __init__(self, icon_text: str, label: str, view_id: str, tooltip: str = ""):
        super().__init__()
        self._icon = icon_text
        self._label = label
        self.view_id = view_id
        self.setCheckable(True)
        self.setAutoExclusive(False)        # on gère l'exclusivité côté sidebar
        self.setToolTip(tooltip or label)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setMinimumHeight(44)
        self._expanded = False
        self._refresh_text()
        self._refresh_style()

    def set_expanded(self, expanded: bool):
        self._expanded = expanded
        self._refresh_text()
        self._refresh_style()

    def _refresh_text(self):
        if self._expanded:
            self.setText(f"  {self._icon}    {self._label}")
        else:
            self.setText(self._icon)

    def _refresh_style(self):
        align = "text-align:left" if self._expanded else "text-align:center"
        font_size = 14 if self._expanded else 20
        padding = "padding:6px 14px" if self._expanded else "padding:8px 0"
        # Indicateur gauche bleu sur l'élément actif
        self.setStyleSheet(f"""
            QPushButton {{
                background:{SIDEBAR_BG};
                color:{SIDEBAR_TEXT};
                border:none;
                border-left:3px solid transparent;
                {padding};
                font-size:{font_size}px;
                {align};
            }}
            QPushButton:hover {{
                background:{SIDEBAR_HOVER};
                border-left-color:{SIDEBAR_DIVIDER};
            }}
            QPushButton:checked {{
                background:{SIDEBAR_ACTIVE};
                color:#fff;
                border-left-color:{SIDEBAR_ACCENT};
                font-weight:bold;
            }}
            QPushButton:disabled {{
                color:#444;
            }}
        """)


# --------------------------------------------------------------------------
# Header (logo + bouton burger)
# --------------------------------------------------------------------------

class _SidebarHeader(QFrame):
    """Header contenant le logo de l'app + le bouton burger pour replier/déplier."""
    burger_clicked = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setFixedHeight(56)
        self.setStyleSheet(f"_SidebarHeader {{ background:{SIDEBAR_BG};"
                           f" border-bottom:1px solid {SIDEBAR_DIVIDER}; }}")
        self._lay = QHBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(0)

        self.btn_burger = QPushButton("☰")
        self.btn_burger.setFixedSize(QSize(RAIL_WIDTH, 56))
        self.btn_burger.setStyleSheet(f"""
            QPushButton {{
                background:transparent;
                color:{SIDEBAR_TEXT};
                border:none;
                font-size:22px;
            }}
            QPushButton:hover {{
                background:{SIDEBAR_HOVER};
                color:{SIDEBAR_ACCENT};
            }}
        """)
        self.btn_burger.setToolTip("Réduire / Élargir la barre latérale")
        self.btn_burger.clicked.connect(self.burger_clicked.emit)
        self._lay.addWidget(self.btn_burger)

        self.title = QLabel("BlackBox  Analyzer")
        self.title.setStyleSheet(f"color:{SIDEBAR_TEXT}; font-size:14px;"
                                 f" font-weight:bold; letter-spacing:1px; padding-left:4px;")
        self.title.setVisible(False)
        self._lay.addWidget(self.title)
        self._lay.addStretch()

    def set_expanded(self, expanded: bool):
        self.title.setVisible(expanded)


# --------------------------------------------------------------------------
# RailSidebar
# --------------------------------------------------------------------------

class RailSidebar(QFrame):
    """Sidebar verticale repliable. Émet view_requested(view_id) au clic."""

    view_requested = pyqtSignal(str)
    apply_clicked = pyqtSignal()
    set_reference_clicked = pyqtSignal()
    open_file_clicked = pyqtSignal()

    # Sections de navigation. Chaque entrée = (icone, label, view_id, tooltip).
    # Les view_id "_divider" insèrent un séparateur visuel.
    NAV_ITEMS = [
        ("📂", "Ouvrir un fichier",  "_open_action", "Ouvrir un .bbl ou .bfl depuis l'explorateur"),
        ("_divider", "", "", ""),
        ("🩺", "Diagnostic",         "diagnostic",   "Analyse + recommandations PID/filtres"),
        ("📈", "Gyroscope",          "gyroscope",    "Courbes brutes du gyro 3 axes"),
        ("🎚", "PID Roll",           "pid_roll",     "Réponse PID sur l'axe roll"),
        ("🎚", "PID Pitch",          "pid_pitch",    "Réponse PID sur l'axe pitch"),
        ("🎚", "PID Yaw",            "pid_yaw",      "Réponse PID sur l'axe yaw"),
        ("🌀", "FFT",                "fft",          "Spectre fréquentiel — détection vibrations"),
        ("⚙",  "Moteurs",            "motors",       "Commandes moteurs et eRPM"),
        ("📊", "Comparaison",        "comparison",   "Avant / après — visible quand une référence est définie"),
        ("_divider", "", "", ""),
        ("🎯", "Profil & Ressenti",  "profile",      "Taille, style, batterie + ressenti pilote"),
    ]

    def __init__(self):
        super().__init__()
        self._expanded = False
        self._buttons: dict[str, NavButton] = {}
        self.setStyleSheet(f"RailSidebar {{ background:{SIDEBAR_BG};"
                           f" border-right:1px solid {SIDEBAR_DIVIDER}; }}")
        self.setFixedWidth(RAIL_WIDTH)

        self._lay = QVBoxLayout(self)
        self._lay.setContentsMargins(0, 0, 0, 0)
        self._lay.setSpacing(0)

        # Header (burger)
        self.header = _SidebarHeader()
        self.header.burger_clicked.connect(self.toggle)
        self._lay.addWidget(self.header)

        # Zone scrollable au cas où l'écran est petit
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._scroll.setStyleSheet("QScrollArea { background:transparent; border:none; }")
        self._scroll_content = QWidget()
        self._scroll_content.setStyleSheet(f"background:{SIDEBAR_BG};")
        self._scroll.setWidget(self._scroll_content)
        nav_layout = QVBoxLayout(self._scroll_content)
        nav_layout.setContentsMargins(0, 8, 0, 0)
        nav_layout.setSpacing(0)
        self._nav_layout = nav_layout

        # Construit les boutons à partir de NAV_ITEMS
        for icon, label, view_id, tip in self.NAV_ITEMS:
            if view_id == "_divider":
                div = QFrame()
                div.setFrameShape(QFrame.Shape.HLine)
                div.setStyleSheet(f"background:{SIDEBAR_DIVIDER}; max-height:1px;"
                                  f" margin:8px 8px;")
                nav_layout.addWidget(div)
                continue
            btn = NavButton(icon, label, view_id, tip)
            btn.clicked.connect(lambda _checked, vid=view_id: self._on_button_clicked(vid))
            nav_layout.addWidget(btn)
            self._buttons[view_id] = btn

        nav_layout.addStretch()

        self._lay.addWidget(self._scroll, stretch=1)

        # Footer : bouton "Appliquer" + "Référence"
        footer = QFrame()
        footer.setStyleSheet(f"QFrame {{ background:{SIDEBAR_BG};"
                             f" border-top:1px solid {SIDEBAR_DIVIDER}; }}")
        f_lay = QVBoxLayout(footer)
        f_lay.setContentsMargins(8, 8, 8, 8)
        f_lay.setSpacing(6)

        self.btn_apply = QPushButton("✓")
        self.btn_apply.setToolTip("Appliquer le profil + ressenti et regénérer le diagnostic")
        self.btn_apply.setMinimumHeight(36)
        self.btn_apply.setEnabled(False)
        self.btn_apply.setStyleSheet(f"""
            QPushButton {{
                background:#2d5a3d;
                color:#fff;
                border:1px solid #3e7a55;
                border-radius:4px;
                font-weight:bold;
                font-size:14px;
            }}
            QPushButton:hover {{ background:#3a7050; }}
            QPushButton:disabled {{ background:#252525; color:#555; border-color:#333; }}
        """)
        self.btn_apply.clicked.connect(self.apply_clicked.emit)
        f_lay.addWidget(self.btn_apply)

        self.btn_set_ref = QPushButton("💾")
        self.btn_set_ref.setToolTip("Définir le vol courant comme référence pour comparaison")
        self.btn_set_ref.setMinimumHeight(32)
        self.btn_set_ref.setEnabled(False)
        self.btn_set_ref.setStyleSheet(f"""
            QPushButton {{
                background:#252525;
                color:{SIDEBAR_TEXT};
                border:1px solid {SIDEBAR_DIVIDER};
                border-radius:4px;
                font-size:13px;
            }}
            QPushButton:hover {{ background:{SIDEBAR_HOVER}; color:#fff; }}
            QPushButton:disabled {{ color:#555; border-color:#2a2a2a; }}
        """)
        self.btn_set_ref.clicked.connect(self.set_reference_clicked.emit)
        f_lay.addWidget(self.btn_set_ref)

        self._footer = footer
        self._btn_apply_full_label  = "✓  Appliquer"
        self._btn_setref_full_label = "💾  Référence"
        self._lay.addWidget(footer)

    # ------------------------------------------------------------------
    # API publique
    # ------------------------------------------------------------------

    def toggle(self):
        self.set_expanded(not self._expanded)

    def set_expanded(self, expanded: bool):
        self._expanded = expanded
        self.setFixedWidth(EXPANDED_WIDTH if expanded else RAIL_WIDTH)
        self.header.set_expanded(expanded)
        for btn in self._buttons.values():
            btn.set_expanded(expanded)
        # Met à jour le texte des boutons footer
        if expanded:
            self.btn_apply.setText(self._btn_apply_full_label)
            self.btn_set_ref.setText(self._btn_setref_full_label)
        else:
            self.btn_apply.setText("✓")
            self.btn_set_ref.setText("💾")

    def set_active(self, view_id: str):
        """Coche le bouton correspondant et décoche les autres."""
        for vid, btn in self._buttons.items():
            btn.setChecked(vid == view_id)

    def set_buttons_enabled(self, enabled: bool, *, except_open: bool = True):
        """Active/désactive tous les boutons sauf 'open' (utile avant 1er chargement)."""
        for vid, btn in self._buttons.items():
            if vid == "_open_action" and except_open:
                continue
            btn.setEnabled(enabled)

    def set_view_visible(self, view_id: str, visible: bool):
        """Cache un bouton de navigation (utilisé pour 'comparison' tant que pas de référence)."""
        btn = self._buttons.get(view_id)
        if btn is not None:
            btn.setVisible(visible)

    def set_apply_enabled(self, enabled: bool):
        self.btn_apply.setEnabled(enabled)

    def set_reference_enabled(self, enabled: bool):
        self.btn_set_ref.setEnabled(enabled)

    # ------------------------------------------------------------------
    # Slots internes
    # ------------------------------------------------------------------

    def _on_button_clicked(self, view_id: str):
        if view_id == "_open_action":
            # Restore l'état checked du bouton précédent (ce n'est pas une vue)
            self._buttons[view_id].setChecked(False)
            self.open_file_clicked.emit()
            return
        # Exclusivité manuelle
        for vid, btn in self._buttons.items():
            if vid != view_id:
                btn.setChecked(False)
        self._buttons[view_id].setChecked(True)
        self.view_requested.emit(view_id)
