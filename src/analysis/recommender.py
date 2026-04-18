"""
Génère des recommandations PID/filtres à partir de l'analyse + profil drone.

Philosophie :
  - On vise la perfection, pas le minimum acceptable.
  - Chaque style de vol a des priorités et des seuils vraiment différents.
  - On propose des ajustements même quand le vol est "passable".
  - P, I, D, FF, D_min, filtres : tout peut être recommandé.
  - Les changements sont bornés par la taille du drone (sécurité).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from analysis.analyzer import AxisAnalysis, SessionAnalysis
from analysis.header_parser import FlightConfig
from analysis.sliders import compute_sliders, dump_sliders_cli


class Severity(str, Enum):
    OK       = "ok"
    INFO     = "info"
    WARNING  = "warning"
    CRITICAL = "critical"


SEVERITY_EMOJI = {
    Severity.OK:       "✅",
    Severity.INFO:     "ℹ️",
    Severity.WARNING:  "⚠️",
    Severity.CRITICAL: "🔴",
}

AXIS_NAME  = ['Roll', 'Pitch', 'Yaw']
AXIS_PARAM = ['roll', 'pitch', 'yaw']


@dataclass
class Recommendation:
    param: str
    current: int
    suggested: int
    severity: Severity
    reason: str
    axis: int = -1

    @property
    def delta_pct(self) -> float:
        if self.current == 0:
            return 0.0
        return (self.suggested - self.current) / self.current * 100.0

    @property
    def label(self) -> str:
        s = SEVERITY_EMOJI.get(self.severity, '')
        if self.current == 0:
            return f"{s} {self.param.upper()} : désactivé → {self.suggested}"
        return (f"{s} {self.param.upper()} : {self.current} → {self.suggested} "
                f"({self.delta_pct:+.0f}%)")

    def to_cli_line(self) -> str:
        if self.current == 0:
            return f"set {self.param} = {self.suggested}    # était désactivé — {self.reason}"
        return (f"set {self.param} = {self.suggested}"
                f"    # était {self.current} ({self.delta_pct:+.0f}%) — {self.reason}")


@dataclass
class DiagnosticReport:
    recommendations: list[Recommendation] = field(default_factory=list)
    summary: list[str]                    = field(default_factory=list)
    warnings: list[str]                   = field(default_factory=list)
    filter_recommendations: list[str]     = field(default_factory=list)
    drone_size: str                        = "5\""
    flying_style: str                      = "Freestyle"
    battery_cells_override: int            = 0
    health_score: int                      = 100
    _cfg: FlightConfig | None              = None

    def has_issues(self) -> bool:
        return any(r.severity in (Severity.WARNING, Severity.CRITICAL)
                   for r in self.recommendations)

    def cli_dump(self) -> str:
        lines = [
            "# ============================================================",
            "# BlackBox Analyzer — Recommandations PID",
            f"# Profil : {self.drone_size}  |  Style : {self.flying_style}",
            f"# Score santé : {self.health_score}/100",
            "# ",
            "# SÉCURITÉ — procédure obligatoire avant chaque modification :",
            "#   1. Volez 30 secondes en douceur",
            "#   2. Posez le drone immédiatement",
            "#   3. Touchez les moteurs à la main",
            "#   4. Si un moteur est > 10°C au-dessus de l'ambiant : STOP,",
            "#      ne volez pas plus, trouvez la cause physique.",
            "#   5. Si les moteurs sont tièdes : volez plus longtemps et",
            "#      faites la BBL suivante.",
            "# Le créateur n'est pas responsable en cas de dommage matériel.",
            "# ============================================================",
            "",
        ]
        changed = [r for r in self.recommendations if r.suggested != r.current]
        if changed:
            lines.append("# --- Réglages PID ---")
            for r in changed:
                lines.append(r.to_cli_line())
            lines.append("")

        if self.filter_recommendations:
            lines.append("# --- Filtres ---")
            lines += self.filter_recommendations
            lines.append("")

        if not changed and not self.filter_recommendations:
            lines.append("# Aucun changement recommandé — score santé proche du maximum.")

        lines += ["", "save"]
        return "\n".join(lines)

    def cli_dump_sliders(self) -> str:
        """Dump alternatif : sliders pour PID, filtres gardés en raw."""
        if self._cfg is None:
            return "# Mode sliders indisponible : config firmware non chargée."
        adj = compute_sliders(self.recommendations, self._cfg, self.filter_recommendations)
        return dump_sliders_cli(adj, self._cfg, self.health_score,
                                self.drone_size, self.flying_style,
                                self.filter_recommendations)


# ---------------------------------------------------------------------------
# Profils drones : plages sûres par taille
# ---------------------------------------------------------------------------

DRONE_PROFILES = {
    # Règle : plus la pale est grande, plus on a besoin de D et moins de P / I.
    # Les gros drones résonnent à plus basse fréquence (moteurs tournent moins vite)
    # → dterm_lpf_min abaissé pour 7"+.
    '3"':  dict(max_delta_pct=45, p_range=(25, 60), d_range=(18, 42),
                i_range=(60, 180), f_range=(60, 180), d_min_ratio_floor=0.40,
                dterm_lpf_min_target=90, dterm_lpf_max_target=160),
    # 5" = référence
    '5"':  dict(max_delta_pct=25, p_range=(38, 78), d_range=(26, 56),
                i_range=(70, 180), f_range=(80, 200), d_min_ratio_floor=0.45,
                dterm_lpf_min_target=90, dterm_lpf_max_target=170),
    # 6" : quasi identique à un 5", juste P/D un peu plus hauts selon config
    '6"':  dict(max_delta_pct=30, p_range=(38, 82), d_range=(28, 58),
                i_range=(70, 175), f_range=(80, 200), d_min_ratio_floor=0.45,
                dterm_lpf_min_target=85, dterm_lpf_max_target=160),
    # 7" : moins de P, moins de I, plus de D. Résonances basses → LPF serré bas.
    '7"':  dict(max_delta_pct=45, p_range=(32, 70), d_range=(32, 65),
                i_range=(60, 160), f_range=(80, 200), d_min_ratio_floor=0.50,
                dterm_lpf_min_target=75, dterm_lpf_max_target=120),
    # 10" : encore plus radical côté P/I bas, D haut, filtres très serrés.
    '10"': dict(max_delta_pct=55, p_range=(22, 55), d_range=(30, 60),
                i_range=(50, 140), f_range=(60, 180), d_min_ratio_floor=0.45,
                dterm_lpf_min_target=60, dterm_lpf_max_target=100),
}
DEFAULT_PROFILE = DRONE_PROFILES['5"']


# ---------------------------------------------------------------------------
# Cibles par style — exigences pour un tune "parfait"
# ---------------------------------------------------------------------------
# Les cibles (_target) définissent l'idéal à atteindre.
# Les _critical sont le seuil où la correction devient prioritaire.

STYLE_TARGETS = {
    # lag_target_ms = délai gyro vs setpoint (ce que corrige le FF).
    # rise_target_ms = temps pour atteindre 90% (limité par physique moteur).
    # Freestyle : drone hyper loqué, FF haut, D ≈ D_min (consensus moderne
    # Blackbird NextLevel / UAV Tech : D=D_min=37, i_roll=120, P=66, dterm 127/257).
    'Freestyle': dict(
        osc_target=0.09,        osc_critical=0.20,
        drift_target=0.08,      drift_critical=0.20,
        propwash_target=0.09,   propwash_critical=0.20,
        rise_target_ms=26,      rise_critical_ms=50,
        overshoot_target=10,    overshoot_critical=22,
        noise_target=2.3,       noise_critical=3.8,
        hf_noise_target=0.06,   hf_noise_critical=0.18,
        lag_target_ms=4,        lag_critical_ms=10,
        d_min_ratio=0.90,        # Blackbird : D_min = D ; consensus 2024 avec RPM filter propre
        prefer_high_ff=True,
        prefer_high_d=True,
    ),
    # Racing : presets ctzsnooze/MinChan — P/D bas (P~42, D~35), I et FF hauts,
    # D_min/D 0.55-0.70 (headroom pour boost D en virage serré).
    'Racing': dict(
        osc_target=0.07,        osc_critical=0.16,
        drift_target=0.14,      drift_critical=0.28,
        propwash_target=0.14,   propwash_critical=0.28,
        rise_target_ms=20,      rise_critical_ms=42,
        overshoot_target=7,     overshoot_critical=16,
        noise_target=3.5,       noise_critical=5.8,
        hf_noise_target=0.18,   hf_noise_critical=0.32,
        lag_target_ms=2,        lag_critical_ms=6,
        d_min_ratio=0.65,        # MinChan 0.54 / ctzsnooze 0.71 → milieu
        prefer_high_ff=True,
        prefer_high_d=False,
    ),
    # Long Range (UAV Tech 6-7") : master 150, pi_gain 85 (PI bas),
    # d_gain 130 (D haut pour masse), ff_gain 115, gyro_filter_mult 40-60.
    'Long Range': dict(
        osc_target=0.10,        osc_critical=0.20,
        drift_target=0.05,      drift_critical=0.12,
        propwash_target=0.25,   propwash_critical=0.45,
        rise_target_ms=70,      rise_critical_ms=120,
        overshoot_target=22,    overshoot_critical=38,
        noise_target=1.8,       noise_critical=2.8,
        hf_noise_target=0.04,   hf_noise_critical=0.12,
        lag_target_ms=18,       lag_critical_ms=35,
        d_min_ratio=0.50,
        prefer_high_ff=False,
        prefer_high_d=False,
        prefer_high_i=True,
    ),
    'Bangers': dict(
        osc_target=0.22,        osc_critical=0.45,
        drift_target=0.28,      drift_critical=0.50,
        propwash_target=0.28,   propwash_critical=0.50,
        rise_target_ms=55,      rise_critical_ms=120,
        overshoot_target=30,    overshoot_critical=50,
        noise_target=5.0,       noise_critical=8.5,
        hf_noise_target=0.25,   hf_noise_critical=0.40,
        lag_target_ms=12,       lag_critical_ms=25,
        d_min_ratio=0.35,
        prefer_high_ff=False,
        prefer_high_d=False,
    ),
}
DEFAULT_STYLE = STYLE_TARGETS['Freestyle']


# ---------------------------------------------------------------------------
# Ressenti du pilote — 4 sliders 1..5 pour capter le feel sans IA.
# 3 = neutre (on respecte les cibles du style). 1-2 ou 4-5 = on pousse dans
# une direction. Ces biais modifient les cibles du style AVANT analyse.
# ---------------------------------------------------------------------------

@dataclass
class FlightFeel:
    locked: int = 3          # 1=flottant souhaité, 5=ultra-locké demandé
    wind_stability: int = 3  # 1=peu important, 5=doit être imperturbable au vent
    responsiveness: int = 3  # 1=doux, 5=stick ultra vif
    propwash_clean: int = 3  # 1=accepte prop wash, 5=doit être impeccable

    @staticmethod
    def neutral() -> 'FlightFeel':
        return FlightFeel()

    def is_neutral(self) -> bool:
        return (self.locked == 3 and self.wind_stability == 3
                and self.responsiveness == 3 and self.propwash_clean == 3)

    def describe(self) -> list[str]:
        """Retourne les directions non-neutres pour affichage."""
        out = []
        for val, neg, pos in [
            (self.locked,          "drone plus libre",      "drone plus locké"),
            (self.wind_stability,  "peu importe le vent",   "imperturbable au vent"),
            (self.responsiveness,  "réponse plus douce",    "réponse plus vive"),
            (self.propwash_clean,  "prop wash toléré",      "post-manœuvre impeccable"),
        ]:
            d = val - 3
            if d > 0:
                out.append(f"+{d}  {pos}")
            elif d < 0:
                out.append(f"{d}  {neg}")
        return out


def _apply_feel(style: dict, feel: FlightFeel) -> dict:
    """Retourne une copie de `style` avec cibles déplacées selon le ressenti."""
    s = dict(style)
    if feel.is_neutral():
        return s

    # 1. Locké : plus locké = lag plus serré, FF plus agressif, D_min plus haut
    d = feel.locked - 3
    if d != 0:
        s['lag_target_ms'] = max(1.0, s['lag_target_ms'] - d * 1.8)
        s['overshoot_target'] = max(4, s['overshoot_target'] - d * 1.5)
        s['d_min_ratio'] = max(0.25, min(1.0, s['d_min_ratio'] + d * 0.05))
        if d > 0:
            s['prefer_high_ff'] = True
            s['prefer_high_d'] = True

    # 2. Stabilité au vent : pousse I et resserre dérive
    d = feel.wind_stability - 3
    if d > 0:
        s['drift_target']   = max(0.03, s['drift_target']   - d * 0.02)
        s['drift_critical'] = max(0.06, s['drift_critical'] - d * 0.03)
        s['prefer_high_i']  = True

    # 3. Réactivité : resserre rise_target, tolère plus d'overshoot
    d = feel.responsiveness - 3
    if d != 0:
        s['rise_target_ms']     = max(14, s['rise_target_ms']     - d * 5)
        s['rise_critical_ms']   = max(30, s['rise_critical_ms']   - d * 8)
        if d > 0:
            s['overshoot_target']  = s['overshoot_target']  + 2
            s['overshoot_critical'] = s['overshoot_critical'] + 3

    # 4. Prop wash : resserre propwash + monte d_min_ratio
    d = feel.propwash_clean - 3
    if d != 0:
        s['propwash_target']   = max(0.04, s['propwash_target']   - d * 0.03)
        s['propwash_critical'] = max(0.08, s['propwash_critical'] - d * 0.04)
        s['d_min_ratio']       = max(0.25, min(1.0, s['d_min_ratio'] + d * 0.04))

    return s


# ---------------------------------------------------------------------------
# Ancres de sliders Simplified Tune — valeurs des presets officiels BF 4.5
# (repo betaflight/firmware-presets). Utilisées comme référence d'affichage
# et comme cible douce si les sliders actuels du pilote sont très différents.
# Format : (master, pi_gain, i_gain, d_gain, dmax_gain, ff_gain, pitch_pi,
#           dterm_mult, gyro_mult)
# ---------------------------------------------------------------------------

SLIDER_REFERENCE = {
    # 3" Cinewhoop (UAV Tech) : filtrage max, D haut, master haut.
    ('3"',  'Freestyle'):  dict(master=160, pi=100, i=100, d=140, dmax=100,
                                 ff=100, pitch_pi=100, dterm_mult=120, gyro_mult=60),
    ('3"',  'Long Range'): dict(master=150, pi=95,  i=90,  d=130, dmax=90,
                                 ff=100, pitch_pi=100, dterm_mult=110, gyro_mult=60),
    # 5" Freestyle : UAV Tech 575-650g / fpvian basher.
    ('5"',  'Freestyle'):  dict(master=125, pi=110, i=105, d=100, dmax=80,
                                 ff=135, pitch_pi=100, dterm_mult=120, gyro_mult=130),
    ('5"',  'Racing'):     dict(master=100, pi=110, i=110, d=100, dmax=100,
                                 ff=130, pitch_pi=100, dterm_mult=120, gyro_mult=120),
    ('5"',  'Long Range'): dict(master=130, pi=90,  i=85,  d=115, dmax=90,
                                 ff=110, pitch_pi=100, dterm_mult=100, gyro_mult=80),
    ('5"',  'Bangers'):    dict(master=115, pi=100, i=100, d=100, dmax=100,
                                 ff=120, pitch_pi=100, dterm_mult=130, gyro_mult=150),
    # 6-7" : UAV Tech LR → master 150, PI bas, D haut, filtres serrés.
    ('6"',  'Freestyle'):  dict(master=140, pi=100, i=95,  d=120, dmax=90,
                                 ff=130, pitch_pi=100, dterm_mult=110, gyro_mult=100),
    ('6"',  'Long Range'): dict(master=150, pi=85,  i=80,  d=130, dmax=90,
                                 ff=115, pitch_pi=100, dterm_mult=100, gyro_mult=60),
    ('6"',  'Racing'):     dict(master=110, pi=105, i=105, d=110, dmax=100,
                                 ff=125, pitch_pi=100, dterm_mult=110, gyro_mult=100),
    ('7"',  'Freestyle'):  dict(master=145, pi=95,  i=90,  d=130, dmax=90,
                                 ff=125, pitch_pi=100, dterm_mult=90,  gyro_mult=70),
    ('7"',  'Long Range'): dict(master=150, pi=85,  i=75,  d=135, dmax=85,
                                 ff=110, pitch_pi=100, dterm_mult=80,  gyro_mult=50),
    # 10" : extrapolé (preset UAV_tech_10in non récupéré — valeurs max de la tendance).
    ('10"', 'Long Range'): dict(master=155, pi=80,  i=70,  d=140, dmax=80,
                                 ff=105, pitch_pi=100, dterm_mult=70,  gyro_mult=45),
    ('10"', 'Freestyle'):  dict(master=150, pi=90,  i=85,  d=135, dmax=85,
                                 ff=115, pitch_pi=100, dterm_mult=75,  gyro_mult=50),
}


def get_slider_reference(drone_size: str, flying_style: str) -> dict | None:
    """Retourne les valeurs slider de référence pour le combo, ou None."""
    ref = SLIDER_REFERENCE.get((drone_size, flying_style))
    if ref is not None:
        return ref
    # Fallback : même taille, style Freestyle ; puis 5" du style demandé.
    return (SLIDER_REFERENCE.get((drone_size, 'Freestyle'))
            or SLIDER_REFERENCE.get(('5"', flying_style))
            or SLIDER_REFERENCE.get(('5"', 'Freestyle')))


# ---------------------------------------------------------------------------
# Score santé (0-100)
# ---------------------------------------------------------------------------

def compute_health_score(session: SessionAnalysis,
                         style: dict = DEFAULT_STYLE) -> int:
    score = 100.0
    for aa in session.axes:
        # Oscillations
        if aa.oscillation_score > style['osc_target']:
            over = aa.oscillation_score - style['osc_target']
            score -= min(18, over * 80)
        # Drift
        if aa.drift_score > style['drift_target']:
            over = aa.drift_score - style['drift_target']
            score -= min(12, over * 50)
        # Prop wash
        if aa.propwash_score > style['propwash_target']:
            over = aa.propwash_score - style['propwash_target']
            score -= min(12, over * 45)
        # Bruit
        if aa.noise_ratio > style['noise_target']:
            over = aa.noise_ratio - style['noise_target']
            score -= min(12, over * 4)
        # Réponse trop lente
        if aa.avg_rise_time_ms > style['rise_target_ms'] and aa.step_count >= 2:
            over_ms = aa.avg_rise_time_ms - style['rise_target_ms']
            score -= min(8, over_ms / 12)
        # Overshoot
        if aa.avg_overshoot_pct > style['overshoot_target'] and aa.step_count >= 2:
            over = aa.avg_overshoot_pct - style['overshoot_target']
            score -= min(6, over / 6)
        # Lag FF
        if aa.tracking_lag_ms > style['lag_target_ms'] and aa.step_count >= 2:
            over = aa.tracking_lag_ms - style['lag_target_ms']
            score -= min(5, over / 6)
        # Vibrations non filtrées
        unfiltered = sum(1 for p in aa.vibration_peaks
                         if not p.covered_by_rpm_filter and p.power_db > 0)
        score -= min(10, unfiltered * 1.8)
    return int(max(0, min(100, round(score))))


# ---------------------------------------------------------------------------
# Génération du rapport
# ---------------------------------------------------------------------------

def generate_report(session: SessionAnalysis, cfg: FlightConfig,
                    drone_size: str = '5"',
                    flying_style: str = 'Freestyle',
                    battery_cells_override: int = 0,
                    feel: FlightFeel | None = None) -> DiagnosticReport:
    report = DiagnosticReport(
        drone_size=drone_size,
        flying_style=flying_style,
        battery_cells_override=battery_cells_override,
        _cfg=cfg,
    )
    report.warnings = list(session.warnings)

    profile = DRONE_PROFILES.get(drone_size, DEFAULT_PROFILE)
    base_style = STYLE_TARGETS.get(flying_style, DEFAULT_STYLE)
    style = _apply_feel(base_style, feel or FlightFeel.neutral())

    # Trace ce que le ressenti a changé
    if feel and not feel.is_neutral():
        report.summary.append("Ressenti pilote : " + " · ".join(feel.describe()))

    # Contexte
    cells = battery_cells_override or session.cell_count
    if cells:
        v = session.battery_voltage
        report.summary.append(f"Batterie : {cells}S  ({v:.2f}V moy.)")
        if battery_cells_override and session.cell_count and \
           battery_cells_override != session.cell_count:
            report.warnings.append(
                f"Tension BBL correspond à {session.cell_count}S, "
                f"profil sélectionné : {battery_cells_override}S. "
                "Recommandations calculées pour la sélection manuelle."
            )
    if session.fly_duration_s > 0:
        report.summary.append(f"Durée de vol analysée : {session.fly_duration_s:.1f}s")
    if session.sample_rate_hz > 0:
        report.summary.append(f"Échantillonnage : {session.sample_rate_hz:.0f}Hz")
    if cfg.board:
        report.summary.append(f"FC : {cfg.board}")
    report.summary.append(f"Style : {flying_style} — cibles exigentes appliquées.")
    if flying_style == 'Bangers':
        report.summary.append(
            "Bangers : tolérance relâchée — on privilégie la survie du drone "
            "(pale abîmée, crash probable) sur la perfection."
        )
    if cfg.simplified_mode > 0:
        report.warnings.append(
            "Mode PID simplifié actif. Désactivez-le pour appliquer ces recommandations."
        )
    if cfg.dshot_bidir and cfg.rpm_filter_harmonics > 0:
        report.summary.append(
            f"Filtre RPM actif ({cfg.rpm_filter_harmonics} harmoniques)."
        )
    else:
        report.warnings.append(
            "Bidirectionnel DSHOT inactif : le filtre RPM ne peut pas fonctionner. "
            "À activer en priorité dans Betaflight (onglet Motors)."
        )

    # Analyse détaillée par axe
    for aa in session.axes:
        _check_axis(aa, cfg, report, profile, style)

    _check_vibrations(session, cfg, report, flying_style)
    _check_filters_global(session, cfg, report, style, profile)

    # Motor imbalance
    imb = session.axes[0].motor_imbalance if session.axes else 0
    if imb > 80:
        report.warnings.append(
            f"Déséquilibre moteur détecté (σ={imb:.0f} DSHOT). "
            "Vérifiez hélices et moteurs avant de régler les PIDs."
        )

    report.health_score = compute_health_score(session, style)

    if not report.recommendations and not report.filter_recommendations:
        report.summary.append(
            f"Aucun axe ne dépasse les cibles du style {flying_style}. "
            f"Score {report.health_score}/100 — très bon."
        )

    return report


# ---------------------------------------------------------------------------
# Analyse par axe — beaucoup plus fine
# ---------------------------------------------------------------------------

def _check_axis(aa: AxisAnalysis, cfg: FlightConfig, report: DiagnosticReport,
                profile: dict, style: dict):
    ax = aa.axis
    name = aa.name
    p_cur = cfg.pid_p[ax]
    i_cur = cfg.pid_i[ax]
    d_cur = cfg.pid_d[ax]
    f_cur = cfg.pid_f[ax] if ax < len(cfg.pid_f) else 0
    dm_cur = cfg.d_min[ax] if ax < len(cfg.d_min) else 0

    max_delta = profile['max_delta_pct'] / 100.0
    p_range = profile['p_range']
    d_range = profile['d_range']
    f_range = profile['f_range']
    i_range = profile['i_range']

    # ===== 1. Oscillations (P trop haut) =====
    if aa.oscillation_score > style['osc_target'] and p_cur > 0:
        over = aa.oscillation_score - style['osc_target']
        sev = Severity.WARNING if aa.oscillation_score > style['osc_critical'] else Severity.INFO
        # Réduction proportionnelle à la sévérité
        reduction = min(0.15, over * 0.6)
        if sev == Severity.WARNING:
            reduction = max(reduction, 0.08)
        p_new = _clamp_change(p_cur, -reduction, max_delta, p_range)
        if p_new != p_cur:
            report.recommendations.append(Recommendation(
                param=f"p_{AXIS_PARAM[ax]}", current=p_cur, suggested=p_new,
                severity=sev, axis=ax,
                reason=(f"oscillation {aa.dominant_freq_hz:.0f}Hz, "
                        f"score {aa.oscillation_score:.2f} > cible {style['osc_target']:.2f}")
            ))
        # Si oscillation HF → abaisser dterm_lpf1 aussi
        if aa.dominant_freq_hz > 250 and cfg.dterm_lpf1_dyn_max_hz > 150:
            new_cutoff = max(100, int(cfg.dterm_lpf1_dyn_max_hz * 0.85))
            report.filter_recommendations.append(
                f"set dterm_lpf1_dyn_max_hz = {new_cutoff}    "
                f"# était {cfg.dterm_lpf1_dyn_max_hz} — oscillation D-term haute"
            )

    # ===== 2. Drift ligne droite (I trop bas OU P trop haut) =====
    if aa.drift_score > style['drift_target']:
        over = aa.drift_score - style['drift_target']
        sev = Severity.WARNING if aa.drift_score > style['drift_critical'] else Severity.INFO

        # Si oscillation déjà détectée → baisser P en priorité
        if aa.has_oscillation and aa.oscillation_score > style['osc_target']:
            # déjà traité plus haut
            pass
        else:
            # Remonter I (typique : oscillation gauche/droite en ligne droite)
            if i_cur > 0:
                boost = min(0.15, over * 0.5)
                if sev == Severity.WARNING:
                    boost = max(boost, 0.10)
                i_new = _clamp_change(i_cur, +boost, max_delta, i_range)
                if i_new != i_cur:
                    report.recommendations.append(Recommendation(
                        param=f"i_{AXIS_PARAM[ax]}", current=i_cur, suggested=i_new,
                        severity=sev, axis=ax,
                        reason=(f"oscillation {aa.drift_freq_hz:.0f}Hz en ligne droite "
                                f"— I insuffisant pour tenir la trajectoire")
                    ))
            # Si iterm_relax_cutoff trop bas → le remonter aussi pour corriger plus fort en calme
            if cfg.iterm_windup < 100:
                pass  # skip : configure dans Betaflight

    # ===== 3. Prop wash (D_min trop bas OU filtres trop lâches) =====
    if aa.propwash_score > style['propwash_target'] and ax < 2:
        over = aa.propwash_score - style['propwash_target']
        sev = Severity.WARNING if aa.propwash_score > style['propwash_critical'] else Severity.INFO
        # Augmenter D_min (ratio cible défini par style)
        target_dm = int(d_cur * style['d_min_ratio'])
        if dm_cur < target_dm and d_cur > 0:
            suggested_dm = min(d_cur, dm_cur + max(2, int((target_dm - dm_cur) * 0.7)))
            if suggested_dm > dm_cur:
                report.recommendations.append(Recommendation(
                    param=f"d_min_{AXIS_PARAM[ax]}", current=dm_cur, suggested=suggested_dm,
                    severity=sev, axis=ax,
                    reason=(f"prop wash détecté (score {aa.propwash_score:.2f}) "
                            f"— D_min plus haut = meilleure récupération")
                ))
        # Si D lui-même est bas → suggérer de le monter légèrement
        elif d_cur > 0 and d_cur < d_range[1] * 0.85 and aa.noise_ratio < style['noise_critical']:
            d_new = _clamp_change(d_cur, +0.08, max_delta, d_range)
            if d_new > d_cur:
                report.recommendations.append(Recommendation(
                    param=f"d_{AXIS_PARAM[ax]}", current=d_cur, suggested=d_new,
                    severity=Severity.INFO, axis=ax,
                    reason=(f"prop wash et bruit D acceptable — "
                            f"plus de D pour amortir les oscillations")
                ))

    # ===== 4. Bruit D excessif (D trop haut OU filtres trop ouverts) =====
    if aa.d_noise_rms > 0 and d_cur > 0 and ax < 2:
        noise_ratio = aa.d_noise_rms / (aa.gyro_noise_rms + 1e-6)
        if noise_ratio > style['noise_target']:
            sev = Severity.WARNING if noise_ratio > style['noise_critical'] else Severity.INFO
            reduction = 0.08 if sev == Severity.INFO else 0.12
            d_new = _clamp_change(d_cur, -reduction, max_delta, d_range)
            if d_new != d_cur:
                report.recommendations.append(Recommendation(
                    param=f"d_{AXIS_PARAM[ax]}", current=d_cur, suggested=d_new,
                    severity=sev, axis=ax,
                    reason=(f"bruit D {noise_ratio:.1f}x > cible {style['noise_target']:.1f}x "
                            f"— risque de chauffe moteur")
                ))

    # ===== 5. Réponse trop lente (P ou FF trop bas) =====
    if aa.avg_rise_time_ms > style['rise_target_ms'] and aa.step_count >= 2:
        sev = Severity.WARNING if aa.avg_rise_time_ms > style['rise_critical_ms'] else Severity.INFO

        # Lag FF significatif → augmenter FF
        if aa.tracking_lag_ms > style['lag_target_ms'] and f_cur > 0:
            boost = 0.12 if sev == Severity.INFO else 0.18
            f_new = _clamp_change(f_cur, +boost, max_delta, f_range)
            if f_new != f_cur:
                report.recommendations.append(Recommendation(
                    param=f"f_{AXIS_PARAM[ax]}", current=f_cur, suggested=f_new,
                    severity=sev, axis=ax,
                    reason=(f"lag gyro {aa.tracking_lag_ms:.0f}ms, "
                            f"rise {aa.avg_rise_time_ms:.0f}ms > {style['rise_target_ms']}ms "
                            f"— FF insuffisant")
                ))
        # Sinon augmenter P (si pas d'oscillation)
        elif p_cur > 0 and not aa.has_oscillation:
            boost = 0.10 if sev == Severity.INFO else 0.15
            p_new = _clamp_change(p_cur, +boost, max_delta, p_range)
            if p_new != p_cur:
                report.recommendations.append(Recommendation(
                    param=f"p_{AXIS_PARAM[ax]}", current=p_cur, suggested=p_new,
                    severity=sev, axis=ax,
                    reason=(f"réponse lente ({aa.avg_rise_time_ms:.0f}ms > "
                            f"{style['rise_target_ms']}ms) — P trop bas")
                ))

    # ===== 6. Overshoot (P trop haut OU D trop bas) =====
    if aa.avg_overshoot_pct > style['overshoot_target'] and aa.step_count >= 2:
        sev = Severity.WARNING if aa.avg_overshoot_pct > style['overshoot_critical'] else Severity.INFO
        # Si D semble bas pour le P → augmenter D
        if d_cur > 0 and ax < 2 and (aa.d_noise_rms / (aa.gyro_noise_rms + 1e-6)) < style['noise_target'] * 0.9:
            boost = 0.08
            d_new = _clamp_change(d_cur, +boost, max_delta, d_range)
            if d_new != d_cur:
                report.recommendations.append(Recommendation(
                    param=f"d_{AXIS_PARAM[ax]}", current=d_cur, suggested=d_new,
                    severity=sev, axis=ax,
                    reason=(f"overshoot {aa.avg_overshoot_pct:.0f}% > {style['overshoot_target']}% "
                            f"et bruit D faible — plus de D pour amortir")
                ))
        elif p_cur > 0 and not aa.has_oscillation:
            reduction = 0.06 if sev == Severity.INFO else 0.10
            p_new = _clamp_change(p_cur, -reduction, max_delta, p_range)
            if p_new != p_cur:
                report.recommendations.append(Recommendation(
                    param=f"p_{AXIS_PARAM[ax]}", current=p_cur, suggested=p_new,
                    severity=sev, axis=ax,
                    reason=(f"overshoot {aa.avg_overshoot_pct:.0f}% > {style['overshoot_target']}% "
                            f"— P un peu trop haut")
                ))

    # ===== 7. FF trop haut (overshoot + lag faible = drone "sursauteur") =====
    if (aa.avg_overshoot_pct > style['overshoot_target'] * 1.3
            and aa.tracking_lag_ms < style['lag_target_ms'] * 0.6
            and aa.step_count >= 2
            and f_cur > f_range[0] * 1.2):
        reduction = 0.08
        f_new = _clamp_change(f_cur, -reduction, max_delta, f_range)
        if f_new < f_cur:
            report.recommendations.append(Recommendation(
                param=f"f_{AXIS_PARAM[ax]}", current=f_cur, suggested=f_new,
                severity=Severity.INFO, axis=ax,
                reason=(f"overshoot {aa.avg_overshoot_pct:.0f}% avec lag faible "
                        f"({aa.tracking_lag_ms:.0f}ms) — FF trop anticipatif")
            ))

    # ===== 8. I trop haut (overshoot sans drift et P OK) =====
    if (aa.avg_overshoot_pct > style['overshoot_critical']
            and aa.step_count >= 3
            and aa.drift_score < style['drift_target'] * 0.7
            and not aa.has_oscillation
            and i_cur > i_range[0] * 1.3):
        reduction = 0.08
        i_new = _clamp_change(i_cur, -reduction, max_delta, i_range)
        if i_new < i_cur:
            report.recommendations.append(Recommendation(
                param=f"i_{AXIS_PARAM[ax]}", current=i_cur, suggested=i_new,
                severity=Severity.INFO, axis=ax,
                reason=(f"overshoot {aa.avg_overshoot_pct:.0f}% sans drift "
                        f"— I peut être trop agressif")
            ))

    # ===== 10. Biais selon le style (pousse activement dans la bonne direction) =====
    # Freestyle/Racing : FF haut → drone "locked", suit le stick au millimètre
    if style.get('prefer_high_ff') and f_cur > 0 and aa.step_count >= 2:
        ff_target = int(f_range[1] * 0.85)
        # Si FF bien sous la cible, ET pas d'overshoot excessif, pousser le FF
        if (f_cur < ff_target and
                aa.avg_overshoot_pct < style['overshoot_target'] * 1.2):
            # Pas déjà suggéré ailleurs ?
            already = any(r.param == f"f_{AXIS_PARAM[ax]}" and r.suggested != r.current
                          for r in report.recommendations)
            if not already:
                boost = 0.10
                f_new = _clamp_change(f_cur, +boost, max_delta, f_range)
                if f_new > f_cur:
                    report.recommendations.append(Recommendation(
                        param=f"f_{AXIS_PARAM[ax]}", current=f_cur, suggested=f_new,
                        severity=Severity.INFO, axis=ax,
                        reason=(f"{report.flying_style} : drone doit être 'locked' — "
                                f"FF peut monter (actuel {f_cur}, cible ~{ff_target})")
                    ))

    # Long Range : FF bas (souple, peu sensible au vent), I haut (tient trajectoire)
    if style.get('prefer_high_ff') is False and f_cur > 0 and aa.step_count >= 2:
        ff_max = int(f_range[0] * 1.3)
        if f_cur > ff_max and aa.avg_overshoot_pct > style['overshoot_target'] * 0.8:
            already = any(r.param == f"f_{AXIS_PARAM[ax]}" and r.suggested != r.current
                          for r in report.recommendations)
            if not already:
                f_new = _clamp_change(f_cur, -0.12, max_delta, f_range)
                if f_new < f_cur:
                    report.recommendations.append(Recommendation(
                        param=f"f_{AXIS_PARAM[ax]}", current=f_cur, suggested=f_new,
                        severity=Severity.INFO, axis=ax,
                        reason=(f"{report.flying_style} : FF doux pour stabilité — "
                                f"moins sensible au vent et aux changements d'altitude")
                    ))

    if style.get('prefer_high_i') and i_cur > 0:
        i_min_target = int(i_range[1] * 0.75)
        if i_cur < i_min_target and aa.drift_score > style['drift_target'] * 0.5:
            already = any(r.param == f"i_{AXIS_PARAM[ax]}" and r.suggested != r.current
                          for r in report.recommendations)
            if not already:
                i_new = _clamp_change(i_cur, +0.10, max_delta, i_range)
                if i_new > i_cur:
                    report.recommendations.append(Recommendation(
                        param=f"i_{AXIS_PARAM[ax]}", current=i_cur, suggested=i_new,
                        severity=Severity.INFO, axis=ax,
                        reason=(f"{report.flying_style} : I plus haut pour tenir "
                                f"la trajectoire sur la durée")
                    ))

    # ===== 9. Valeurs hors plages (avertissement seul) =====
    if p_cur > 0 and not (p_range[0] <= p_cur <= p_range[1]):
        direction = "trop haut" if p_cur > p_range[1] else "trop bas"
        report.warnings.append(
            f"P {name} = {p_cur} ({direction} pour {report.drone_size}, "
            f"plage habituelle {p_range[0]}–{p_range[1]})"
        )
    if d_cur > 0 and ax < 2 and not (d_range[0] <= d_cur <= d_range[1]):
        direction = "trop haut" if d_cur > d_range[1] else "trop bas"
        report.warnings.append(
            f"D {name} = {d_cur} ({direction} pour {report.drone_size}, "
            f"plage habituelle {d_range[0]}–{d_range[1]})"
        )


# ---------------------------------------------------------------------------
# Filtres globaux
# ---------------------------------------------------------------------------

def _check_filters_global(session: SessionAnalysis, cfg: FlightConfig,
                          report: DiagnosticReport, style: dict,
                          profile: dict = DEFAULT_PROFILE):
    # Cibles D-term LPF par taille (gros drone = résonances basses = LPF serré bas)
    dterm_min_target = profile.get('dterm_lpf_min_target', 90)
    dterm_max_target = profile.get('dterm_lpf_max_target', 170)

    # 1. Cible structurelle selon la taille de drone — appliquée même sans bruit anormal.
    #    Ex : un 7" doit tourner autour de 75/120, pas 90/170.
    cur_min = cfg.dterm_lpf1_dyn_min_hz
    cur_max = cfg.dterm_lpf1_dyn_max_hz
    if cur_min > 0 and abs(cur_min - dterm_min_target) > max(10, dterm_min_target * 0.12):
        report.filter_recommendations.append(
            f"set dterm_lpf1_dyn_min_hz = {dterm_min_target}    "
            f"# était {cur_min} — cible taille {report.drone_size} "
            f"(résonances moteurs plus basses sur gros props)"
        )
    if cur_max > 0 and abs(cur_max - dterm_max_target) > max(15, dterm_max_target * 0.12):
        report.filter_recommendations.append(
            f"set dterm_lpf1_dyn_max_hz = {dterm_max_target}    "
            f"# était {cur_max} — cible taille {report.drone_size}"
        )

    # 2. Correction fine selon le bruit HF mesuré (surcharge la cible structurelle si pic).
    hf_vals = [aa.hf_noise_ratio for aa in session.axes[:2] if aa.hf_noise_ratio > 0]
    if not hf_vals:
        return
    avg_hf = sum(hf_vals) / len(hf_vals)

    if avg_hf > style['hf_noise_critical']:
        # Bruit HF élevé → serrer dterm_lpf1 en-deçà de la cible structurelle
        cur = cfg.dterm_lpf1_dyn_max_hz or cfg.dterm_lpf1_hz
        if cur > 0:
            new = max(int(dterm_max_target * 0.85), int(cur * 0.82))
            if new < cur:
                report.filter_recommendations.append(
                    f"set dterm_lpf1_dyn_max_hz = {new}    "
                    f"# était {cur} — bruit HF élevé ({avg_hf*100:.0f}% > {style['hf_noise_critical']*100:.0f}%)"
                )
    elif avg_hf < style['hf_noise_target'] * 0.6 and session.axes[0].avg_rise_time_ms > style['rise_target_ms']:
        # Peu de bruit + réponse lente → ouvrir les filtres (sans dépasser largement la cible)
        cur = cfg.dterm_lpf1_dyn_max_hz or cfg.dterm_lpf1_hz
        if 0 < cur < dterm_max_target * 1.1:
            new = min(int(dterm_max_target * 1.2), int(cur * 1.15))
            if new > cur:
                report.filter_recommendations.append(
                    f"set dterm_lpf1_dyn_max_hz = {new}    "
                    f"# était {cur} — peu de bruit HF, plus de bande passante possible"
                )

    # Gyro LPF : si bruit raw très élevé → filtre gyro trop ouvert
    noise_ratios = [aa.noise_ratio for aa in session.axes[:2] if aa.noise_ratio > 0]
    if noise_ratios:
        max_noise = max(noise_ratios)
        if max_noise > style['noise_critical'] * 1.5 and cfg.gyro_lpf1_hz > 200:
            new_gyro = max(150, int(cfg.gyro_lpf1_hz * 0.85))
            report.filter_recommendations.append(
                f"set gyro_lpf1_static_hz = {new_gyro}    "
                f"# était {cfg.gyro_lpf1_hz} — bruit gyro brut très élevé ({max_noise:.1f}x)"
            )
        elif max_noise < style['noise_target'] * 0.5 and 0 < cfg.gyro_lpf1_hz < 400:
            new_gyro = min(500, int(cfg.gyro_lpf1_hz * 1.15))
            report.filter_recommendations.append(
                f"set gyro_lpf1_static_hz = {new_gyro}    "
                f"# était {cfg.gyro_lpf1_hz} — très peu de bruit gyro, plus de réactivité possible"
            )


# ---------------------------------------------------------------------------
# Vibrations mécaniques + filtres notch
# ---------------------------------------------------------------------------

def _check_vibrations(session: SessionAnalysis, cfg: FlightConfig,
                      report: DiagnosticReport, flying_style: str):
    all_unfiltered: list[tuple[str, float, float]] = []
    for aa in session.axes:
        bad = [p for p in aa.vibration_peaks
               if not p.covered_by_rpm_filter and p.power_db > 0]
        for p in bad:
            all_unfiltered.append((aa.name, p.freq_hz, p.power_db))

    if not all_unfiltered:
        return

    n_peaks = len(all_unfiltered)
    if n_peaks >= 4:
        if flying_style == 'Bangers':
            report.warnings.append(
                f"{n_peaks} pics de vibration non filtrés — attendu en Bangers après crash. "
                "Vérifiez les hélices."
            )
        else:
            report.warnings.append(
                f"{n_peaks} pics de vibration non filtrés. "
                "Possible : cadre fatigué, anti-vibrations usés, vis desserrées. "
                "Inspection physique recommandée avant nouveau tune."
            )

    by_axis: dict[str, list[tuple[float, str]]] = {}
    for aa in session.axes:
        bad = [p for p in aa.vibration_peaks if not p.covered_by_rpm_filter and p.power_db > 0]
        if bad:
            by_axis[aa.name] = [(p.freq_hz, p.label) for p in bad]

    for axis_name, peaks in by_axis.items():
        freqs_str = ', '.join(f'{f:.0f}Hz ({lbl})' for f, lbl in peaks[:3])
        report.warnings.append(f"Résonances non filtrées sur {axis_name} : {freqs_str}.")

    _recommend_filters(all_unfiltered, cfg, report)


def _recommend_filters(peaks: list[tuple[str, float, float]],
                       cfg: FlightConfig, report: DiagnosticReport):
    if not peaks:
        return

    unique_freqs: list[float] = []
    seen: set[int] = set()
    for _, f, _ in sorted(peaks, key=lambda x: -x[2]):
        bucket = int(f / 30) * 30
        if bucket not in seen:
            seen.add(bucket)
            unique_freqs.append(f)
        if len(unique_freqs) >= 3:
            break

    if not unique_freqs:
        return

    dyn_active = cfg.dyn_notch_count > 0 and cfg.dyn_notch_max_hz > 0

    if len(unique_freqs) == 1:
        f = unique_freqs[0]
        cutoff = max(50, int(f * 0.7))
        report.filter_recommendations += [
            f"# Notch statique pour résonance à {f:.0f}Hz",
            f"set gyro_notch1_hz = {int(f)}",
            f"set gyro_notch1_cutoff = {cutoff}",
        ]
    else:
        min_f = int(min(unique_freqs) * 0.8)
        max_f = int(max(unique_freqs) * 1.2)
        if dyn_active:
            cur_min = cfg.dyn_notch_min_hz
            cur_max = cfg.dyn_notch_max_hz
            if min_f < cur_min or max_f > cur_max:
                report.filter_recommendations += [
                    f"# Élargir le notch dynamique pour couvrir les résonances",
                    f"set dyn_notch_min_hz = {min(min_f, cur_min)}",
                    f"set dyn_notch_max_hz = {max(max_f, cur_max)}",
                    f"set dyn_notch_count = {max(cfg.dyn_notch_count, 3)}",
                ]
        else:
            report.filter_recommendations += [
                f"# Activer le notch dynamique ({len(unique_freqs)} résonances)",
                f"set dyn_notch_count = 3",
                f"set dyn_notch_min_hz = {min_f}",
                f"set dyn_notch_max_hz = {max_f}",
                f"set dyn_notch_q = 250",
            ]


def _clamp_change(current: int, delta_ratio: float,
                  max_delta: float, safe_range: tuple) -> int:
    clamped_delta = max(-max_delta, min(max_delta, delta_ratio))
    new_val = round(current * (1 + clamped_delta))
    new_val = max(safe_range[0], min(safe_range[1], new_val))
    return int(new_val)
