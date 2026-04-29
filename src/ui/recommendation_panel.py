"""
Panel de diagnostic : contexte du vol, recommandations, CLI dump.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from analysis.analyzer import FlightTypeResult, SessionAnalysis
from analysis.header_parser import FlightConfig
from analysis.recommender import DiagnosticReport, Recommendation, Severity, AXIS_NAME
from analysis.sliders import compute_sliders
from analysis.symptom_db import CauseVector, RiskLevel, SymptomRule

# ---------------------------------------------------------------------------
# Gate de sécurité : "J'accepte les risques avant d'afficher les recos".
# Compteur PAR OUVERTURE de l'application — il se réinitialise à chaque
# lancement (variable de module). Le gate disparaît après 3 acceptations
# dans la session courante. La prochaine fois qu'on lance le logiciel,
# il réapparaîtra de zéro — c'est volontaire pour qu'un pilote ne s'habitue
# jamais à cliquer sans lire.
# ---------------------------------------------------------------------------

_SESSION_GATE_CLICKS: int = 0
_SESSION_GATE_LIMIT: int = 3


def _gate_auto_bypass() -> bool:
    return _SESSION_GATE_CLICKS >= _SESSION_GATE_LIMIT


def _increment_gate_count():
    global _SESSION_GATE_CLICKS
    _SESSION_GATE_CLICKS += 1


def _strip_cli_comments(dump: str) -> str:
    """Retire lignes # et commentaires inline pour un copier-coller propre."""
    out = []
    for line in dump.splitlines():
        s = line.strip()
        if not s or s.startswith('#'):
            continue
        if '#' in line:
            line = line.split('#', 1)[0].rstrip()
        out.append(line)
    return "\n".join(out)


def _parse_filter_line(line: str) -> tuple[str, str]:
    """'set foo = 145    # était 170 — bruit HF' → ('set foo = 145', 'était 170 — bruit HF')"""
    if line.strip().startswith('#'):
        return ('', line.lstrip('# ').strip())
    if '#' in line:
        cmd, _, note = line.partition('#')
        return (cmd.strip(), note.strip())
    return (line.strip(), '')

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
        # Encarts compactés (avril 2026) : padding/margin réduits pour montrer
        # plus de réglages à l'écran sans scroller.
        self.setStyleSheet(f"""
            QFrame {{
                background: {bg};
                border-left: 3px solid {color};
                border-radius: 3px;
                padding: 2px;
                margin: 1px 0;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 1, 6, 1)
        layout.setSpacing(0)

        axis_str = f" ({AXIS_NAME[reco.axis]})" if reco.axis >= 0 else ""
        layout.addWidget(_label(reco.label + axis_str, bold=True, color=color, size=10))
        layout.addWidget(_label(reco.reason, color='#aaa', size=9))


class GenericCard(QFrame):
    """Card générique pour afficher filtres / sliders."""
    def __init__(self, title: str, detail: str, severity: Severity = Severity.INFO):
        super().__init__()
        color = SEV_COLOR[severity]
        bg = SEV_BG[severity]
        self.setStyleSheet(f"""
            QFrame {{
                background: {bg};
                border-left: 3px solid {color};
                border-radius: 3px;
                padding: 2px;
                margin: 1px 0;
            }}
        """)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 1, 6, 1)
        layout.setSpacing(0)
        layout.addWidget(_label(title, bold=True, color=color, size=10))
        if detail:
            layout.addWidget(_label(detail, color='#aaa', size=9))


# ---------------------------------------------------------------------------
# Onglet Contexte : infos hardware + réglages actuels
# ---------------------------------------------------------------------------

_FLIGHT_TYPE_COLOR = {
    "Freestyle":            '#27ae60',
    "Vol mixte":            '#f39c12',
    "Stationnaire / Hover": '#3498db',
}
_FLIGHT_TYPE_ICON = {
    "Freestyle":            "🟢",
    "Vol mixte":            "🟡",
    "Stationnaire / Hover": "🔵",
}


class ContextTab(QWidget):
    def __init__(self, cfg: FlightConfig, drone_size: str,
                 flight_type: FlightTypeResult | None = None):
        super().__init__()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        # --- Type de vol détecté ---
        if flight_type is not None:
            ft_box = QGroupBox("Type de vol détecté")
            ft_box.setStyleSheet(
                "QGroupBox { color: #aaa; border: 1px solid #333; "
                "border-radius:4px; margin-top:8px; padding:8px; }"
                "QGroupBox::title { subcontrol-origin: margin; left:8px; }"
            )
            ft_layout = QVBoxLayout(ft_box)
            ft_layout.setSpacing(4)

            color = _FLIGHT_TYPE_COLOR.get(flight_type.label, '#e0e0e0')
            icon  = _FLIGHT_TYPE_ICON.get(flight_type.label, '⬜')
            ft_layout.addWidget(_label(
                f"{icon}  {flight_type.label.upper()}",
                bold=True, color=color, size=14
            ))
            ft_layout.addWidget(_label(
                f"Confiance : {flight_type.confidence * 100:.0f}%   "
                f"(score : {flight_type.score}/9)",
                color='#aaa', size=10
            ))
            ft_layout.addWidget(_label(
                f"Setpoint max : {flight_type.max_setpoint_dps:.0f}°/s   •   "
                f"Taux haute cadence : {flight_type.time_high_rate_pct * 100:.1f}%   •   "
                f"Amplitude throttle : {flight_type.throttle_p2p * 100:.0f}%",
                color='#888', size=10
            ))
            layout.addWidget(ft_box)

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

def _build_reco_list_raw(report: DiagnosticReport) -> QWidget:
    """Construit la vue 'Valeurs brutes' : filtres en premier, puis PIDs.
    Splitter vertical entre les deux sections pour redimensionner."""

    container = QWidget()
    container_layout = QVBoxLayout(container)
    container_layout.setContentsMargins(0, 0, 0, 0)
    container_layout.setSpacing(0)

    splitter = QSplitter(Qt.Orientation.Vertical)
    splitter.setHandleWidth(6)
    splitter.setStyleSheet(
        "QSplitter::handle { background:#2a2a2a; }"
        "QSplitter::handle:hover { background:#4a9eff; }"
    )

    # ===== FILTRES =====
    filter_widget = QScrollArea()
    filter_widget.setWidgetResizable(True)
    filter_widget.setFrameShape(QFrame.Shape.NoFrame)
    filter_inner = QWidget()
    filter_layout = QVBoxLayout(filter_inner)
    filter_layout.setContentsMargins(8, 4, 8, 6)
    filter_layout.setSpacing(2)

    filter_cards: list[tuple[str, str]] = []
    current_note = ''
    for line in report.filter_recommendations:
        cmd, note = _parse_filter_line(line)
        if not cmd:
            current_note = note
            continue
        filter_cards.append((cmd, note or current_note))
        current_note = ''

    if filter_cards:
        filter_layout.addWidget(_label(
            f"🎛  Filtres — {len(filter_cards)} réglage(s)", bold=True,
            color='#3498db', size=13
        ))
        filter_layout.addWidget(_label(
            "Les filtres sont la base d'un tune propre : vibrations, "
            "bruit HF, résonances.", color='#aaa', size=10))
        for cmd, note in filter_cards:
            filter_layout.addWidget(GenericCard(cmd, note, Severity.INFO))
    else:
        filter_layout.addWidget(_label("🎛  Filtres : OK, rien à ajuster.",
                                       bold=True, color='#27ae60', size=12))
    filter_layout.addStretch()
    filter_widget.setWidget(filter_inner)
    splitter.addWidget(filter_widget)

    # ===== PIDS =====
    pid_widget = QScrollArea()
    pid_widget.setWidgetResizable(True)
    pid_widget.setFrameShape(QFrame.Shape.NoFrame)
    pid_inner = QWidget()
    pid_layout = QVBoxLayout(pid_inner)
    pid_layout.setContentsMargins(8, 6, 8, 6)
    pid_layout.setSpacing(2)

    pid_changes = [r for r in report.recommendations if r.suggested != r.current]
    if pid_changes:
        pid_layout.addWidget(_label(
            f"⚙  PID — {len(pid_changes)} ajustement(s)",
            bold=True, color='#e0e0e0', size=13
        ))
        for reco in pid_changes:
            pid_layout.addWidget(RecoCard(reco))
    else:
        pid_layout.addWidget(_label("⚙  PID : OK, aucun changement nécessaire.",
                                    bold=True, color='#27ae60', size=12))
    pid_layout.addStretch()
    pid_widget.setWidget(pid_inner)
    splitter.addWidget(pid_widget)

    splitter.setStretchFactor(0, 1)
    splitter.setStretchFactor(1, 1)
    splitter.setSizes([350, 350])

    container_layout.addWidget(splitter)
    return container


def _build_reco_list_sliders(report: DiagnosticReport) -> QWidget:
    """Vue Sliders : PID en sliders (0.00-2.00), filtres en raw."""
    inner = QWidget()
    layout = QVBoxLayout(inner)
    layout.setContentsMargins(8, 4, 8, 6)
    layout.setSpacing(2)

    cfg = report._cfg
    if cfg is None:
        layout.addWidget(_label("Sliders indisponibles (pas de config firmware).",
                                color='#f39c12', size=12))
        layout.addStretch()
        return inner

    adj = compute_sliders(report.recommendations, cfg, report.filter_recommendations)

    # ===== FILTRES (identiques au mode brut — toujours en raw) =====
    filter_cards: list[tuple[str, str]] = []
    current_note = ''
    for line in report.filter_recommendations:
        cmd, note = _parse_filter_line(line)
        if not cmd:
            current_note = note
            continue
        filter_cards.append((cmd, note or current_note))
        current_note = ''

    if filter_cards:
        layout.addWidget(_label(
            f"🎛  Filtres (valeurs brutes) — {len(filter_cards)}",
            bold=True, color='#3498db', size=13))
        for cmd, note in filter_cards:
            layout.addWidget(GenericCard(cmd, note, Severity.INFO))
        layout.addWidget(_separator())
    else:
        layout.addWidget(_label("🎛  Filtres : OK.",
                                bold=True, color='#27ae60', size=12))
        layout.addWidget(_separator())

    # ===== PID (sliders 0.00-2.00) =====
    # Note : activer simplified_pids_mode écrase les PIDs bruts du firmware.
    layout.addWidget(_label(
        "⚠️  Activer les sliders remplace les valeurs PID brutes par celles "
        "calculées depuis les sliders. Sauvegardez votre diff Betaflight avant.",
        color='#f39c12', size=10))

    slider_rows = []
    def _row(label, cur, new, cli_name):
        if new != cur:
            slider_rows.append((label, cur, new, cli_name))

    _row('Multiplicateur Maître', cfg.simplified_master or 100,
         adj.master_multiplier, 'simplified_master_multiplier')
    _row('Suivi (Gains P & I)', cfg.simplified_pi_gain, adj.pi_gain,
         'simplified_pi_gain')
    _row('Dérive - Oscillations (Gains I)', cfg.simplified_i_gain,
         adj.i_gain, 'simplified_i_gain')
    _row('Atténuation (D Gains)', cfg.simplified_d_gain, adj.d_gain,
         'simplified_d_gain')
    _row('Atténuation dynamique (D Max)', cfg.simplified_dmax_gain,
         adj.dmax_gain, 'simplified_dmax_gain')
    _row('Réponse des sticks (Gains FF)', cfg.simplified_feedforward,
         adj.feedforward_gain, 'simplified_feedforward_gain')
    _row('Suivi du Pitch (Pitch:Roll P,I,FF)', cfg.simplified_pitch_pi_gain,
         adj.pitch_pi_gain, 'simplified_pitch_pi_gain')

    if slider_rows:
        layout.addWidget(_label(
            f"⚙  Sliders PID — {len(slider_rows)} ajustement(s)",
            bold=True, color='#e0e0e0', size=13))
        for label, cur, new, _ in slider_rows:
            f_cur = cur / 100.0
            f_new = new / 100.0
            direction = "↓" if new < cur else "↑"
            title = f"{label} : {f_cur:.2f}  {direction}  {f_new:.2f}"
            det = f"Déplacez le curseur Betaflight à {f_new:.2f} (valeur CLI : {new})"
            layout.addWidget(GenericCard(title, det, Severity.INFO))
    else:
        layout.addWidget(_label("⚙  Sliders PID : OK, aucun déplacement.",
                                bold=True, color='#27ae60', size=12))

    if adj.notes:
        layout.addWidget(_separator())
        layout.addWidget(_label("Notes de conversion :", color='#aaa', size=10))
        for n in adj.notes:
            layout.addWidget(_label(f"  • {n}", color='#888', size=10))

    layout.addStretch()
    return inner


def _build_safety_gate(on_accept) -> QWidget:
    """Page d'avertissement avec bouton 'J'ai compris'. Partagée Diag/CLI."""
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(30, 30, 30, 30)
    lay.setSpacing(14)

    box = QFrame()
    box.setStyleSheet(
        "QFrame { background:#2e2410; border-left:4px solid #f39c12;"
        " border-radius:6px; padding:12px; }"
    )
    box_lay = QVBoxLayout(box)
    box_lay.setSpacing(8)
    box_lay.addWidget(_label("⚠️  PROCÉDURE DE SÉCURITÉ OBLIGATOIRE",
                              bold=True, color='#f39c12', size=16))
    box_lay.addWidget(_label(
        "1.  Sauvegardez votre diff Betaflight avant toute modification.",
        color='#ffd479', size=13))
    box_lay.addWidget(_label(
        "2.  Volez 30 secondes en douceur après chaque changement.",
        color='#ffd479', size=13))
    box_lay.addWidget(_label(
        "3.  Posez le drone et touchez les moteurs à la main.",
        color='#ffd479', size=13))
    box_lay.addWidget(_label(
        "4.  Si un moteur est > 10 °C au-dessus de l'ambiant : STOP. "
        "Cherchez la cause physique (hélice abîmée, roulement mort, "
        "vis desserrée) avant d'aller plus loin.",
        color='#ffd479', size=13))
    box_lay.addWidget(_label(
        "5.  Moteurs tièdes ? Volez plus longtemps et refaites une black box "
        "pour affiner le tune.",
        color='#ffd479', size=13))
    lay.addWidget(box)

    lay.addWidget(_label(
        "Le créateur n'est pas responsable en cas de dommage matériel.",
        color='#bbb', size=11))

    lay.addStretch()

    btn = QPushButton("✓  J'ai compris — afficher les recommandations")
    btn.setStyleSheet(
        "QPushButton { background:#2d5a3d; color:#fff; border:1px solid #3e7a55;"
        " padding:12px 20px; border-radius:6px; font-size:14px; font-weight:bold; }"
        "QPushButton:hover { background:#3a7050; }"
    )
    btn.clicked.connect(on_accept)
    lay.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
    return w


class RecommendationsTab(QWidget):
    def __init__(self, report: DiagnosticReport):
        super().__init__()
        from PyQt6.QtWidgets import QStackedWidget
        self.report = report
        self.stack = QStackedWidget()

        if _gate_auto_bypass():
            self.stack.addWidget(self._build_content_page(report))
        else:
            self.stack.addWidget(_build_safety_gate(self._on_gate_accepted))
            self.stack.addWidget(self._build_content_page(report))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.stack)

    def _on_gate_accepted(self):
        _increment_gate_count()
        self.stack.setCurrentIndex(1)

    def _build_content_page(self, report: DiagnosticReport) -> QWidget:
        w = QWidget()
        outer = QVBoxLayout(w)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(4)

        # Bouton retour à la procédure (plus compact)
        back_row = QHBoxLayout()
        back_row.setContentsMargins(0, 0, 0, 0)
        back = QPushButton("← Procédure de sécurité")
        back.setStyleSheet(
            "QPushButton { background:#2d2d2d; color:#ccc; border:1px solid #555;"
            " padding:2px 8px; border-radius:3px; font-size:10px; }"
            "QPushButton:hover { background:#3a3a3a; }"
        )
        back.setMaximumHeight(22)
        # Si bypass actif, la gate n'existe pas (index 0 = contenu) → masquer le bouton
        back.setVisible(not _gate_auto_bypass())
        back.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        back_row.addWidget(back)
        back_row.addStretch()
        outer.addLayout(back_row)

        # Splitter vertical : header (résumé / warnings) ↔ encarts réglages.
        # L'utilisateur peut tirer la poignée pour agrandir l'une ou l'autre zone
        # et arrêter de scroller.
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.setHandleWidth(6)
        splitter.setStyleSheet(
            "QSplitter::handle { background:#2a2a2a; }"
            "QSplitter::handle:hover { background:#4a9eff; }"
        )

        header_scroll = QScrollArea()
        header_scroll.setWidgetResizable(True)
        header_scroll.setFrameShape(QFrame.Shape.NoFrame)
        header_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        header = QWidget()
        hlay = QVBoxLayout(header)
        hlay.setContentsMargins(8, 2, 8, 2)
        hlay.setSpacing(1)
        for line in report.summary:
            hlay.addWidget(_label(f"• {line}", color='#aaa', size=9))
        for warn in report.warnings:
            hlay.addWidget(_label(f"⚠️  {warn}", color='#f39c12', size=9))
        header_scroll.setWidget(header)
        splitter.addWidget(header_scroll)

        sub = QTabWidget()
        sub.setStyleSheet("QTabBar::tab { padding: 4px 14px; }")

        # Vue brute : contient déjà son propre splitter Filtres/PID + scrolls
        sub.addTab(_build_reco_list_raw(report), "Valeurs brutes")

        scroll_sl = QScrollArea()
        scroll_sl.setWidgetResizable(True)
        scroll_sl.setFrameShape(QFrame.Shape.NoFrame)
        scroll_sl.setWidget(_build_reco_list_sliders(report))
        sub.addTab(scroll_sl, "Sliders PID")

        splitter.addWidget(sub)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([100, 600])

        outer.addWidget(splitter)
        return w


# ---------------------------------------------------------------------------
# Onglet CLI Dump
# ---------------------------------------------------------------------------

class CliDumpTab(QWidget):
    """Deux pages : avertissement/procédure → 'J'ai compris' → dump copiable."""

    def __init__(self, report: DiagnosticReport):
        super().__init__()
        self.report = report
        from PyQt6.QtWidgets import QStackedWidget
        self.stack = QStackedWidget()

        if _gate_auto_bypass():
            self.stack.addWidget(self._build_dump_page())
        else:
            self.stack.addWidget(self._build_gate_page())
            self.stack.addWidget(self._build_dump_page())

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.stack)

    # -- Page 1 : avertissement, gros texte --
    def _build_gate_page(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(30, 30, 30, 30)
        lay.setSpacing(14)

        lay.addWidget(_label(
            f"Profil : {self.report.drone_size}   •   "
            f"Style : {self.report.flying_style}   •   "
            f"Score : {self.report.health_score}/100",
            bold=True, color='#e0e0e0', size=14
        ))

        # Bloc sécurité, grand et visible
        from PyQt6.QtWidgets import QFrame
        box = QFrame()
        box.setStyleSheet(
            "QFrame { background:#2e2410; border-left:4px solid #f39c12;"
            " border-radius:6px; padding:12px; }"
        )
        box_lay = QVBoxLayout(box)
        box_lay.setSpacing(8)
        box_lay.addWidget(_label("⚠️  PROCÉDURE DE SÉCURITÉ OBLIGATOIRE",
                                  bold=True, color='#f39c12', size=16))
        box_lay.addWidget(_label(
            "1.  Sauvegardez votre diff Betaflight avant toute modification.",
            color='#ffd479', size=13))
        box_lay.addWidget(_label(
            "2.  Volez 30 secondes en douceur après chaque changement.",
            color='#ffd479', size=13))
        box_lay.addWidget(_label(
            "3.  Posez le drone et touchez les moteurs à la main.",
            color='#ffd479', size=13))
        box_lay.addWidget(_label(
            "4.  Si un moteur est > 10 °C au-dessus de l'ambiant : STOP. "
            "Cherchez la cause physique (hélice abîmée, roulement mort, "
            "vis desserrée) avant d'aller plus loin.",
            color='#ffd479', size=13))
        box_lay.addWidget(_label(
            "5.  Moteurs tièdes ? Volez plus longtemps et refaites une black box "
            "pour affiner le tune.",
            color='#ffd479', size=13))
        lay.addWidget(box)

        lay.addWidget(_label(
            "Le créateur n'est pas responsable en cas de dommage matériel.",
            color='#bbb', size=11))

        n_pid = sum(1 for r in self.report.recommendations
                    if r.suggested != r.current)
        n_flt = len([l for l in self.report.filter_recommendations
                     if l.strip() and not l.strip().startswith('#')])
        lay.addWidget(_label(
            f"Prêt à appliquer : {n_flt} commande(s) filtre + "
            f"{n_pid} ajustement(s) PID.",
            color='#e0e0e0', size=13))

        lay.addStretch()

        btn = QPushButton("✓  J'ai compris — afficher les commandes CLI")
        btn.setStyleSheet(
            "QPushButton { background:#2d5a3d; color:#fff; border:1px solid #3e7a55;"
            " padding:12px 20px; border-radius:6px; font-size:14px; font-weight:bold; }"
            "QPushButton:hover { background:#3a7050; }"
        )
        btn.clicked.connect(self._on_cli_gate_accepted)
        lay.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
        return w

    def _on_cli_gate_accepted(self):
        _increment_gate_count()
        self.stack.setCurrentIndex(1)

    # -- Page 2 : dump copiable --
    def _build_dump_page(self) -> QWidget:
        from PyQt6.QtWidgets import QRadioButton, QButtonGroup
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 8, 8, 8)
        lay.setSpacing(4)

        top = QHBoxLayout()
        back = QPushButton("← Retour à la procédure")
        back.setStyleSheet(
            "QPushButton { background:#2d2d2d; color:#ccc; border:1px solid #555;"
            " padding:4px 10px; border-radius:4px; }"
            "QPushButton:hover { background:#3a3a3a; }"
        )
        back.setVisible(not _gate_auto_bypass())
        back.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        top.addWidget(back)

        top.addWidget(_label("Mode :", color='#ccc', size=11))
        # Style custom pour les radio buttons : indicateur ROND avec POINT bleu
        # quand sélectionné. Le défaut Qt6 est illisible (rond gris qui s'efface).
        radio_style = """
            QRadioButton {
                color: #ddd;
                font-size: 13px;
                padding: 4px 10px;
                spacing: 8px;
                background: #2a2a2a;
                border: 1px solid #444;
                border-radius: 4px;
            }
            QRadioButton:hover {
                background: #333;
                border-color: #4a9eff;
            }
            QRadioButton:checked {
                background: #1e3a5f;
                color: #fff;
                border: 2px solid #4a9eff;
                font-weight: bold;
            }
            QRadioButton::indicator {
                width: 16px;
                height: 16px;
                border-radius: 9px;
                border: 2px solid #888;
                background: #1a1a1a;
            }
            QRadioButton::indicator:hover {
                border-color: #4a9eff;
            }
            QRadioButton::indicator:checked {
                border: 2px solid #4a9eff;
                background: qradialgradient(cx:0.5, cy:0.5, radius:0.5,
                    stop:0 #4a9eff, stop:0.55 #4a9eff, stop:0.6 #1e3a5f, stop:1 #1e3a5f);
            }
        """
        self.rb_raw = QRadioButton("Valeurs brutes")
        self.rb_slider = QRadioButton("Sliders PID")
        self.rb_raw.setChecked(True)
        self.rb_raw.setStyleSheet(radio_style)
        self.rb_slider.setStyleSheet(radio_style)
        self.rb_raw.setCursor(Qt.CursorShape.PointingHandCursor)
        self.rb_slider.setCursor(Qt.CursorShape.PointingHandCursor)
        grp = QButtonGroup(w)
        grp.addButton(self.rb_raw)
        grp.addButton(self.rb_slider)
        self.rb_raw.toggled.connect(self._refresh)
        self.rb_slider.toggled.connect(self._refresh)
        top.addWidget(self.rb_raw)
        top.addWidget(self.rb_slider)
        top.addStretch()
        lay.addLayout(top)

        lay.addWidget(_label(
            "Copiez ce bloc dans l'onglet CLI du Configurator, puis tapez 'save'.",
            color='#aaa', size=10))

        self.text_edit = QPlainTextEdit()
        self.text_edit.setReadOnly(True)
        self.text_edit.setFont(QFont("Consolas", 11))
        self.text_edit.setStyleSheet(
            "background: #111; color: #e0e0e0; border: 1px solid #333;"
        )
        lay.addWidget(self.text_edit)
        self._refresh()

        btn = QPushButton("📋  Copier dans le presse-papiers")
        btn.setStyleSheet(
            "QPushButton { background:#2d2d2d; color:#fff; border:1px solid #555;"
            "padding:6px 14px; border-radius:4px; }"
            "QPushButton:hover { background:#3a3a3a; }"
        )
        btn.clicked.connect(self._copy)
        lay.addWidget(btn, alignment=Qt.AlignmentFlag.AlignRight)
        return w

    def _refresh(self):
        if self.rb_slider.isChecked():
            raw = self.report.cli_dump_sliders()
        else:
            raw = self.report.cli_dump()
        self.text_edit.setPlainText(_strip_cli_comments(raw))

    def _copy(self):
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText(self.text_edit.toPlainText())


# ---------------------------------------------------------------------------
# Onglet Symptômes (base de connaissances jello/jitter/slug/over/vib)
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
# Onglet Check OK — checklist hardware pré-réglage
# ---------------------------------------------------------------------------

_STATUS_BADGE = {
    'ok':       ('✅', '#27ae60', '#1a2e22', 'OK'),
    'warning':  ('⚠️',  '#f39c12', '#2e2410', 'À VÉRIFIER'),
    'critical': ('🔴', '#e74c3c', '#2e1010', 'PROBLÈME'),
    'unknown':  ('❔', '#888',    '#1e1e1e', 'NON DÉTECTABLE'),
}


def _evaluate_hardware(sa: SessionAnalysis | None,
                       cfg: FlightConfig) -> list[tuple[str, str, str, str]]:
    """Auto-diagnostic hardware à partir de l'analyse blackbox.
    Retourne une liste de (icon, title, status, detail).
    status ∈ {'ok','warning','critical','unknown'}."""
    if sa is None or not sa.axes:
        return []

    axes_rp = sa.axes[:2]   # Roll & Pitch (Yaw moins fiable mécaniquement)

    # Stats agrégées
    imb = max((aa.motor_imbalance for aa in axes_rp), default=0.0)
    avg_hf = sum(aa.hf_noise_ratio for aa in axes_rp) / max(len(axes_rp), 1)
    sag = sa.battery_sag_v_per_cell
    has_low_freq_osc = any(0 < aa.dominant_freq_hz < 30 and aa.has_oscillation
                           for aa in axes_rp)

    # Pics structurels (non couverts RPM, hors harmoniques moteur)
    structural_peaks = sum(
        1 for aa in axes_rp for p in aa.vibration_peaks
        if not p.covered_by_rpm_filter and p.harmonic == 0 and 100 < p.freq_hz < 500
    )
    # Pics liés aux hélices (harmoniques RPM non filtrées)
    prop_peaks = sum(
        1 for aa in axes_rp for p in aa.vibration_peaks
        if not p.covered_by_rpm_filter and p.harmonic > 0
    )

    out: list[tuple[str, str, str, str]] = []

    # 1. Visserie du châssis
    if structural_peaks >= 4:
        out.append(("🔩", "Visserie du châssis", "critical",
                    f"{structural_peaks} pics de vibration structurelle non filtrés "
                    f"(100–500 Hz). Frame probablement desserrée — resserrer toute la visserie "
                    f"(bras, top plate, stack, moteurs)."))
    elif structural_peaks >= 2:
        out.append(("🔩", "Visserie du châssis", "warning",
                    f"{structural_peaks} pic(s) de résonance dans la bande structurelle. "
                    f"Vérifier le serrage des vis de la frame."))
    else:
        out.append(("🔩", "Visserie du châssis", "ok",
                    "Aucune résonance structurelle suspecte. Frame saine."))

    # 2. Hélices
    if imb > 80 or prop_peaks >= 3:
        out.append(("🪁", "Hélices", "critical",
                    f"Déséquilibre fort (σ={imb:.0f}) ou {prop_peaks} pics RPM non filtrés. "
                    f"Au moins une hélice est abîmée, déséquilibrée ou mal serrée."))
    elif imb > 50 or prop_peaks >= 1:
        out.append(("🪁", "Hélices", "warning",
                    f"Léger déséquilibre (σ={imb:.0f}). "
                    f"Vérifier l'état visuel et l'équilibrage des hélices."))
    else:
        out.append(("🪁", "Hélices", "ok",
                    f"Hélices bien équilibrées (σ={imb:.0f})."))

    # 3. Roulements moteur
    if imb > 100:
        out.append(("🔧", "Roulements moteur", "critical",
                    f"Déséquilibre extrême (σ={imb:.0f}). Suspicion de roulement HS. "
                    f"Faire tourner chaque moteur à la main : résistance ou cliquetis = à remplacer."))
    elif imb > 60:
        out.append(("🔧", "Roulements moteur", "warning",
                    f"Déséquilibre moteur élevé (σ={imb:.0f}). "
                    f"Tester chaque moteur à la main pour identifier le roulement fatigué."))
    else:
        out.append(("🔧", "Roulements moteur", "ok",
                    "Pas de signe de roulement défectueux."))

    # 4. Condensateur d'alimentation
    if sag > 0.5 and has_low_freq_osc:
        out.append(("⚡", "Condensateur d'alimentation", "critical",
                    f"Sag {sag:.2f} V/cell + oscillations basse fréquence détectées. "
                    f"Condensateur 1 000–2 000 µF / 35 V probablement absent, mort ou sous-dimensionné."))
    elif sag > 0.4:
        out.append(("⚡", "Condensateur d'alimentation", "warning",
                    f"Sag batterie {sag:.2f} V/cell. "
                    f"Vérifier la présence et l'état du condensateur sur les pads batterie ESC."))
    elif sag > 0:
        out.append(("⚡", "Condensateur d'alimentation", "ok",
                    f"Sag batterie normal ({sag:.2f} V/cell). Condensateur efficace."))
    else:
        out.append(("⚡", "Condensateur d'alimentation", "unknown",
                    "Données vbat insuffisantes pour évaluer l'alimentation."))

    # 5. Silentblocs FC
    if avg_hf > 0.12:
        out.append(("🧲", "Montage FC (silentblocs)", "critical",
                    f"Bruit gyro HF élevé ({avg_hf*100:.0f}%). "
                    f"Silentblocs trop durs ou FC en contact direct avec la frame."))
    elif avg_hf > 0.08:
        out.append(("🧲", "Montage FC (silentblocs)", "warning",
                    f"Bruit gyro HF modéré ({avg_hf*100:.0f}%). "
                    f"Envisager des silentblocs plus mous (Shore 30–40 A)."))
    else:
        out.append(("🧲", "Montage FC (silentblocs)", "ok",
                    f"Bruit HF gyro dans la norme ({avg_hf*100:.0f}%). FC bien isolée."))

    # 6. Connecteur batterie (XT60)
    if sag > 0.7:
        out.append(("🔋", "Connecteur batterie (XT60)", "critical",
                    f"Sag très élevé ({sag:.2f} V/cell). "
                    f"Connecteur XT60 probablement oxydé/brûlé OU batterie en fin de vie."))
    elif sag > 0.5:
        out.append(("🔋", "Connecteur batterie (XT60)", "warning",
                    f"Sag élevé ({sag:.2f} V/cell). Inspecter le XT60 et l'état de la batterie."))
    elif sag > 0:
        out.append(("🔋", "Connecteur batterie (XT60)", "ok",
                    "Connecteur batterie sain."))
    else:
        out.append(("🔋", "Connecteur batterie (XT60)", "unknown",
                    "Données vbat insuffisantes pour évaluer le connecteur."))

    # 7. Récepteur / antennes — non détectable
    out.append(("📡", "Récepteur et antennes", "unknown",
                "Non détectable depuis la blackbox. À vérifier visuellement : "
                "antennes droites, non coincées dans la frame, récepteur fixé."))

    return out


class CheckOKTab(QWidget):
    def __init__(self, report: DiagnosticReport, sa: SessionAnalysis | None,
                 cfg: FlightConfig):
        super().__init__()
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        inner = QWidget()
        layout = QVBoxLayout(inner)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        results = _evaluate_hardware(sa, cfg)

        # Compteurs
        n_crit = sum(1 for _, _, st, _ in results if st == 'critical')
        n_warn = sum(1 for _, _, st, _ in results if st == 'warning')
        n_ok   = sum(1 for _, _, st, _ in results if st == 'ok')

        # Bannière de synthèse
        banner = QFrame()
        if n_crit > 0:
            banner_bg, banner_color = '#2e1010', '#e74c3c'
            banner_title = f"🔴  {n_crit} problème(s) hardware critique(s) détecté(s)"
            banner_text = ("Avant de toucher aux PIDs, traitez les points marqués en rouge — "
                           "ils empêcheront tout réglage stable.")
        elif n_warn > 0:
            banner_bg, banner_color = '#2e2410', '#f39c12'
            banner_title = f"⚠️  {n_warn} point(s) hardware à vérifier"
            banner_text = ("Le drone est peut-être pilotable mais des éléments demandent "
                           "une vérification physique avant ou après le réglage PID.")
        else:
            banner_bg, banner_color = '#1a2e22', '#27ae60'
            banner_title = f"✅  Hardware OK — {n_ok} point(s) validé(s)"
            banner_text = ("Aucun problème mécanique ou électrique détectable depuis cette "
                           "blackbox. Vous pouvez passer aux réglages PID en confiance.")

        banner.setStyleSheet(
            f"QFrame {{ background:{banner_bg}; border-left:4px solid {banner_color}; "
            f"border-radius:4px; padding:8px; }}"
        )
        bl = QVBoxLayout(banner)
        bl.setContentsMargins(8, 6, 8, 6)
        bl.setSpacing(4)
        bl.addWidget(_label(banner_title, bold=True, color=banner_color, size=13))
        bl.addWidget(_label(banner_text, color='#ccc', size=11))
        layout.addWidget(banner)

        layout.addWidget(_label(
            "Diagnostic automatique — déterminé à partir de la blackbox, pas de "
            "l'utilisateur. Les coches reflètent ce que l'analyse a observé.",
            color='#888', size=10
        ))
        layout.addWidget(_separator())

        if not results:
            layout.addWidget(_label(
                "Données d'analyse indisponibles pour le check hardware.",
                color='#888', size=11))
        else:
            for icon, title, status, detail in results:
                layout.addWidget(self._make_item(icon, title, status, detail))

        layout.addStretch()
        scroll.setWidget(inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    @staticmethod
    def _make_item(icon: str, title: str, status: str, detail: str) -> QFrame:
        badge_icon, color, bg, badge_text = _STATUS_BADGE[status]

        frame = QFrame()
        frame.setStyleSheet(
            f"QFrame {{ background:{bg}; border-left:3px solid {color}; "
            f"border-radius:4px; margin:2px 0; }}"
        )
        hl = QHBoxLayout(frame)
        hl.setContentsMargins(10, 8, 10, 8)
        hl.setSpacing(12)

        # Icône statut (gros)
        status_lbl = QLabel(badge_icon)
        status_lbl.setStyleSheet(f"color:{color}; font-size:22px;")
        status_lbl.setFixedWidth(34)
        status_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignTop)
        hl.addWidget(status_lbl)

        # Texte central : titre + détail
        vl = QVBoxLayout()
        vl.setSpacing(2)

        title_row = QHBoxLayout()
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(6)
        title_row.addWidget(_label(f"{icon}  {title}", bold=True, color='#e0e0e0', size=12))
        badge = QLabel(badge_text)
        badge.setStyleSheet(
            f"color:{color}; background:rgba(0,0,0,0.25); border:1px solid {color}; "
            f"border-radius:3px; padding:1px 6px; font-size:9px; font-weight:bold;"
        )
        title_row.addWidget(badge)
        title_row.addStretch()
        vl.addLayout(title_row)

        detail_lbl = _label(detail, color='#aaa', size=10)
        detail_lbl.setWordWrap(True)
        vl.addWidget(detail_lbl)
        hl.addLayout(vl, stretch=1)

        return frame


# ---------------------------------------------------------------------------
# Widget principal de diagnostic (regroupe les 4 onglets)
# ---------------------------------------------------------------------------

class DiagnosticWidget(QWidget):
    def __init__(self, cfg: FlightConfig, report: DiagnosticReport,
                 drone_size: str,
                 flight_type: FlightTypeResult | None = None,
                 sa: SessionAnalysis | None = None):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        tabs = QTabWidget()
        tabs.addTab(ContextTab(cfg, drone_size, flight_type), "📋  Contexte")
        tabs.addTab(RecommendationsTab(report),          "🔍  Diagnostic")
        tabs.addTab(SymptomTab(report),                  "🩺  Symptômes")
        tabs.addTab(CheckOKTab(report, sa, cfg),         "✅  Check OK")
        tabs.addTab(CliDumpTab(report),                  "💻  CLI Dump")

        # Aller directement au diagnostic s'il y a des problèmes
        if report.has_issues():
            tabs.setCurrentIndex(1)
        elif report.matched_symptoms:
            tabs.setCurrentIndex(2)

        layout.addWidget(tabs)
