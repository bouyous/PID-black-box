"""
Génère des recommandations PID/filtres à partir de l'analyse + profil drone.
Principe de sécurité :
  - Les limites varient selon la taille du drone (3"→10").
  - On n'augmente jamais D seul sans vérifier le bruit.
  - Chaque recommandation indique le % de changement et la raison.
  - Le CLI dump est en lecture seule (l'utilisateur l'applique manuellement).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from analysis.analyzer import AxisAnalysis, SessionAnalysis
from analysis.header_parser import FlightConfig
from analysis.symptom_db import SymptomRule, match_symptoms


class Severity(str, Enum):
    OK      = "ok"
    INFO    = "info"
    WARNING = "warning"
    CRITICAL = "critical"


SEVERITY_EMOJI = {
    Severity.OK:       "✅",
    Severity.INFO:     "ℹ️",
    Severity.WARNING:  "⚠️",
    Severity.CRITICAL: "🔴",
}

AXIS_NAME = ['Roll', 'Pitch', 'Yaw']
AXIS_PARAM = ['roll', 'pitch', 'yaw']


@dataclass
class Recommendation:
    param: str          # ex: "p_roll"
    current: int
    suggested: int
    severity: Severity
    reason: str         # en français
    axis: int = -1      # -1 = global

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
            return (f"set {self.param} = {self.suggested}"
                    f"    # était désactivé — {self.reason}")
        return (f"set {self.param} = {self.suggested}"
                f"    # était {self.current} ({self.delta_pct:+.0f}%) — {self.reason}")


@dataclass
class DiagnosticReport:
    recommendations: list[Recommendation] = field(default_factory=list)
    summary: list[str]                    = field(default_factory=list)
    warnings: list[str]                   = field(default_factory=list)
    filter_recommendations: list[str]     = field(default_factory=list)  # lignes CLI brutes
    matched_symptoms: list[SymptomRule]   = field(default_factory=list)  # règles symptômes matchées
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
            f"# Profil drone : {self.drone_size}  |  Style : {self.flying_style}",
            f"# Score santé : {self.health_score}/100",
            "# APPLIQUER MANUELLEMENT dans le CLI Betaflight",
            "# Testez TOUJOURS en vol prudent avant de valider.",
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
            lines.append("# --- Filtres (résonances mécaniques détectées) ---")
            lines += self.filter_recommendations
            lines.append("")

        if not changed and not self.filter_recommendations:
            lines.append("# Aucun changement recommandé.")

        lines += ["", "save"]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Limites de sécurité par taille de drone
# ---------------------------------------------------------------------------
# Sources : Betaflight presets officiels, Joshua Bardwell, UAV Tech, Oscar Liang
# Pitch P est typiquement 5-15 pts plus haut que Roll P → plages adaptées

DRONE_PROFILES = {
    '3"':  dict(max_delta_pct=45, p_range=(25, 60), d_range=(18, 42), i_scale=1.1),
    '5"':  dict(max_delta_pct=25, p_range=(38, 78), d_range=(26, 56), i_scale=1.0),
    '6"':  dict(max_delta_pct=35, p_range=(42, 92), d_range=(28, 62), i_scale=0.95),
    '7"':  dict(max_delta_pct=45, p_range=(38, 88), d_range=(25, 58), i_scale=0.9),
    '10"': dict(max_delta_pct=55, p_range=(22, 68), d_range=(16, 48), i_scale=0.85),
}

DEFAULT_PROFILE = DRONE_PROFILES['5"']

# Seuils par style de vol
STYLE_THRESHOLDS = {
    'Freestyle':    dict(rise_max=80,  overshoot_max=25, noise_ratio_max=3.5, osc_score=0.35),
    'Racing':       dict(rise_max=55,  overshoot_max=18, noise_ratio_max=4.5, osc_score=0.30),
    'Long Range':   dict(rise_max=130, overshoot_max=35, noise_ratio_max=3.0, osc_score=0.28),
    'Bangers':      dict(rise_max=110, overshoot_max=40, noise_ratio_max=7.0, osc_score=0.45),
}
DEFAULT_STYLE = STYLE_THRESHOLDS['Freestyle']


# ---------------------------------------------------------------------------
# Score de santé (0–100)
# ---------------------------------------------------------------------------

def compute_health_score(session: SessionAnalysis) -> int:
    score = 100
    for aa in session.axes:
        if aa.has_oscillation:
            score -= min(20, int(aa.oscillation_score * 28))
        if aa.noise_ratio > 3.5:
            score -= min(15, int((aa.noise_ratio - 3.5) * 4))
        if aa.avg_rise_time_ms > 100:
            score -= min(8, int((aa.avg_rise_time_ms - 100) / 15))
        if aa.avg_overshoot_pct > 30:
            score -= min(6, int((aa.avg_overshoot_pct - 30) / 10))
        unfiltered = sum(1 for p in aa.vibration_peaks
                         if not p.covered_by_rpm_filter and p.power_db > 0)
        score -= min(12, unfiltered * 2)
    return max(0, min(100, score))


# ---------------------------------------------------------------------------
# Génération des recommandations
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

    profile  = DRONE_PROFILES.get(drone_size, DEFAULT_PROFILE)
    style    = STYLE_THRESHOLDS.get(flying_style, DEFAULT_STYLE)
    max_delta = profile['max_delta_pct'] / 100.0
    p_range   = profile['p_range']
    d_range   = profile['d_range']

    # Infos générales
    cells = battery_cells_override or session.cell_count
    if cells:
        v = session.battery_voltage
        report.summary.append(f"Batterie : {cells}S  ({v:.2f}V moy.)")
        if battery_cells_override and session.cell_count and battery_cells_override != session.cell_count:
            report.warnings.append(
                f"Tension détectée dans le BBL correspond à {session.cell_count}S, "
                f"mais profil sélectionné : {battery_cells_override}S. "
                "Les recommandations sont calculées pour la sélection manuelle."
            )
    if session.fly_duration_s > 0:
        report.summary.append(f"Durée de vol analysée : {session.fly_duration_s:.1f}s")
    if session.sample_rate_hz > 0:
        report.summary.append(f"Fréquence d'échantillonnage : {session.sample_rate_hz:.0f}Hz")
    if cfg.board:
        report.summary.append(f"FC : {cfg.board}")
    if flying_style == 'Bangers':
        report.summary.append(
            "Style Bangers/Intérieur : seuils relâchés — un peu de bruit D est toléré "
            "pour protéger les moteurs en cas de pale abîmée."
        )
    if cfg.simplified_mode > 0:
        report.warnings.append(
            "Mode PID simplifié actif (simplified_pids_mode). "
            "Les valeurs P/I/D affichées sont les valeurs RÉELLES. "
            "Pour les modifier, désactivez le mode simplifié dans BF."
        )
    if cfg.dshot_bidir and cfg.rpm_filter_harmonics > 0:
        report.summary.append(
            f"Filtre RPM actif ({cfg.rpm_filter_harmonics} harmoniques, "
            f"min {cfg.rpm_filter_min_hz}Hz)."
        )

    # Analyse axe par axe
    for aa in session.axes:
        _check_axis(aa, cfg, report, profile, style, max_delta, p_range, d_range)

    # Vibrations mécaniques
    _check_vibrations(session, cfg, report, flying_style)

    # Équilibre moteurs
    imb = session.axes[0].motor_imbalance if session.axes else 0
    if imb > 80:
        report.warnings.append(
            f"Déséquilibre moteur détecté (σ={imb:.0f} DSHOT). "
            "Vérifiez vos hélices et moteurs avant de modifier les PIDs."
        )

    # Score final
    report.health_score = compute_health_score(session)

    # Matching symptomatique (gelo, geno, slug, over, vib_mech)
    has_osc    = any(aa.has_oscillation for aa in session.axes)
    osc_freq   = max((aa.dominant_freq_hz for aa in session.axes if aa.has_oscillation), default=0.0)
    high_d_noi = any(
        aa.d_noise_rms / (aa.gyro_noise_rms + 1e-6) > style.get('noise_ratio_max', 3.5)
        for aa in session.axes if aa.d_noise_rms > 0
    )
    slow_resp  = any(
        aa.avg_rise_time_ms > style.get('rise_max', 80) and aa.step_count >= 3
        for aa in session.axes
    )
    high_over  = any(
        aa.avg_overshoot_pct > style.get('overshoot_max', 25) and aa.step_count >= 3
        for aa in session.axes
    )
    unfiltered_vib = any(
        any(p for p in aa.vibration_peaks if not p.covered_by_rpm_filter)
        for aa in session.axes
    )
    jitter = max((aa.oscillation_score for aa in session.axes), default=0.0)

    report.matched_symptoms = match_symptoms(
        has_oscillation       = has_osc,
        oscillation_freq_hz   = osc_freq,
        high_d_noise          = high_d_noi,
        slow_response         = slow_resp,
        high_overshoot        = high_over,
        unfiltered_vibrations = unfiltered_vib,
        jitter_score          = jitter,
    )

    if not report.recommendations and not report.filter_recommendations:
        report.summary.append(
            f"Aucun problème majeur détecté. Score santé : {report.health_score}/100."
        )

    return report


def _check_vibrations(session: SessionAnalysis, cfg: FlightConfig,
                      report: DiagnosticReport, flying_style: str = 'Freestyle'):
    """Ajoute des avertissements et des recommandations filtres pour les vibrations."""
    all_unfiltered: list[tuple[str, float, float]] = []  # (axis_name, freq, db)

    for aa in session.axes:
        bad = [p for p in aa.vibration_peaks
               if not p.covered_by_rpm_filter and p.power_db > 0]
        for p in bad:
            all_unfiltered.append((aa.name, p.freq_hz, p.power_db))

    if not all_unfiltered:
        return

    # Alerte de qualité cadre si nombreuses résonances
    n_peaks = len(all_unfiltered)
    if n_peaks >= 4:
        if flying_style == 'Bangers':
            report.warnings.append(
                f"{n_peaks} pics de vibration non filtrés détectés. "
                "En style Bangers, c'est attendu après un crash — "
                "vérifiez les hélices avant le prochain vol."
            )
        else:
            report.warnings.append(
                f"{n_peaks} pics de vibration non filtrés détectés. "
                "Cela peut indiquer un cadre de mauvaise qualité ou fatigué, "
                "des anti-vibrations usés, ou des vis desserrées. "
                "Inspection physique recommandée avant de modifier les PIDs."
            )

    # Avertissements par axe
    by_axis: dict[str, list[tuple[float, str]]] = {}
    for aa in session.axes:
        bad = [p for p in aa.vibration_peaks if not p.covered_by_rpm_filter and p.power_db > 0]
        if bad:
            by_axis[aa.name] = [(p.freq_hz, p.label) for p in bad]

    for axis_name, peaks in by_axis.items():
        freqs_str = ', '.join(f'{f:.0f}Hz ({lbl})' for f, lbl in peaks[:3])
        report.warnings.append(
            f"Résonances non filtrées sur {axis_name} : {freqs_str}."
        )

    # Recommandations filtres
    _recommend_filters(all_unfiltered, cfg, report)

    # Recommandations spécifiques par pic
    for aa in session.axes:
        for p in aa.vibration_peaks:
            if p.covered_by_rpm_filter:
                continue
            if p.freq_hz < 100 and p.power_db > 0:
                ax = aa.axis
                if ax < 2 and cfg.pid_d[ax] > 0:
                    d_min = cfg.d_min[ax] if ax < len(cfg.d_min) else 0
                    if d_min < cfg.pid_d[ax] * 0.8:
                        report.recommendations.append(Recommendation(
                            param=f"d_min_{AXIS_PARAM[ax]}",
                            current=d_min,
                            suggested=min(cfg.pid_d[ax], d_min + 3),
                            severity=Severity.INFO, axis=ax,
                            reason=f"prop wash à {p.freq_hz:.0f}Hz — d_min plus haut peut aider"
                        ))
                break
            elif 150 < p.freq_hz < 500 and p.power_db > 0 and flying_style != 'Bangers':
                report.warnings.append(
                    f"Résonance mécanique à {p.freq_hz:.0f}Hz ({aa.name}) — "
                    "serrez les vis, vérifiez les anti-vibrations et l'état du cadre."
                )
                break


def _recommend_filters(peaks: list[tuple[str, float, float]],
                       cfg: FlightConfig, report: DiagnosticReport):
    """Génère des recommandations CLI de filtres notch pour les résonances."""
    if not peaks:
        return

    # Collecte les fréquences uniques (pas déjà couvertes par dyn_notch actif)
    unique_freqs: list[float] = []
    seen: set[int] = set()
    for _, f, _ in sorted(peaks, key=lambda x: -x[2]):  # tri par puissance
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
        # Un seul pic → filtre notch statique
        f = unique_freqs[0]
        cutoff = max(50, int(f * 0.7))
        report.filter_recommendations += [
            f"# Filtre notch statique pour résonance à {f:.0f}Hz",
            f"set gyro_notch1_hz = {int(f)}",
            f"set gyro_notch1_cutoff = {cutoff}",
        ]
    else:
        # Plusieurs pics → ajuster/activer le filtre notch dynamique
        min_f = int(min(unique_freqs) * 0.8)
        max_f = int(max(unique_freqs) * 1.2)

        if dyn_active:
            # Ajuster la plage si les pics sont hors de la plage actuelle
            cur_min = cfg.dyn_notch_min_hz
            cur_max = cfg.dyn_notch_max_hz
            need_change = min_f < cur_min or max_f > cur_max
            if need_change:
                report.filter_recommendations += [
                    f"# Ajuster la plage du notch dynamique pour couvrir les résonances détectées",
                    f"set dyn_notch_min_hz = {min(min_f, cur_min)}",
                    f"set dyn_notch_max_hz = {max(max_f, cur_max)}",
                    f"set dyn_notch_count = {max(cfg.dyn_notch_count, 3)}",
                ]
        else:
            # Activer le notch dynamique
            report.filter_recommendations += [
                f"# Activer le filtre notch dynamique ({len(unique_freqs)} résonances détectées)",
                f"set dyn_notch_count = 3",
                f"set dyn_notch_min_hz = {min_f}",
                f"set dyn_notch_max_hz = {max_f}",
                f"set dyn_notch_q = 250",
            ]


def _check_axis(aa: AxisAnalysis, cfg: FlightConfig, report: DiagnosticReport,
                profile: dict, style: dict, max_delta: float,
                p_range: tuple, d_range: tuple):
    ax = aa.axis
    name = aa.name
    p_cur = cfg.pid_p[ax]
    i_cur = cfg.pid_i[ax]
    d_cur = cfg.pid_d[ax]

    osc_threshold   = style['osc_score']
    noise_threshold = style['noise_ratio_max']
    rise_threshold  = style['rise_max']
    over_threshold  = style['overshoot_max']

    # --- Oscillations P ---
    if aa.has_oscillation and aa.oscillation_score > osc_threshold and p_cur > 0:
        reduction = min(0.15, aa.oscillation_score * 0.25)
        p_new = _clamp_change(p_cur, -reduction, max_delta, p_range)
        if p_new != p_cur:
            report.recommendations.append(Recommendation(
                param=f"p_{AXIS_PARAM[ax]}",
                current=p_cur, suggested=p_new,
                severity=Severity.WARNING, axis=ax,
                reason=(f"oscillations à {aa.dominant_freq_hz:.0f}Hz "
                        f"(score {aa.oscillation_score:.2f})")
            ))

    # --- Bruit D excessif ---
    if aa.d_noise_rms > 0 and d_cur > 0 and ax < 2:
        noise_ratio = aa.d_noise_rms / (aa.gyro_noise_rms + 1e-6)
        if noise_ratio > noise_threshold:
            reduction = 0.10 if noise_ratio < noise_threshold * 1.4 else 0.15
            d_new = _clamp_change(d_cur, -reduction, max_delta, d_range)
            if d_new != d_cur:
                report.recommendations.append(Recommendation(
                    param=f"d_{AXIS_PARAM[ax]}",
                    current=d_cur, suggested=d_new,
                    severity=Severity.WARNING, axis=ax,
                    reason=(f"bruit D élevé (ratio {noise_ratio:.1f}x, seuil {noise_threshold}x) — "
                            "réduire D ou abaisser dterm_lpf1_hz")
                ))

    # --- Suivi setpoint trop lent ---
    if aa.avg_rise_time_ms > rise_threshold and aa.step_count >= 3 and p_cur > 0:
        increase = 0.10
        p_new = _clamp_change(p_cur, +increase, max_delta, p_range)
        if p_new != p_cur and not aa.has_oscillation:
            report.recommendations.append(Recommendation(
                param=f"p_{AXIS_PARAM[ax]}",
                current=p_cur, suggested=p_new,
                severity=Severity.INFO, axis=ax,
                reason=(f"réponse lente ({aa.avg_rise_time_ms:.0f}ms > {rise_threshold}ms) — "
                        "P légèrement bas")
            ))

    # --- Overshoot excessif ---
    if aa.avg_overshoot_pct > over_threshold and aa.step_count >= 3:
        if p_cur > 0 and not aa.has_oscillation:
            reduction = 0.08
            p_new = _clamp_change(p_cur, -reduction, max_delta, p_range)
            if p_new != p_cur:
                report.recommendations.append(Recommendation(
                    param=f"p_{AXIS_PARAM[ax]}",
                    current=p_cur, suggested=p_new,
                    severity=Severity.INFO, axis=ax,
                    reason=(f"overshoot {aa.avg_overshoot_pct:.0f}% > {over_threshold}% — "
                            "P légèrement haut ou I_relax à vérifier")
                ))

    # --- Valeurs hors plages connues ---
    if p_cur > 0 and not (p_range[0] <= p_cur <= p_range[1]):
        direction = "trop haut" if p_cur > p_range[1] else "trop bas"
        report.warnings.append(
            f"P {name} = {p_cur} ({direction} pour un {report.drone_size} "
            f"style {report.flying_style}, plage habituelle {p_range[0]}–{p_range[1]})"
        )
    if d_cur > 0 and ax < 2 and not (d_range[0] <= d_cur <= d_range[1]):
        direction = "trop haut" if d_cur > d_range[1] else "trop bas"
        report.warnings.append(
            f"D {name} = {d_cur} ({direction} pour un {report.drone_size}, "
            f"plage habituelle {d_range[0]}–{d_range[1]})"
        )


def _clamp_change(current: int, delta_ratio: float,
                  max_delta: float, safe_range: tuple) -> int:
    clamped_delta = max(-max_delta, min(max_delta, delta_ratio))
    new_val = round(current * (1 + clamped_delta))
    new_val = max(safe_range[0], min(safe_range[1], new_val))
    return int(new_val)
