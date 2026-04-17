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
        return (f"{s} {self.param.upper()} : {self.current} → {self.suggested} "
                f"({self.delta_pct:+.0f}%)")

    def to_cli_line(self) -> str:
        return (f"set {self.param} = {self.suggested}"
                f"    # était {self.current} ({self.delta_pct:+.0f}%) — {self.reason}")


@dataclass
class DiagnosticReport:
    recommendations: list[Recommendation] = field(default_factory=list)
    summary: list[str]                    = field(default_factory=list)
    warnings: list[str]                   = field(default_factory=list)
    drone_size: str                       = "5\""

    def has_issues(self) -> bool:
        return any(r.severity in (Severity.WARNING, Severity.CRITICAL)
                   for r in self.recommendations)

    def cli_dump(self) -> str:
        lines = [
            "# ============================================================",
            "# BlackBox Analyzer — Recommandations PID",
            f"# Profil drone : {self.drone_size}",
            "# APPLIQUER MANUELLEMENT dans le CLI Betaflight",
            "# Testez TOUJOURS en vol prudent avant de valider.",
            "# ============================================================",
            "",
        ]
        changed = [r for r in self.recommendations if r.suggested != r.current]
        if not changed:
            lines.append("# Aucun changement recommandé.")
        else:
            lines.append("# Valeurs à modifier :")
            for r in changed:
                lines.append(r.to_cli_line())
        lines += ["", "save"]
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Limites de sécurité par taille de drone
# ---------------------------------------------------------------------------

# max_delta_pct : variation maximale par rapport à la valeur actuelle
# p_range, d_range : plages absolues connues comme sûres
DRONE_PROFILES = {
    '3"':  dict(max_delta_pct=45, p_range=(35, 75), d_range=(20, 50), i_scale=1.1),
    '5"':  dict(max_delta_pct=25, p_range=(35, 58), d_range=(22, 48), i_scale=1.0),
    '6"':  dict(max_delta_pct=35, p_range=(30, 52), d_range=(18, 42), i_scale=0.95),
    '7"':  dict(max_delta_pct=45, p_range=(28, 52), d_range=(15, 40), i_scale=0.9),
    '10"': dict(max_delta_pct=55, p_range=(18, 42), d_range=(10, 32), i_scale=0.85),
}

DEFAULT_PROFILE = DRONE_PROFILES['5"']


# ---------------------------------------------------------------------------
# Génération des recommandations
# ---------------------------------------------------------------------------

def generate_report(session: SessionAnalysis, cfg: FlightConfig,
                    drone_size: str = '5"') -> DiagnosticReport:
    report = DiagnosticReport(drone_size=drone_size)
    report.warnings = list(session.warnings)

    profile = DRONE_PROFILES.get(drone_size, DEFAULT_PROFILE)
    max_delta = profile['max_delta_pct'] / 100.0
    p_range   = profile['p_range']
    d_range   = profile['d_range']

    # Infos générales
    if session.cell_count:
        report.summary.append(f"Batterie détectée : {session.cell_count}S "
                               f"({session.battery_voltage:.2f}V moy.)")
    if session.fly_duration_s > 0:
        report.summary.append(f"Durée de vol analysée : {session.fly_duration_s:.1f}s")
    if session.sample_rate_hz > 0:
        report.summary.append(f"Fréquence d'échantillonnage : "
                               f"{session.sample_rate_hz:.0f}Hz")
    if cfg.board:
        report.summary.append(f"FC : {cfg.board}")
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
        _check_axis(aa, cfg, report, profile, max_delta, p_range, d_range)

    # Équilibre moteurs
    imb = session.axes[0].motor_imbalance if session.axes else 0
    if imb > 80:
        report.warnings.append(
            f"Déséquilibre moteur détecté (σ={imb:.0f} DSHOT). "
            "Vérifiez vos hélices et moteurs avant de modifier les PIDs."
        )

    # Si aucun problème
    if not report.recommendations:
        report.summary.append("Aucun problème majeur détecté. Le réglage semble équilibré.")

    return report


def _check_axis(aa: AxisAnalysis, cfg: FlightConfig, report: DiagnosticReport,
                profile: dict, max_delta: float,
                p_range: tuple, d_range: tuple):
    ax = aa.axis
    name = aa.name
    p_cur = cfg.pid_p[ax]
    i_cur = cfg.pid_i[ax]
    d_cur = cfg.pid_d[ax]

    # --- Oscillations P ---
    if aa.has_oscillation and p_cur > 0:
        reduction = min(0.15, aa.oscillation_score * 0.25)
        p_new = _clamp_change(p_cur, -reduction, max_delta, p_range)
        if p_new != p_cur:
            report.recommendations.append(Recommendation(
                param=f"p_{AXIS_PARAM[ax]}",
                current=p_cur, suggested=p_new,
                severity=Severity.WARNING, axis=ax,
                reason=(f"oscillations détectées à {aa.dominant_freq_hz:.0f}Hz "
                        f"(score {aa.oscillation_score:.2f})")
            ))

    # --- Bruit D excessif ---
    if aa.d_noise_rms > 0 and d_cur > 0 and ax < 2:  # pas de D sur yaw
        # Si le bruit D est très élevé par rapport au niveau gyro
        noise_ratio = aa.d_noise_rms / (aa.gyro_noise_rms + 1e-6)
        if noise_ratio > 3.5:
            reduction = 0.10 if noise_ratio < 5 else 0.15
            d_new = _clamp_change(d_cur, -reduction, max_delta, d_range)
            if d_new != d_cur:
                report.recommendations.append(Recommendation(
                    param=f"d_{AXIS_PARAM[ax]}",
                    current=d_cur, suggested=d_new,
                    severity=Severity.WARNING, axis=ax,
                    reason=(f"bruit D élevé (ratio {noise_ratio:.1f}x) — "
                            "réduire D ou abaisser dterm_lpf1_hz")
                ))

    # --- Suivi setpoint trop lent (P ou FF trop bas) ---
    if aa.avg_rise_time_ms > 0 and aa.step_count >= 3:
        if aa.avg_rise_time_ms > 80 and p_cur > 0:
            increase = 0.10
            p_new = _clamp_change(p_cur, +increase, max_delta, p_range)
            if p_new != p_cur and not aa.has_oscillation:
                report.recommendations.append(Recommendation(
                    param=f"p_{AXIS_PARAM[ax]}",
                    current=p_cur, suggested=p_new,
                    severity=Severity.INFO, axis=ax,
                    reason=(f"réponse lente ({aa.avg_rise_time_ms:.0f}ms) — "
                            "P légèrement bas")
                ))

    # --- Overshoot excessif ---
    if aa.avg_overshoot_pct > 25 and aa.step_count >= 3:
        if p_cur > 0 and not aa.has_oscillation:
            reduction = 0.08
            p_new = _clamp_change(p_cur, -reduction, max_delta, p_range)
            if p_new != p_cur:
                report.recommendations.append(Recommendation(
                    param=f"p_{AXIS_PARAM[ax]}",
                    current=p_cur, suggested=p_new,
                    severity=Severity.INFO, axis=ax,
                    reason=(f"overshoot moyen {aa.avg_overshoot_pct:.0f}% — "
                            "P légèrement haut ou I relax à vérifier")
                ))

    # --- Valeurs hors plages connues (alerte informative) ---
    if p_cur > 0 and not (p_range[0] <= p_cur <= p_range[1]):
        direction = "trop haut" if p_cur > p_range[1] else "trop bas"
        report.warnings.append(
            f"P {name} = {p_cur} ({direction} pour un {report.drone_size}, "
            f"plage habituelle {p_range[0]}–{p_range[1]})"
        )
    if d_cur > 0 and ax < 2 and not (d_range[0] <= d_cur <= d_range[1]):
        direction = "trop haut" if d_cur > d_range[1] else "trop bas"
        report.warnings.append(
            f"D {name} = {d_cur} ({direction} pour un {report.drone_size}, "
            f"plage habituelle {d_range[0]}–{d_range[1]})"
        )


def _clamp_change(current: int, delta_ratio: float,
                  max_delta: float, safe_range: tuple) -> int:
    """Applique un changement relatif en respectant la limite max et la plage sûre."""
    clamped_delta = max(-max_delta, min(max_delta, delta_ratio))
    new_val = round(current * (1 + clamped_delta))
    new_val = max(safe_range[0], min(safe_range[1], new_val))
    return int(new_val)
