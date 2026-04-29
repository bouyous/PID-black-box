"""
DropOverlay — overlay semi-transparent affiché lorsqu'un fichier est glissé sur
la fenêtre. Couvre toute la zone client de la MainWindow et indique à
l'utilisateur où relâcher.

Utilisation typique :
    self._overlay = DropOverlay(self)            # parent = QMainWindow
    # dans dragEnterEvent : self._overlay.show_overlay()
    # dans dropEvent / dragLeaveEvent : self._overlay.hide_overlay()
    # dans resizeEvent : self._overlay.update_geometry()
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QWidget


OVERLAY_BG     = "rgba(74, 158, 255, 0.18)"
OVERLAY_BORDER = "#4a9eff"


class DropOverlay(QLabel):
    """Label transparent aux events souris, affiché par-dessus la fenêtre."""

    def __init__(self, parent: QWidget):
        super().__init__(parent)
        self.setText(
            "📂\n\n"
            "Déposez votre fichier blackbox\n"
            "(.bbl / .bfl)"
        )
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setStyleSheet(f"""
            QLabel {{
                background: {OVERLAY_BG};
                color: #fff;
                font-size: 26px;
                font-weight: bold;
                letter-spacing: 1px;
                border: 4px dashed {OVERLAY_BORDER};
                border-radius: 16px;
                padding: 60px;
            }}
        """)
        self.hide()

    def show_overlay(self):
        self.update_geometry()
        self.raise_()
        self.show()

    def hide_overlay(self):
        self.hide()

    def update_geometry(self):
        if self.parent() is None:
            return
        # Marges intérieures pour ne pas masquer la sidebar / la status bar
        rect = self.parent().rect()
        margin = 24
        self.setGeometry(
            rect.x() + margin,
            rect.y() + margin,
            rect.width() - 2 * margin,
            rect.height() - 2 * margin,
        )
