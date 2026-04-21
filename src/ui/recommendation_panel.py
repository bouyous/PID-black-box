"""
Panel de diagnostic : contexte du vol, recommandations, CLI dump.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from analysis.header_parser import FlightConfig
from analysis.recommender import DiagnosticReport, Recommendation, Severity, AXIS_NAME
from analysis.symptom_db import CauseVector, RiskLevel, SymptomRule

# ---------------------------------------------------------------------------
# Couleurs par sévérité
# ---------------------------------------------------------------------------
SEV_COLOR = {
    Severity.OK:       '#27ae60',
    Severity.INFO:     '#3498db',
    Severity.WARNING:  '#f39c12',
    Severity.CRITICAL: '#e74c3c',
}
SEV_BG = {
    Severity.OK:       '#1a2e22',
    Severity.INFO:     '#1a2535',
    Severity.WARNING:  '#2e2410',
    Severity.CRITICAL: '#2e1010',
}


def _label(text: str, bold: bool = False, color: str = '#e0e0e0',
           size: int = 12) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    font = QFont()
    font.setPointSize(size)
    font.setBold(bold)
    lbl.setFont(font)
    lbl.setStyleSheet(f"color: {color};")
    return lbl


def _separator() -> QFrame:
    line = QFrame()
    line.setFrameShape(QFrame.Shape.HLine)
    line.setStyleSheet("color: #333;")
    return line


# ---------------------------------------------------------------------------
# Card d'une recommandation
# ---------------------------------------------------------------------------

class RecoCard(QFrame):
    def __init__(self, reco: Recommendation):
        super().__init__()
        color  = SEV_COLOR[reco.severity]
        bg     = SEV_BG[reco.severity]
        self.setStyleSheet(f"""
            QFrame {{
                background: {bg};
                border-left: 4px solid {color};
                border-radius: 4px;
                padding: 8px;
                margin: 3px 0;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # Titre : paramètre + changement
        layout.addWidget(_label(reco.label, bold=True, color=color, size=12))

        axis_str = f" — axe {AXIS_NAME[reco.axis]}" if reco.axis >= 0 else ""
        layout.addWidget(_label(f"Raison{axis_str} : {reco.reason}", size=11))


# ---------------------------------------------------------------------------
# Onglet Contexte : infos hardware + réglages actuels
# ---------------------------------------------------------------------------

class ContextTab(QWidget):
    def __init__(self, cfg: FlightConfig, drone_size: str):
        super().__init__()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # --- Hardware ---
        hw = QGroupBox("Hardware")
        hw.setStyleSheet("QGroupBox { color: #aaa; border: 1px solid #333; "
                         "border-radius:4px; margin-top:8px; padding:8px; }"
                         "QGroupBox::title { subcontrol-origin: margin; left:8px; }")
        hw_layout = QVBoxLayout(hw)
        hw_layout.setSpacing(4)

        hw_layout.addWidget(_label(f"FC : {cfg.board or 'inconnu'}"))
        hw_layout.addWidget(_label(f"Firmware : {cfg.firmware_version or 'inconnu'}"))
        hw_layout.addWidget(_label(f"Craft name : {cfg.craft_name or '—'}"))
        hw_layout.addWidget(_label(f"Profil sélectionné : {drone_size}"))
        hw_layout.addWidget(_label(
            f"Loop time : {cfg.looptime_us}µs  "
            f"({1_000_000 // max(cfg.looptime_us, 1):.0f}Hz)"
        ))
        hw_layout.addWidget(_label(f"Motor poles : {cfg.motor_poles}"))

        # Bidir DSHOT bien en évidence
        bidir_color = '#2ecc71' if cfg.dshot_bidir else '#e74c3c'
        bidir_text  = "✅ Bidirectionnel DSHOT : ACTIF (filtres RPM disponibles)" \
                      if cfg.dshot_bidir else \
                      "⚠️ Bidirectionnel DSHOT : INACTIF (filtres RPM désactivés)"
        hw_layout.addWidget(_label(bidir_text, bold=True, color=bidir_color))
        if cfg.dshot_bidir and cfg.rpm_filter_harmonics:
            hw_layout.addWidget(_label(
                f"   RPM filter : {cfg.rpm_filter_harmonics} harmoniques, "
                f"min {cfg.rpm_filter_min_hz}Hz, Q={cfg.rpm_filter_q}"
            ))

        layout.addWidget(hw)

        # --- PIDs actuels ---
        pid_box = QGroupBox("PIDs actuels")
        pid_box.setStyleSheet(hw.styleSheet())
        pid_layout = QVBoxLayout(pid_box)
        pid_layout.setSpacing(2)

        for ax, name in enumerate(AXIS_NAME):
            p = cfg.pid_p[ax]
            i = cfg.pid_i[ax]
            d = cfg.pid_d[ax]
            f = cfg.pid_f[ax] if ax < len(cfg.pid_f) else 0
            dm = cfg.d_min[ax] if ax < len(cfg.d_min) else 0
            d_str = f"D:{d}  D_min:{dm}" if ax < 2 else "D:—"
            pid_layout.addWidget(_label(
                f"{name} :  P:{p}   I:{i}   {d_str}   FF:{f}",
                size=12
            ))

        if cfg.simplified_mode > 0:
            pid_layout.addWidget(_separator())
            pid_layout.addWidget(_label(
                f"⚠️ Mode PID simplifié actif (mode {cfg.simplified_mode}, "
                f"master×{cfg.simplified_master}%)",
                color='#f39c12'
            ))

        layout.addWidget(pid_box)

        # --- Filtres actuels ---
        filt_box = QGroupBox("Filtres actuels")
        filt_box.setStyleSheet(hw.styleSheet())
        filt_layout = QVBoxLayout(filt_box)
        filt_layout.setSpacing(2)

        filt_layout.addWidget(_label(
            f"Gyro LPF1 : {cfg.gyro_lpf1_hz}Hz    "
            f"Gyro LPF2 : {cfg.gyro_lpf2_hz}Hz"
        ))
        filt_layout.addWidget(_label(
            f"D-term LPF1 : {cfg.dterm_lpf1_hz}Hz "
            f"(dyn {cfg.dterm_lpf1_dyn_min_hz}–{cfg.dterm_lpf1_dyn_max_hz}Hz)"
        ))
        filt_layout.addWidget(_label(f"D-term LPF2 : {cfg.dterm_lpf2_hz}Hz"))
        filt_layout.addWidget(_label(
            f"Notch dyn : {cfg.dyn_notch_count} filtres, "
            f"{cfg.dyn_notch_min_hz}–{cfg.dyn_notch_max_hz}Hz, "
            f"Q={cfg.dyn_notch_q}"
        ))

        layout.addWidget(filt_box)

        # --- FF / autres ---
        other_box = QGroupBox("Feed-forward & divers")
        other_box.setStyleSheet(hw.styleSheet())
        other_layout = QVBoxLayout(other_box)
        other_layout.setSpacing(2)
        other_layout.addWidget(_label(
            f"FF weight : Roll:{cfg.ff_weight[0]}  "
            f"Pitch:{cfg.ff_weight[1]}  Yaw:{cfg.ff_weight[2]}"
        ))
        other_layout.addWidget(_label(
            f"FF boost:{cfg.ff_boost}  smooth:{cfg.ff_smooth_factor}  "
            f"jitter:{cfg.ff_jitter_factor}"
        ))
        other_layout.addWidget(_label(
            f"Anti-gravity gain : {cfg.anti_gravity_gain}    "
            f"I-term windup : {cfg.iterm_windup}%"
        ))
        other_layout.addWidget(_label(
            f"TPA : {cfg.tpa_rate}% à partir de {cfg.tpa_breakpoint}"
        ))
        layout.addWidget(other_box)

        layout.addStretch()
        scroll.setWidget(inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)


# ---------------------------------------------------------------------------
# Onglet Recommandations
# ---------------------------------------------------------------------------

class RecommendationsTab(QWidget):
    def __init__(self, report: DiagnosticReport):
        super().__init__()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(6)

        # Résumé
        for line in report.summary:
            layout.addWidget(_label(f"• {line}", color='#aaa', size=11))

        if report.summary:
            layout.addWidget(_separator())

        # Avertissements globaux
        for warn in report.warnings:
            layout.addWidget(_label(f"⚠️  {warn}", color='#f39c12', size=11))

        if report.warnings:
            layout.addWidget(_separator())

        # Recommandations
        if not report.recommendations:
            layout.addWidget(_label(
                "✅  Aucune correction nécessaire détectée.",
                bold=True, color='#27ae60', size=13
            ))
        else:
            layout.addWidget(_label(
                f"{len(report.recommendations)} correction(s) suggérée(s) :",
                bold=True, size=13
            ))
            for reco in report.recommendations:
                layout.addWidget(RecoCard(reco))

        layout.addStretch()
        scroll.setWidget(inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)


# ---------------------------------------------------------------------------
# Onglet CLI Dump
# ---------------------------------------------------------------------------

class CliDumpTab(QWidget):
    def __init__(self, report: DiagnosticReport):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(6)

        layout.addWidget(_label(
            "Copiez ce bloc dans le CLI Betaflight (onglet CLI du Configurator).",
            color='#aaa', size=11
        ))

        self.text_edit = QPlainTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont("Consolas", 11))
        self.text_edit.setStyleSheet(
            "background: #111; color: #e0e0e0; border: 1px solid #333;"
        )
        self.text_edit.setPlainText(report.cli_dump())
        layout.addWidget(self.text_edit)

        btn = QPushButton("📋  Copier dans le presse-papiers")
        btn.setStyleSheet(
            "QPushButton { background:#2d2d2d; color:#fff; border:1px solid #555;"
            "padding:6px 14px; border-radius:4px; }"
            "QPushButton:hover { background:#3a3a3a; }"
        )
        btn.clicked.connect(self._copy)
        layout.addWidget(btn, alignment=Qt.AlignmentFlag.AlignRight)

    def _copy(self):
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.text_edit.toPlainText())


# ---------------------------------------------------------------------------
# Onglet Symptômes (base de connaissances gelo/geno/slug/over/vib)
# ---------------------------------------------------------------------------

_VECTOR_COLOR: dict[CauseVector, str] = {
    CauseVector.SOFTWARE:   '#3498db',
    CauseVector.PID:        '#9b59b6',
    CauseVector.ELECTRICAL: '#e74c3c',
    CauseVector.MECHANICAL: '#e67e22',
    CauseVector.GYRO:       '#1abc9c',
}

_RISK_COLOR: dict[RiskLevel, str] = {
    RiskLevel.LOW:    '#27ae60',
    RiskLevel.MEDIUM: '#f39c12',
    RiskLevel.HIGH:   '#e74c3c',
    RiskLevel.NA:     '#888',
}


class SymptomCard(QFrame):
    """Affiche une règle de symptôme complète avec ses causes et son flow."""

    def __init__(self, rule: SymptomRule):
        super().__init__()
        self.setStyleSheet("""
            QFrame {
                background: #1e1e2e;
                border: 1px solid #444;
                border-radius: 6px;
                padding: 6px;
                margin: 4px 0;
            }
        """)
        root = QVBoxLayout(self)
        root.setContentsMargins(10, 8, 10, 10)
        root.setSpacing(6)

        # Titre symptôme
        title = _label(f"⚠️  {rule.label_fr}", bold=True, color='#fff', size=13)
        root.addWidget(title)

        sev_color = '#e74c3c' if rule.severity == 'Haute' else '#f39c12'
        root.addWidget(_label(f"Sévérité : {rule.severity}", color=sev_color, size=11))
        root.addWidget(_label(rule.description, color='#aaa', size=11))

        root.addWidget(_separator())

        # --- Causes ---
        root.addWidget(_label("Causes potentielles :", bold=True, color='#ccc', size=12))

        for cause in rule.causes:
            v_color = _VECTOR_COLOR.get(cause.vector, '#888')
            r_color = _RISK_COLOR.get(cause.risk, '#888')

            cause_frame = QFrame()
            cause_frame.setStyleSheet(f"""
                QFrame {{
                    background: #252535;
                    border-left: 3px solid {v_color};
                    border-radius: 3px;
                    padding: 4px;
                    margin: 2px 0;
                }}
            """)
            cf_layout = QVBoxLayout(cause_frame)
            cf_layout.setContentsMargins(8, 4, 8, 4)
            cf_layout.setSpacing(2)

            cf_layout.addWidget(_label(
                f"[{cause.vector.value}]", bold=True, color=v_color, size=11
            ))
            cf_layout.addWidget(_label(cause.details, color='#ccc', size=11))

            if cause.params_to_adjust:
                params = ', '.join(cause.params_to_adjust)
                cf_layout.addWidget(_label(
                    f"Paramètres : {params}", color='#7fb3ff', size=11
                ))
            if cause.test_quantifiable:
                cf_layout.addWidget(_label(
                    f"Test : {cause.test_quantifiable}", color='#aaa', size=10
                ))
            if cause.action:
                cf_layout.addWidget(_label(
                    f"Action : {cause.action}", color='#2ecc71', size=11
                ))
            cf_layout.addWidget(_label(
                f"Risque sur-réglage : {cause.risk.value} — {cause.risk_reason}",
                color=r_color, size=10
            ))

            root.addWidget(cause_frame)

        # --- Flow de décision ---
        if rule.flow:
            root.addWidget(_separator())
            root.addWidget(_label("Arbre de décision :", bold=True, color='#ccc', size=12))
            for step in rule.flow:
                flow_txt = (
                    f"Étape {step.step} — Si {step.condition}\n"
                    f"  → {step.action}"
                )
                if step.result:
                    flow_txt += f"\n  Résultat probable : {step.result}"
                root.addWidget(_label(flow_txt, color='#bbb', size=11))


class SymptomTab(QWidget):
    """Onglet affichant les symptômes détectés et la base de connaissances associée."""

    def __init__(self, report: DiagnosticReport):
        super().__init__()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        if not report.matched_symptoms:
            layout.addWidget(_label(
                "✅  Aucun symptôme pathologique détecté dans ce vol.",
                bold=True, color='#27ae60', size=13
            ))
            layout.addWidget(_label(
                "Continuez à voler et importez une nouvelle blackbox "
                "après avoir modifié les PIDs si vous souhaitez comparer.",
                color='#888', size=11
            ))
        else:
            layout.addWidget(_label(
                f"🔍  {len(report.matched_symptoms)} symptôme(s) détecté(s) "
                "— consultez les causes et actions ci-dessous :",
                bold=True, color='#f39c12', size=13
            ))
            layout.addWidget(_label(
                "Ces diagnostics sont basés sur l'analyse de la blackbox. "
                "Appliquez les corrections progressivement et faites un vol de test entre chaque changement.",
                color='#888', size=11
            ))
            layout.addWidget(_separator())

            for rule in report.matched_symptoms:
                layout.addWidget(SymptomCard(rule))

        layout.addStretch()
        scroll.setWidget(inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)


# ---------------------------------------------------------------------------
# Widget principal de diagnostic (regroupe les 4 onglets)
# ---------------------------------------------------------------------------

class DiagnosticWidget(QWidget):
    def __init__(self, cfg: FlightConfig, report: DiagnosticReport,
                 drone_size: str):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        tabs = QTabWidget()
        tabs.addTab(ContextTab(cfg, drone_size),         "📋  Contexte")
        tabs.addTab(RecommendationsTab(report),          "🔍  Diagnostic")
        tabs.addTab(SymptomTab(report),                  "🩺  Symptômes")
        tabs.addTab(CliDumpTab(report),                  "💻  CLI Dump")

        # Aller directement au diagnostic s'il y a des problèmes
        if report.has_issues():
            tabs.setCurrentIndex(1)
        elif report.matched_symptoms:
            tabs.setCurrentIndex(2)

        layout.addWidget(tabs)
