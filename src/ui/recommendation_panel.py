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

from analysis.analyzer import FlightTypeResult
from analysis.header_parser import FlightConfig
from analysis.recommender import DiagnosticReport, Recommendation, Severity, AXIS_NAME
from analysis.sliders import compute_sliders


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
    """Construit la vue 'Valeurs brutes' : filtres en premier, puis PIDs."""
    inner = QWidget()
    layout = QVBoxLayout(inner)
    layout.setContentsMargins(8, 4, 8, 6)
    layout.setSpacing(2)

    # ===== FILTRES EN PREMIER =====
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
            f"🎛  Filtres — {len(filter_cards)} réglage(s)", bold=True,
            color='#3498db', size=13
        ))
        layout.addWidget(_label(
            "Les filtres sont la base d'un tune propre : vibrations, "
            "bruit HF, résonances.", color='#aaa', size=10))
        for cmd, note in filter_cards:
            layout.addWidget(GenericCard(cmd, note, Severity.INFO))
        layout.addWidget(_separator())
    else:
        layout.addWidget(_label("🎛  Filtres : OK, rien à ajuster.",
                                bold=True, color='#27ae60', size=12))
        layout.addWidget(_separator())

    # ===== PIDS =====
    pid_changes = [r for r in report.recommendations if r.suggested != r.current]
    if pid_changes:
        layout.addWidget(_label(
            f"⚙  PID — {len(pid_changes)} ajustement(s)",
            bold=True, color='#e0e0e0', size=13
        ))
        for reco in pid_changes:
            layout.addWidget(RecoCard(reco))
    else:
        layout.addWidget(_label("⚙  PID : OK, aucun changement nécessaire.",
                                bold=True, color='#27ae60', size=12))

    layout.addStretch()
    return inner


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
        self.stack.addWidget(_build_safety_gate(
            lambda: self.stack.setCurrentIndex(1)
        ))
        self.stack.addWidget(self._build_content_page(report))

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.stack)

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
        back.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        back_row.addWidget(back)
        back_row.addStretch()
        outer.addLayout(back_row)

        # Header summary + warnings : compacté dans un scroll à hauteur limitée
        # pour laisser la zone réglages remonter et prendre plus d'espace.
        header_scroll = QScrollArea()
        header_scroll.setWidgetResizable(True)
        header_scroll.setFrameShape(QFrame.Shape.NoFrame)
        header_scroll.setMaximumHeight(110)   # plafond haut de la zone info
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
        outer.addWidget(header_scroll)

        sub = QTabWidget()
        sub.setStyleSheet("QTabBar::tab { padding: 4px 14px; }")

        scroll_raw = QScrollArea()
        scroll_raw.setWidgetResizable(True)
        scroll_raw.setFrameShape(QFrame.Shape.NoFrame)
        scroll_raw.setWidget(_build_reco_list_raw(report))
        sub.addTab(scroll_raw, "Valeurs brutes")

        scroll_sl = QScrollArea()
        scroll_sl.setWidgetResizable(True)
        scroll_sl.setFrameShape(QFrame.Shape.NoFrame)
        scroll_sl.setWidget(_build_reco_list_sliders(report))
        sub.addTab(scroll_sl, "Sliders PID")

        outer.addWidget(sub)
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
        btn.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        lay.addWidget(btn, alignment=Qt.AlignmentFlag.AlignCenter)
        return w

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
        back.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        top.addWidget(back)

        top.addWidget(_label("Mode :", color='#ccc', size=11))
        self.rb_raw = QRadioButton("Valeurs brutes")
        self.rb_slider = QRadioButton("Sliders PID")
        self.rb_raw.setChecked(True)
        self.rb_raw.setStyleSheet("color:#ddd;")
        self.rb_slider.setStyleSheet("color:#ddd;")
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
                 drone_size: str,
                 flight_type: FlightTypeResult | None = None):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        tabs = QTabWidget()
        tabs.addTab(ContextTab(cfg, drone_size, flight_type), "📋  Contexte")
        tabs.addTab(RecommendationsTab(report),          "🔍  Diagnostic")
        tabs.addTab(SymptomTab(report),                  "🩺  Symptômes")
        tabs.addTab(CliDumpTab(report),                  "💻  CLI Dump")

        # Aller directement au diagnostic s'il y a des problèmes
        if report.has_issues():
            tabs.setCurrentIndex(1)
        elif report.matched_symptoms:
            tabs.setCurrentIndex(2)

        layout.addWidget(tabs)
