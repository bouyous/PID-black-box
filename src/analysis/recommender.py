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


# ---------------------------------------------------------------------------
# Profils drones : plages sûres par taille
# ---------------------------------------------------------------------------

DRONE_PROFILES = {
    '3"':  dict(max_delta_pct=45, p_range=(25, 60), d_range=(18, 42),
                i_range=(60, 180), f_range=(60, 180), d_min_ratio_floor=0.40),
    '5"':  dict(max_delta_pct=25, p_range=(38, 78), d_range=(26, 56),
                i_range=(70, 180), f_range=(80, 200), d_min_ratio_floor=0.45),
    '6"':  dict(max_delta_pct=35, p_range=(42, 92), d_range=(28, 62),
                i_range=(70, 180), f_range=(80, 200), d_min_ratio_floor=0.45),
    '7"':  dict(max_delta_pct=45, p_range=(38, 88), d_range=(25, 58),
                i_range=(70, 180), f_range=(80, 200), d_min_ratio_floor=0.40),
    '10"': dict(max_delta_pct=55, p_range=(22, 68), d_range=(16, 48),
                i_range=(60, 160), f_range=(60, 180), d_min_ratio_floor=0.35),
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
    'Freestyle': dict(
        osc_target=0.10,        osc_critical=0.22,
        drift_target=0.10,      drift_critical=0.25,
        propwash_target=0.10,   propwash_critical=0.22,
        rise_target_ms=30,      rise_critical_ms=60,
        overshoot_target=12,    overshoot_critical=25,
        noise_target=2.5,       noise_critical=4.2,
        hf_noise_target=0.08,   hf_noise_critical=0.20,
        lag_target_ms=5,        lag_critical_ms=12,
        d_min_ratio=0.65,
    ),
    'Racing': dict(
        osc_target=0.08,        osc_critical=0.18,
        drift_target=0.15,      drift_critical=0.30,
        propwash_target=0.15,   propwash_critical=0.30,
        rise_target_ms=22,      rise_critical_ms=45,
        overshoot_target=8,     overshoot_critical=18,
        noise_target=3.2,       noise_critical=5.5,
        hf_noise_target=0.15,   hf_noise_critical=0.28,
        lag_target_ms=3,        lag_critical_ms=8,
        d_min_ratio=0.75,
    ),
    'Long Range': dict(
        osc_target=0.08,        osc_critical=0.15,
        drift_target=0.06,      drift_critical=0.15,
        propwash_target=0.18,   propwash_critical=0.35,
        rise_target_ms=55,      rise_critical_ms=100,
        overshoot_target=18,    overshoot_critical=30,
        noise_target=2.0,       noise_critical=3.2,
        hf_noise_target=0.05,   hf_noise_critical=0.15,
        lag_target_ms=10,       lag_critical_ms=25,
        d_min_ratio=0.50,
    ),
    'Bangers': dict(
        osc_target=0.18,        osc_critical=0.40,
        drift_target=0.22,      drift_critical=0.45,
        propwash_target=0.22,   propwash_critical=0.45,
        rise_target_ms=45,      rise_critical_ms=100,
        overshoot_target=25,    overshoot_critical=45,
        noise_target=4.5,       noise_critical=7.5,
        hf_noise_target=0.20,   hf_noise_critical=0.35,
        lag_target_ms=8,        lag_critical_ms=20,
        d_min_ratio=0.40,
    ),
}
DEFAULT_STYLE = STYLE_TARGETS['Freestyle']


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
                    battery_cells_override: int = 0) -> DiagnosticReport:
    report = DiagnosticReport(
        drone_size=drone_size,
        flying_style=flying_style,
        battery_cells_override=battery_cells_override,
    )
    report.warnings = list(session.warnings)

    profile = DRONE_PROFILES.get(drone_size, DEFAULT_PROFILE)
    style   = STYLE_TARGETS.get(flying_style, DEFAULT_STYLE)

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
    _check_filters_global(session, cfg, report, style)

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
                          report: DiagnosticReport, style: dict):
    # Bruit HF moyen sur les 2 axes (yaw hors D)
    hf_vals = [aa.hf_noise_ratio for aa in session.axes[:2] if aa.hf_noise_ratio > 0]
    if not hf_vals:
        return
    avg_hf = sum(hf_vals) / len(hf_vals)

    if avg_hf > style['hf_noise_critical']:
        # Bruit HF élevé → serrer dterm_lpf1
        cur = cfg.dterm_lpf1_dyn_max_hz or cfg.dterm_lpf1_hz
        if cur > 120:
            new = max(100, int(cur * 0.82))
            report.filter_recommendations.append(
                f"set dterm_lpf1_dyn_max_hz = {new}    "
                f"# était {cur} — bruit HF élevé ({avg_hf*100:.0f}% > {style['hf_noise_critical']*100:.0f}%)"
            )
    elif avg_hf < style['hf_noise_target'] * 0.6 and session.axes[0].avg_rise_time_ms > style['rise_target_ms']:
        # Peu de bruit HF + réponse lente → on peut ouvrir les filtres pour gagner en réactivité
        cur = cfg.dterm_lpf1_dyn_max_hz or cfg.dterm_lpf1_hz
        if 0 < cur < 250:
            new = min(260, int(cur * 1.15))
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
