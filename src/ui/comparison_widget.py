"""
Widget de comparaison avant/après entre deux sessions BBL.
Objectif : guider le pilote sans tourner en rond.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QPlainTextEdit, QPushButton, QScrollArea, QTabWidget,
    QVBoxLayout, QWidget,
)

from analysis.analyzer import SessionAnalysis
from analysis.header_parser import FlightConfig
from analysis.recommender import DiagnosticReport


def _lbl(text: str, bold: bool = False, color: str = '#e0e0e0', size: int = 12) -> QLabel:
    l = QLabel(text)
    l.setWordWrap(True)
    f = QFont()
    f.setPointSize(size)
    f.setBold(bold)
    l.setFont(f)
    l.setStyleSheet(f"color:{color};")
    return l


def _sep() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet("color:#333;")
    return line


def _color_delta(delta: float, good_direction: str = 'down') -> str:
    """Retourne la couleur selon si le changement est positif ou négatif."""
    if abs(delta) < 3:
        return '#888'
    if good_direction == 'down':
        return '#2ecc71' if delta < 0 else '#e74c3c'
    else:
        return '#2ecc71' if delta > 0 else '#e74c3c'


def _arrow(delta: float, good_direction: str = 'down') -> str:
    if abs(delta) < 3:
        return '→'
    if good_direction == 'down':
        return '↓' if delta < 0 else '↑'
    else:
        return '↑' if delta > 0 else '↓'


AXIS_NAMES = ['Roll', 'Pitch', 'Yaw']


class ComparisonWidget(QWidget):
    def __init__(self,
                 ref_sa: SessionAnalysis, ref_rp: DiagnosticReport,
                 ref_cfg: FlightConfig, ref_name: str,
                 new_sa: SessionAnalysis, new_rp: DiagnosticReport,
                 new_cfg: FlightConfig, new_name: str,
                 drone_size: str, flying_style: str,
                 is_oscillating: bool = False):
        super().__init__()
        self.ref_rp = ref_rp
        self.new_rp = new_rp
        self._is_oscillating = is_oscillating

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)

        # Titre
        layout.addWidget(_lbl(
            f"Comparaison  {ref_name}  →  {new_name}",
            bold=True, size=13
        ))
        layout.addWidget(_lbl(
            f"Profil : {drone_size}  /  {flying_style}",
            color='#888', size=11
        ))
        layout.addWidget(_sep())

        # Scores globaux
        layout.addWidget(self._build_score_section(ref_rp, new_rp))
        layout.addWidget(_sep())

        # Tableau par axe
        layout.addWidget(self._build_axis_table(ref_sa, new_sa))
        layout.addWidget(_sep())

        # Verdict global
        layout.addWidget(self._build_verdict(ref_rp, new_rp, ref_sa, new_sa, is_oscillating))
        layout.addWidget(_sep())

        # CLI dump de référence (pour revenir en arrière si besoin)
        if ref_rp.recommendations or ref_rp.filter_recommendations:
            layout.addWidget(self._build_rollback_section(ref_rp))

        layout.addStretch()
        scroll.setWidget(inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    # ------------------------------------------------------------------

    def _build_score_section(self, ref: DiagnosticReport, new: DiagnosticReport) -> QWidget:
        box = QGroupBox("Score de santé global (0 = catastrophique, 100 = parfait)")
        box.setStyleSheet("QGroupBox { color:#aaa; border:1px solid #333; border-radius:4px; "
                          "margin-top:8px; padding:8px; }"
                          "QGroupBox::title { subcontrol-origin:margin; left:8px; }")
        row = QHBoxLayout(box)
        row.setSpacing(24)

        for label, score, is_new in [("Référence", ref.health_score, False),
                                      ("Nouveau", new.health_score, True)]:
            col = QVBoxLayout()
            col.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col.addWidget(_lbl(label, color='#aaa', size=11))

            color = '#27ae60' if score >= 80 else '#f39c12' if score >= 55 else '#e74c3c'
            big = QLabel(str(score))
            f = QFont()
            f.setPointSize(36)
            f.setBold(True)
            big.setFont(f)
            big.setStyleSheet(f"color:{color};")
            big.setAlignment(Qt.AlignmentFlag.AlignCenter)
            col.addWidget(big)
            col.addWidget(_lbl("/100", color='#555', size=10))
            row.addLayout(col)

        # Delta
        delta = new.health_score - ref.health_score
        if abs(delta) >= 3:
            dcol = '#2ecc71' if delta > 0 else '#e74c3c'
            dsign = '+' if delta > 0 else ''
            row.addWidget(_lbl(f"{dsign}{delta} pts", bold=True, color=dcol, size=18))

        return box

    def _build_axis_table(self, ref: SessionAnalysis, new: SessionAnalysis) -> QWidget:
        box = QGroupBox("Détail par axe")
        box.setStyleSheet("QGroupBox { color:#aaa; border:1px solid #333; border-radius:4px; "
                          "margin-top:8px; padding:8px; }"
                          "QGroupBox::title { subcontrol-origin:margin; left:8px; }")
        grid = QGridLayout(box)
        grid.setSpacing(8)

        # En-têtes
        headers = ['Axe', 'Oscillation (score)', 'Bruit D', 'Temps montée (ms)',
                   'Overshoot (%)', 'Vibrations']
        for col, h in enumerate(headers):
            grid.addWidget(_lbl(h, bold=True, color='#aaa', size=10), 0, col)

        for row_idx, axis_idx in enumerate(range(3)):
            if axis_idx >= len(ref.axes) or axis_idx >= len(new.axes):
                continue
            ra = ref.axes[axis_idx]
            na = new.axes[axis_idx]
            r = row_idx + 1

            grid.addWidget(_lbl(AXIS_NAMES[axis_idx], bold=True), r, 0)

            # Oscillation score
            delta_osc = na.oscillation_score - ra.oscillation_score
            c = _color_delta(delta_osc * 100, 'down')
            grid.addWidget(_lbl(
                f"{ra.oscillation_score:.2f}  {_arrow(delta_osc*100,'down')}  "
                f"{na.oscillation_score:.2f}", color=c
            ), r, 1)

            # Bruit D
            delta_d = na.d_noise_rms - ra.d_noise_rms
            c = _color_delta(delta_d, 'down')
            grid.addWidget(_lbl(
                f"{ra.d_noise_rms:.1f}  {_arrow(delta_d,'down')}  {na.d_noise_rms:.1f}",
                color=c
            ), r, 2)

            # Temps de montée
            if ra.avg_rise_time_ms > 0 or na.avg_rise_time_ms > 0:
                delta_rt = na.avg_rise_time_ms - ra.avg_rise_time_ms
                c = _color_delta(delta_rt, 'down')
                grid.addWidget(_lbl(
                    f"{ra.avg_rise_time_ms:.0f}  {_arrow(delta_rt,'down')}  "
                    f"{na.avg_rise_time_ms:.0f}", color=c
                ), r, 3)
            else:
                grid.addWidget(_lbl("—", color='#555'), r, 3)

            # Overshoot
            if ra.avg_overshoot_pct > 0 or na.avg_overshoot_pct > 0:
                delta_ov = na.avg_overshoot_pct - ra.avg_overshoot_pct
                c = _color_delta(delta_ov, 'down')
                grid.addWidget(_lbl(
                    f"{ra.avg_overshoot_pct:.0f}  {_arrow(delta_ov,'down')}  "
                    f"{na.avg_overshoot_pct:.0f}", color=c
                ), r, 4)
            else:
                grid.addWidget(_lbl("—", color='#555'), r, 4)

            # Vibrations non filtrées
            ref_vib = sum(1 for p in ra.vibration_peaks if not p.covered_by_rpm_filter)
            new_vib = sum(1 for p in na.vibration_peaks if not p.covered_by_rpm_filter)
            delta_v = new_vib - ref_vib
            c = _color_delta(delta_v, 'down')
            grid.addWidget(_lbl(
                f"{ref_vib}  {_arrow(delta_v,'down')}  {new_vib}", color=c
            ), r, 5)

        return box

    def _build_verdict(self, ref_rp: DiagnosticReport, new_rp: DiagnosticReport,
                       ref_sa: SessionAnalysis, new_sa: SessionAnalysis,
                       is_oscillating: bool = False) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        delta = new_rp.health_score - ref_rp.health_score

        if delta >= 8:
            emoji, color, title = "✅", '#27ae60', "Amélioration significative"
            detail = (f"Le score a progressé de {delta} points. "
                      "Les réglages vont dans la bonne direction. "
                      "Vous pouvez continuer à affiner.")
        elif delta >= 3:
            emoji, color, title = "↗️", '#2ecc71', "Légère amélioration"
            detail = (f"Amélioration de {delta} points. "
                      "Continuez dans cette direction, les gains restent modestes.")
        elif delta >= -3:
            emoji, color, title = "ℹ️", '#3498db', "Résultat similaire"
            detail = ("La différence est minime (< 3 pts). "
                      "Les sensations en vol sont le meilleur indicateur à ce stade. "
                      "Évitez de continuer à modifier si les sensations sont bonnes.")
        elif delta >= -8:
            emoji, color, title = "⚠️", '#f39c12', "Légère régression"
            detail = (f"Le score a baissé de {abs(delta)} points. "
                      "Revenez partiellement aux réglages de référence "
                      "et analysez quelle modification a causé cette régression.")
        else:
            emoji, color, title = "🔴", '#e74c3c', "Régression — revenez en arrière"
            detail = (f"Le score a baissé de {abs(delta)} points. "
                      "Remettez les réglages de référence avant le prochain vol. "
                      "Le bloc CLI ci-dessous vous permet de restaurer la situation initiale.")

        layout.addWidget(_lbl(f"{emoji}  {title}", bold=True, color=color, size=14))
        layout.addWidget(_lbl(detail, color='#ccc', size=11))

        # Avertissement oscillation détectée (priorité haute)
        if is_oscillating:
            osc_frame = QFrame()
            osc_frame.setStyleSheet(
                "QFrame { background:#2e1010; border-left:4px solid #e74c3c; "
                "border-radius:4px; padding:8px; margin:4px 0; }"
            )
            osc_lay = QVBoxLayout(osc_frame)
            osc_lay.setContentsMargins(8, 6, 8, 6)
            osc_lay.setSpacing(4)
            osc_lay.addWidget(_lbl(
                "🔴  STOP — Vous tournez en rond",
                bold=True, color='#e74c3c', size=13
            ))
            osc_lay.addWidget(_lbl(
                "Le score monte et descend en alternance. Continuer à changer les PIDs "
                "ne mènera nulle part. Ce que vous devez faire :\n"
                "  1. Vérifiez mécaniquement le drone (visserie, hélices, roulements, condensateur).\n"
                "  2. Appliquez d'abord les réglages filtres (onglet Diagnostic → Valeurs brutes).\n"
                "  3. Volez 2 minutes en douceur, refaites une blackbox fraîche, puis comparez.",
                color='#ffaaaa', size=11
            ))
            layout.addWidget(osc_frame)

        # Avertissement "ne pas tourner en rond" (score stagne sans oscillation)
        n_changes_ref  = len([r for r in ref_rp.recommendations if r.suggested != r.current])
        n_changes_new  = len([r for r in new_rp.recommendations if r.suggested != r.current])
        if not is_oscillating and n_changes_ref > 0 and n_changes_new > 0 and delta < 5:
            layout.addWidget(_lbl(
                "⚠️  Le logiciel propose encore des corrections alors que le score stagne. "
                "Avant de continuer, vérifiez mécaniquement le drone "
                "(hélices, visserie, anti-vibrations) — une source physique peut bloquer les progrès.",
                color='#f39c12', size=11
            ))

        return box

    def _build_rollback_section(self, ref_rp: DiagnosticReport) -> QWidget:
        box = QGroupBox("Restaurer les réglages de référence (si régression)")
        box.setStyleSheet("QGroupBox { color:#f39c12; border:1px solid #444; border-radius:4px; "
                          "margin-top:8px; padding:8px; }"
                          "QGroupBox::title { subcontrol-origin:margin; left:8px; }")
        layout = QVBoxLayout(box)
        layout.addWidget(_lbl(
            "Ce sont les réglages recommandés AVANT vos modifications. "
            "Copiez-les dans le CLI Betaflight pour revenir à l'état de référence.",
            color='#aaa', size=11
        ))

        # Génère un CLI dump inverse : remet les valeurs originales (current des recommandations)
        lines = [
            "# === RESTAURATION — réglages de la session de référence ===",
            "",
        ]
        for r in ref_rp.recommendations:
            if r.suggested != r.current:
                lines.append(f"set {r.param} = {r.current}    # restauration")
        if ref_rp.filter_recommendations:
            lines.append("")
            lines.append("# Désactiver les filtres ajoutés :")
            lines.append("set gyro_notch1_hz = 0")
            lines.append("set gyro_notch1_cutoff = 0")
        lines += ["", "save"]

        te = QPlainTextEdit()
        te.setReadOnly(True)
        te.setFont(QFont("Consolas", 10))
        te.setStyleSheet("background:#111; color:#e0e0e0; border:1px solid #333;")
        te.setMaximumHeight(150)
        te.setPlainText("\n".join(lines))
        layout.addWidget(te)

        btn = QPushButton("📋  Copier la restauration")
        btn.setStyleSheet(
            "QPushButton { background:#2d2d2d; color:#fff; border:1px solid #555;"
            "padding:5px 12px; border-radius:4px; }"
            "QPushButton:hover { background:#3a3a3a; }"
        )
        btn.clicked.connect(lambda: self._copy_text(te.toPlainText()))
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignRight)

        return box

    @staticmethod
    def _copy_text(text: str):
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(text)
