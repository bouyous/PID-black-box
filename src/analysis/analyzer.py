"""
Moteur d'analyse : FFT, détection de bruit, suivi setpoint.
Travaille sur une DataFrame déjà décodée + un FlightConfig.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from analysis.header_parser import FlightConfig

AXIS_NAMES = ['Roll', 'Pitch', 'Yaw']

# Fréquences d'oscillation PID typiques (Hz)
OSCILLATION_BAND = (40, 400)

# Drift ligne droite : oscillation basse fréquence en vol stable
DRIFT_BAND = (3, 30)

# Oscillation PID classique d'un 5" (P trop haut / D trop bas) :
# tombe entre la bande drift (3-30) et la bande osc HF (40-400). Détectée
# séparément pour ne PAS recommander une hausse de I (qui empire le drone).
PID_OSC_BAND = (8, 40)

# Prop wash : oscillation 20-80 Hz après un input
PROPWASH_BAND = (15, 80)

# Seuil throttle stick (échelle 1000-2000µs)
THROTTLE_FLY_MIN = 1100
THROTTLE_LOW_CUT = 1150
MOTOR_FLY_RATIO  = 0.15
MIN_FLY_SECONDS  = 2.0


@dataclass
class VibrationPeak:
    freq_hz: float
    power_db: float
    covered_by_rpm_filter: bool
    harmonic: int = 0
    label: str = ""


@dataclass
class PidBalanceMetrics:
    p_rms: float = 0.0
    i_rms: float = 0.0
    d_rms: float = 0.0
    f_rms: float = 0.0
    d_to_p_ratio: float = 0.0
    i_to_p_ratio: float = 0.0
    f_to_p_ratio: float = 0.0
    sample_count: int = 0
    verdict: str = "Indisponible"
    detail: str = "Traces PID absentes ou trop courtes."


@dataclass
class StepResponseCurve:
    time_ms: np.ndarray = field(default_factory=lambda: np.array([]))
    response: np.ndarray = field(default_factory=lambda: np.array([]))
    sample_count: int = 0
    peak: float = 0.0
    latency_ms: float = 0.0


@dataclass
class AxisAnalysis:
    axis: int
    name: str

    # FFT / oscillations
    fft_freqs: np.ndarray = field(default_factory=lambda: np.array([]))
    fft_power: np.ndarray = field(default_factory=lambda: np.array([]))
    dominant_freq_hz: float = 0.0
    oscillation_score: float = 0.0
    has_oscillation: bool = False

    # Bruit
    gyro_noise_rms: float = 0.0
    d_noise_rms: float = 0.0
    noise_ratio: float = 0.0
    hf_noise_ratio: float = 0.0      # bruit > 300Hz / bruit total

    # Drift ligne droite (oscillation basse fréquence en vol stable)
    drift_score: float = 0.0         # 0-1
    drift_freq_hz: float = 0.0

    # Oscillation PID 8-40 Hz (P trop haut / D trop bas / filtres trop lâches).
    # Distincte du drift : ce n'est pas un manque de I, c'est une boucle qui
    # accroche. Recommander I↑ ici aggrave systématiquement le drone.
    pid_osc_score: float = 0.0       # 0-1
    pid_osc_freq_hz: float = 0.0
    has_pid_oscillation: bool = False

    # Punch wobble : plongeon ou rebond du nez sur les coups de gaz.
    # Calcule la corrélation throttle_jerk × |gyro| sur fenêtres de punch-out.
    punch_wobble_score: float = 0.0  # 0-1 (utile surtout sur Pitch)

    # Prop wash (oscillation amortie après input)
    propwash_score: float = 0.0      # 0-1
    low_throttle_rebound_score: float = 0.0  # 0-1
    low_throttle_rebound_freq_hz: float = 0.0

    # Vibrations mécaniques
    vibration_peaks: list[VibrationPeak] = field(default_factory=list)
    has_unfiltered_vibration: bool = False

    # Suivi setpoint
    step_count: int = 0
    avg_rise_time_ms: float = 0.0
    avg_overshoot_pct: float = 0.0
    avg_error_rms: float = 0.0
    tracking_lag_ms: float = 0.0     # retard gyro vs setpoint (indique FF bas)
    pid_balance: PidBalanceMetrics = field(default_factory=PidBalanceMetrics)
    step_response_curve: StepResponseCurve = field(default_factory=StepResponseCurve)

    # Équilibre moteurs
    motor_imbalance: float = 0.0

    # Vent / perturbations externes : ratio gyro_std / sp_std en sections
    # calmes (stick doux). Si gyro très agité ET stick calme = le drone subit
    # une force externe (vent, turbulences) — pas un manque d'I.
    # 0   = pas de perturbation détectée
    # 0.5 = vent modéré
    # 1.0 = vent fort / rafales (aucune chance qu'un manque d'I crée ça)
    wind_disturbance_score: float = 0.0
    gyro_std_calm: float = 0.0       # σ(gyro) sur sections calmes (deg/s)
    sp_std_calm: float = 0.0         # σ(setpoint) sur sections calmes (deg/s)


@dataclass
class FlightTypeResult:
    label: str                   # "Freestyle", "Vol mixte", "Stationnaire / Hover"
    confidence: float            # 0.0–1.0
    score: int                   # score brut (0–9)
    max_setpoint_dps: float      # max |setpoint| roll/pitch en vol
    time_high_rate_pct: float    # % du temps à |sp| > 300 deg/s
    throttle_p2p: float          # amplitude throttle normalisée 0–1
    sp_std: float                # écart-type setpoint roll/pitch


@dataclass
class FlightProtocolResult:
    calm_reference_s: float = 0.0
    throttle_ramp_s: float = 0.0
    tune_maneuver_s: float = 0.0
    confidence: float = 0.0
    calm_windows: list[tuple[float, float]] = field(default_factory=list)
    throttle_ramp_windows: list[tuple[float, float]] = field(default_factory=list)
    tune_windows: list[tuple[float, float]] = field(default_factory=list)

    @property
    def label(self) -> str:
        if self.confidence >= 0.80:
            return "fort"
        if self.confidence >= 0.55:
            return "moyen"
        return "limité"


@dataclass
class SessionAnalysis:
    axes: list[AxisAnalysis] = field(default_factory=list)
    sample_rate_hz: float = 0.0
    fly_duration_s: float = 0.0
    battery_voltage: float = 0.0
    battery_voltage_min: float = 0.0   # tension minimale atteinte (sag pic)
    battery_sag_v_per_cell: float = 0.0  # (max − min) / nb cells
    cell_count: int = 0
    avg_erpm: list[float] = field(default_factory=list)
    avg_motor_hz: float = 0.0
    throttle_avg: float = 0.0        # moyenne de la manette en vol (0-1)
    throttle_p2p: float = 0.0        # variation crête-crête (jerk)
    low_throttle_maneuver_pct: float = 0.0
    warnings: list[str] = field(default_factory=list)
    flight_type: FlightTypeResult | None = None
    protocol: FlightProtocolResult = field(default_factory=FlightProtocolResult)


def analyze(df: pd.DataFrame, cfg: FlightConfig) -> SessionAnalysis:
    result = SessionAnalysis()

    if len(df) > 1 and 'time_s' in df.columns:
        dt = np.diff(df['time_s'].to_numpy(dtype=np.float64))
        dt = dt[dt > 0]
        if len(dt):
            result.sample_rate_hz = 1.0 / np.median(dt)

    if 'vbatLatest' in df.columns:
        vbat = df['vbatLatest'].dropna()
        if len(vbat):
            result.battery_voltage = float(vbat.mean())
            result.battery_voltage_min = float(vbat.min())
            result.cell_count = _guess_cell_count(
                result.battery_voltage, float(vbat.max())
            )
            if result.cell_count > 0:
                result.battery_sag_v_per_cell = (
                    float(vbat.max() - vbat.min()) / result.cell_count
                )

    fly_mask = _fly_mask(df)
    result.fly_duration_s = float(fly_mask.sum()) / max(result.sample_rate_hz, 1)

    if result.fly_duration_s < MIN_FLY_SECONDS:
        result.warnings.append(
            f"Session trop courte pour une analyse fiable "
            f"({result.fly_duration_s:.1f}s de vol détecté)."
        )

    # Throttle stats
    if 'rcCommand[3]' in df.columns:
        thr = df['rcCommand[3]'].to_numpy(dtype=np.float64)[fly_mask]
        if len(thr):
            norm = np.clip((thr - 1000) / 1000.0, 0, 1)
            result.throttle_avg = float(np.mean(norm))
            result.throttle_p2p = float(np.percentile(norm, 95) - np.percentile(norm, 5))
            result.low_throttle_maneuver_pct = _low_throttle_maneuver_pct(df, fly_mask)

    for axis in range(3):
        result.axes.append(_analyze_axis(df, cfg, axis, fly_mask, result.sample_rate_hz))

    result.avg_erpm = _avg_erpm(df, fly_mask)
    if result.avg_erpm:
        valid = [r for r in result.avg_erpm if r > 500]
        result.avg_motor_hz = _erpm_to_motor_hz(float(np.mean(valid)), cfg) if valid else 0.0

    for aa in result.axes:
        _detect_vibrations(aa, df, cfg, fly_mask, result.sample_rate_hz,
                           result.avg_motor_hz)

    result.axes[0].motor_imbalance = _motor_imbalance(df, fly_mask)
    result.flight_type = detect_flight_type(df, fly_mask)
    result.protocol = detect_flight_protocol(df, fly_mask, result.sample_rate_hz)

    return result


def detect_flight_protocol(df: pd.DataFrame, fly_mask: np.ndarray,
                           fs: float) -> FlightProtocolResult:
    """Détecte les phases utiles au diagnostic dans une session.

    Le protocole n'est pas obligatoire. Il sert à qualifier la confiance :
    une courte phase calme aide les filtres, les rampes gaz aident les
    vibrations/harmoniques, et les grosses commandes restent indispensables
    pour PID/FF/latence.
    """
    fs = max(float(fs or _infer_sample_rate(df)), 1.0)
    n = len(df)
    if n == 0:
        return FlightProtocolResult()

    sp_abs = np.zeros(n, dtype=np.float64)
    gyro_abs = np.zeros(n, dtype=np.float64)
    for axis in range(3):
        sp_col = f'setpoint[{axis}]'
        gyro_col = f'gyroADC[{axis}]'
        if sp_col in df.columns:
            sp_abs = np.maximum(sp_abs, np.abs(df[sp_col].to_numpy(dtype=np.float64)))
        if gyro_col in df.columns:
            gyro_abs = np.maximum(gyro_abs, np.abs(df[gyro_col].to_numpy(dtype=np.float64)))

    time = df['time_s'].to_numpy(dtype=np.float64) if 'time_s' in df.columns else np.arange(n) / fs

    calm = fly_mask & (sp_abs < 70) & (gyro_abs < 120)
    calm_runs = _find_runs(calm, min_len=max(1, int(fs * 2.0)))
    calm_s = float(max((e - s for s, e in calm_runs), default=0) / fs)

    ramp_s = 0.0
    ramp_runs: list[tuple[int, int]] = []
    if 'rcCommand[3]' in df.columns:
        thr = df['rcCommand[3]'].to_numpy(dtype=np.float64)
        norm = np.clip((thr - 1000.0) / 1000.0, 0.0, 1.0)
        if len(norm) > 1:
            dthr = np.gradient(_smooth_for_protocol(norm, fs, seconds=0.45)) * fs
            ramp = (
                fly_mask
                & (norm > 0.08)
                & (norm < 0.92)
                & (np.abs(dthr) > 0.025)
                & (np.abs(dthr) < 1.8)
            )
            ramp_runs = _find_runs(ramp, min_len=max(1, int(fs * 0.25)))
            ramp_s = float(sum(e - s for s, e in ramp_runs) / fs)

    tune = fly_mask & ((sp_abs > 160) | (gyro_abs > 260))
    tune_runs = _find_runs(tune, min_len=max(1, int(fs * 0.05)))
    tune_s = float(sum(e - s for s, e in tune_runs) / fs)

    calm_score = min(calm_s / 25.0, 1.0)
    ramp_score = min(ramp_s / 12.0, 1.0)
    tune_score = min(tune_s / 5.0, 1.0)
    confidence = 0.25 * calm_score + 0.30 * ramp_score + 0.45 * tune_score
    return FlightProtocolResult(
        calm_reference_s=float(calm_s),
        throttle_ramp_s=float(ramp_s),
        tune_maneuver_s=float(tune_s),
        confidence=float(min(confidence, 1.0)),
        calm_windows=_runs_to_windows(calm_runs, time, limit=3),
        throttle_ramp_windows=_runs_to_windows(ramp_runs, time, limit=6),
        tune_windows=_runs_to_windows(tune_runs, time, limit=8),
    )


def _smooth_for_protocol(values: np.ndarray, fs: float, seconds: float) -> np.ndarray:
    win = max(3, int(fs * seconds))
    if win >= len(values):
        win = max(3, len(values) // 2)
    if win <= 3:
        return values
    kernel = np.ones(win, dtype=np.float64) / win
    return np.convolve(values, kernel, mode='same')


def _runs_to_windows(runs: list[tuple[int, int]], time: np.ndarray,
                     limit: int = 5) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    if len(time) == 0:
        return out
    last = len(time) - 1
    for start, end in sorted(runs, key=lambda r: r[1] - r[0], reverse=True)[:limit]:
        s = max(0, min(start, last))
        e = max(0, min(end - 1, last))
        out.append((float(time[s]), float(time[e])))
    return sorted(out)


def detect_flight_type(df: pd.DataFrame, fly_mask: np.ndarray) -> FlightTypeResult:
    """Détermine si le vol est Freestyle, mixte ou Stationnaire/Hover.

    Basé sur le setpoint max, la proportion de temps à haute cadence,
    la variation du throttle et l'écart-type des setpoints.
    """
    max_sp = 0.0
    sp_std = 0.0
    time_high_rate_pct = 0.0

    for axis in range(2):  # roll et pitch (yaw moins discriminant)
        col = f'setpoint[{axis}]'
        if col in df.columns:
            sp = df[col].to_numpy(dtype=np.float64)[fly_mask]
            if len(sp):
                max_sp = max(max_sp, float(np.max(np.abs(sp))))
                sp_std = max(sp_std, float(np.std(sp)))
                time_high_rate_pct = max(time_high_rate_pct,
                                         float(np.mean(np.abs(sp) > 300)))

    throttle_p2p = 0.0
    if 'rcCommand[3]' in df.columns:
        thr = df['rcCommand[3]'].to_numpy(dtype=np.float64)[fly_mask]
        if len(thr) > 10:
            throttle_p2p = float(
                (np.percentile(thr, 95) - np.percentile(thr, 5)) / 1000.0
            )

    score = 0
    if max_sp > 500:
        score += 3
    elif max_sp > 350:
        score += 2
    elif max_sp > 200:
        score += 1

    if time_high_rate_pct > 0.08:
        score += 2
    elif time_high_rate_pct > 0.03:
        score += 1

    if throttle_p2p > 0.55:
        score += 2
    elif throttle_p2p > 0.35:
        score += 1

    if sp_std > 150:
        score += 2
    elif sp_std > 80:
        score += 1

    max_score = 9
    if score >= 6:
        label = "Freestyle"
        confidence = min(1.0, score / max_score)
    elif score >= 3:
        label = "Vol mixte"
        confidence = 0.5 + abs(score - 4.5) / max_score
    else:
        label = "Stationnaire / Hover"
        confidence = min(1.0, (max_score - score) / max_score)

    return FlightTypeResult(
        label=label,
        confidence=confidence,
        score=score,
        max_setpoint_dps=max_sp,
        time_high_rate_pct=time_high_rate_pct,
        throttle_p2p=throttle_p2p,
        sp_std=sp_std,
    )


def _analyze_axis(df: pd.DataFrame, cfg: FlightConfig, axis: int,
                  fly_mask: np.ndarray, fs: float) -> AxisAnalysis:
    aa = AxisAnalysis(axis=axis, name=AXIS_NAMES[axis])

    gyro_col = f'gyroADC[{axis}]'
    raw_col  = f'gyroUnfilt[{axis}]'
    d_col    = f'axisD[{axis}]'
    sp_col   = f'setpoint[{axis}]'

    if gyro_col not in df.columns:
        return aa

    gyro = df[gyro_col].to_numpy(dtype=np.float64)
    t    = df['time_s'].to_numpy(dtype=np.float64)
    gyro_fly = gyro[fly_mask]

    if len(gyro_fly) < 256 or fs < 100:
        return aa

    # FFT gyro filtré
    freqs, power = _welch_psd(gyro_fly, fs)
    aa.fft_freqs = freqs
    aa.fft_power = power

    # Pic dominant dans la bande PID
    band = (freqs >= OSCILLATION_BAND[0]) & (freqs <= OSCILLATION_BAND[1])
    if band.any():
        band_power = power[band]
        band_freqs = freqs[band]
        peak_idx   = np.argmax(band_power)
        aa.dominant_freq_hz = float(band_freqs[peak_idx])
        total_p = float(band_power.sum()) + 1e-9
        aa.oscillation_score = float(band_power[peak_idx]) / total_p
        aa.has_oscillation = aa.oscillation_score > 0.12 and aa.dominant_freq_hz > 50

    # Bruit HF (> 300 Hz) pour guider la tuning de filtres
    if len(freqs):
        total_p = float(np.sum(power)) + 1e-9
        hf_mask = freqs > 300
        hf_p = float(np.sum(power[hf_mask])) if hf_mask.any() else 0
        aa.hf_noise_ratio = hf_p / total_p

    # Bruit gyro
    aa.gyro_noise_rms = float(np.std(gyro_fly))
    if raw_col in df.columns:
        raw_fly = df[raw_col].to_numpy(dtype=np.float64)[fly_mask]
        raw_std  = float(np.std(raw_fly))
        filt_std = float(np.std(gyro_fly)) + 1e-9
        aa.noise_ratio = raw_std / filt_std

    # Bruit D-term
    if d_col in df.columns:
        d_fly = df[d_col].to_numpy(dtype=np.float64)[fly_mask]
        aa.d_noise_rms = float(np.std(d_fly))

    # Suivi setpoint + drift + prop wash
    if sp_col in df.columns:
        sp = df[sp_col].to_numpy(dtype=np.float64)
        _fill_step_response(aa, t, gyro, sp, fly_mask, fs)
        _detect_drift(aa, gyro, sp, fly_mask, fs)
        _detect_pid_oscillation(aa, gyro, sp, fly_mask, fs)
        _detect_propwash(aa, gyro, sp, fly_mask, fs)
        _detect_low_throttle_rebound(aa, df, gyro, sp, fly_mask, fs)
        _detect_punch_wobble(aa, df, gyro, fly_mask, fs)

    _fill_pid_balance(aa, df, fly_mask)

    return aa


def _fill_pid_balance(aa: AxisAnalysis, df: pd.DataFrame, fly_mask: np.ndarray):
    p_col = f'axisP[{aa.axis}]'
    i_col = f'axisI[{aa.axis}]'
    d_col = f'axisD[{aa.axis}]'
    f_col = f'axisF[{aa.axis}]'
    if p_col not in df.columns or not fly_mask.any():
        return

    active = fly_mask.copy()
    sp_col = f'setpoint[{aa.axis}]'
    gyro_col = f'gyroADC[{aa.axis}]'
    if sp_col in df.columns:
        active &= np.abs(df[sp_col].to_numpy(dtype=np.float64)) > 60
    elif gyro_col in df.columns:
        active &= np.abs(df[gyro_col].to_numpy(dtype=np.float64)) > 60

    if active.sum() < 128:
        active = fly_mask
    if active.sum() < 128:
        return

    def rms(col: str) -> float:
        if col not in df.columns:
            return 0.0
        vals = df[col].to_numpy(dtype=np.float64)[active]
        vals = vals[np.isfinite(vals)]
        if len(vals) == 0:
            return 0.0
        return float(np.sqrt(np.mean(vals * vals)))

    p = rms(p_col)
    i = rms(i_col)
    d = rms(d_col)
    f = rms(f_col)
    ratio_dp = d / max(p, 1e-6)
    ratio_ip = i / max(p, 1e-6)
    ratio_fp = f / max(p, 1e-6)

    verdict = "OK"
    detail = "D/P dans une zone lisible, à confirmer avec rebonds et température moteur."
    if d > 0:
        if ratio_dp < 0.30:
            verdict = "D faible vs P"
            detail = "D amortit peu les arrêts : surveiller bounceback et propwash."
        elif ratio_dp < 0.45:
            verdict = "D un peu bas"
            detail = "Réponse vive, mais marge limitée sur les rebonds en sortie de figure."
        elif ratio_dp > 0.90:
            verdict = "D très haut vs P"
            detail = "Drone potentiellement mou, moteurs plus chauds, latence ressentie."
        elif ratio_dp > 0.70:
            verdict = "D haut"
            detail = "Bon amortissement possible, mais vérifier chaleur moteur et bruit D."
    elif aa.axis < 2:
        verdict = "D absent"
        detail = "Aucun amortissement D mesurable sur roll/pitch."

    aa.pid_balance = PidBalanceMetrics(
        p_rms=p,
        i_rms=i,
        d_rms=d,
        f_rms=f,
        d_to_p_ratio=float(ratio_dp if p > 0 else 0.0),
        i_to_p_ratio=float(ratio_ip if p > 0 else 0.0),
        f_to_p_ratio=float(ratio_fp if p > 0 else 0.0),
        sample_count=int(active.sum()),
        verdict=verdict,
        detail=detail,
    )


def _fill_step_response(aa: AxisAnalysis, t: np.ndarray, gyro: np.ndarray,
                        sp: np.ndarray, fly_mask: np.ndarray, fs: float):
    dsp = np.abs(np.diff(sp, prepend=sp[0]))
    if not fly_mask.any():
        return
    threshold = max(50.0, np.percentile(dsp[fly_mask], 95) * 0.3)
    step_starts = np.where((dsp > threshold) & fly_mask)[0]

    if len(step_starts) == 0:
        return
    merged = [step_starts[0]]
    for s in step_starts[1:]:
        if s - merged[-1] > int(fs * 0.15):
            merged.append(s)
    step_starts = np.array(merged)

    win = int(fs * 0.50)
    curve_len = max(64, int(fs * 0.50))
    x_src = np.linspace(0, 500, curve_len, endpoint=False)
    x_dst = np.linspace(0, 500, 160)
    rise_times, overshoots, errors, lags = [], [], [], []
    norm_curves: list[np.ndarray] = []

    for idx in step_starts:
        end = min(idx + win, len(gyro) - 1)
        if end - idx < int(fs * 0.05):
            continue
        pre_start = max(0, idx - int(fs * 0.03))
        sp_start = float(np.median(sp[pre_start:idx + 1]))

        post_start = min(idx + max(1, int(fs * 0.035)), len(sp) - 1)
        post_end = min(idx + max(2, int(fs * 0.14)), end)
        if post_end - post_start < int(fs * 0.03):
            continue
        post_sp = sp[post_start:post_end]
        if len(post_sp) < 3:
            continue
        sp_target = float(np.median(post_sp))
        if np.std(post_sp) > max(40.0, abs(sp_target - sp_start) * 0.45):
            continue
        delta = sp_target - sp_start
        if abs(delta) < 30:
            continue

        window_gyro = gyro[idx:end]
        window_sp   = sp[idx:end]

        errors.append(float(np.sqrt(np.mean((window_gyro - window_sp) ** 2))))

        target90 = sp_start + 0.9 * delta
        if delta > 0:
            above = np.where(window_gyro >= target90)[0]
        else:
            above = np.where(window_gyro <= target90)[0]
        if len(above):
            rise_times.append(float(above[0]) / fs * 1000)

        # Lag : décalage entre moment où sp atteint 50% et gyro atteint 50%
        target50 = sp_start + 0.5 * delta
        if delta > 0:
            sp_at_50 = np.where(window_sp >= target50)[0]
            gyro_at_50 = np.where(window_gyro >= target50)[0]
        else:
            sp_at_50 = np.where(window_sp <= target50)[0]
            gyro_at_50 = np.where(window_gyro <= target50)[0]
        if len(sp_at_50) and len(gyro_at_50):
            lag = (float(gyro_at_50[0]) - float(sp_at_50[0])) / fs * 1000
            if 0 <= lag < 200:
                lags.append(lag)

        if abs(delta) > 0:
            peak = float(np.max(window_gyro)) if delta > 0 else float(np.min(window_gyro))
            overshoot = abs(peak - sp_target) / abs(delta) * 100
            if overshoot < 200:
                overshoots.append(overshoot)

        curve_end = min(idx + curve_len, len(gyro))
        if curve_end - idx >= max(32, int(fs * 0.12)):
            g = gyro[idx:curve_end]
            norm = (g - sp_start) / delta
            if len(norm) < curve_len:
                norm = np.pad(norm, (0, curve_len - len(norm)), mode='edge')
            norm = np.clip(norm, -0.5, 1.8)
            norm_curves.append(np.interp(x_dst, x_src, norm[:curve_len]))

    aa.step_count       = len(step_starts)
    aa.avg_rise_time_ms  = float(np.mean(rise_times))  if rise_times  else 0.0
    aa.avg_overshoot_pct = float(np.mean(overshoots)) if overshoots else 0.0
    aa.avg_error_rms     = float(np.mean(errors))     if errors     else 0.0
    aa.tracking_lag_ms   = float(np.mean(lags))       if lags       else 0.0
    if norm_curves:
        avg_curve = np.mean(np.vstack(norm_curves), axis=0)
        aa.step_response_curve = StepResponseCurve(
            time_ms=x_dst,
            response=avg_curve,
            sample_count=len(norm_curves),
            peak=float(np.max(avg_curve)),
            latency_ms=aa.tracking_lag_ms,
        )


def _detect_drift(aa: AxisAnalysis, gyro: np.ndarray, sp: np.ndarray,
                  fly_mask: np.ndarray, fs: float):
    """Détecte les oscillations lentes (3-30 Hz) en vol stable.

    Signature typique : ligne droite (setpoint proche 0), gyro oscille
    → soit P trop haut, soit I trop bas, soit iterm_relax trop agressif.
    """
    # Sections calmes : |sp| < 80 deg/s pendant > 0.4s
    calm = (np.abs(sp) < 80) & fly_mask
    runs = _find_runs(calm, min_len=int(fs * 0.4))
    if not runs:
        return

    pieces = [gyro[s:e] for s, e in runs]
    gyro_calm = np.concatenate(pieces) if pieces else np.array([])
    if len(gyro_calm) < 512:
        return

    # FFT sur sections calmes
    freqs, psd = _welch_psd(gyro_calm, fs, nperseg=1024)
    if len(freqs) == 0:
        return

    band = (freqs >= DRIFT_BAND[0]) & (freqs <= DRIFT_BAND[1])
    if not band.any():
        return

    band_power = psd[band]
    band_freqs = freqs[band]
    peak_idx = int(np.argmax(band_power))
    peak_f = float(band_freqs[peak_idx])
    peak_p = float(band_power[peak_idx])

    # Score relatif : pic vs somme dans la bande
    total_band = float(np.sum(band_power)) + 1e-9
    rel = peak_p / total_band

    # Normalisation absolue : compare au niveau global
    total_power = float(np.sum(psd)) + 1e-9
    abs_contrib = peak_p / total_power * 10

    aa.drift_score = float(min(1.0, max(rel * 1.5, abs_contrib)))
    aa.drift_freq_hz = peak_f

    # Détection PERTURBATION EXTERNE (vent / rafales) :
    #   Quand le pilote a le stick calme, on devrait voir un gyro calme.
    #   Si le gyro reste très agité malgré un setpoint quasi nul, ce n'est
    #   pas un défaut PID (un manque d'I ne crée pas d'agitation gyro
    #   spontanée — il créerait une dérive lente UNI-directionnelle).
    #   C'est le drone qui SUBIT une force externe → vent fort / rafales.
    sp_calm_concat = np.concatenate([sp[s:e] for s, e in runs])
    if len(sp_calm_concat) >= 256:
        gyro_std = float(np.std(gyro_calm))
        sp_std = float(np.std(sp_calm_concat))
        aa.gyro_std_calm = gyro_std
        aa.sp_std_calm = sp_std
        # Ratio gyro/setpoint en sections calmes
        # - sticks vraiment calmes (< 30 deg/s std)
        # - gyro très agité (> 30 deg/s std)
        # - ratio > 3 → vent qui domine la boucle de réponse
        if sp_std < 30 and gyro_std > 30:
            ratio = gyro_std / max(sp_std, 1.0)
            # Calibration empirique : ratio 3 = perturbation modérée,
            # ratio 8+ = vent fort qui domine
            aa.wind_disturbance_score = float(min(1.0,
                                                  max(0.0, (ratio - 3.0) / 6.0)))


def _detect_pid_oscillation(aa: AxisAnalysis, gyro: np.ndarray, sp: np.ndarray,
                             fly_mask: np.ndarray, fs: float):
    """Détecte une oscillation PID 8-40 Hz en vol calme et en vol actif.

    Différent du drift : on cherche un pic *étroit* persistant (boucle qui
    accroche), pas une dérive lente. Si présent, **interdire** au recommender
    de monter I (ça aggraverait). La cause est P trop haut, D trop bas, ou
    filtres D-term trop lâches.

    Le score combine deux mesures :
      - rel = pic / énergie de la bande 8-40 Hz   (concentration)
      - q   = pic / médiane de la bande            (proéminence)
    On exige `q > 3` pour parler d'oscillation, sinon on est juste face au
    bruit large bande naturel d'un quad.
    """
    # On utilise l'ensemble du vol (pas seulement les sections calmes) :
    # une oscillation PID s'exprime aussi pendant les manœuvres modérées.
    gyro_fly = gyro[fly_mask]
    if len(gyro_fly) < 1024:
        return

    freqs, psd = _welch_psd(gyro_fly, fs, nperseg=2048)
    if len(freqs) == 0:
        return

    band = (freqs >= PID_OSC_BAND[0]) & (freqs <= PID_OSC_BAND[1])
    if not band.any():
        return

    band_power = psd[band]
    band_freqs = freqs[band]
    peak_idx = int(np.argmax(band_power))
    peak_f = float(band_freqs[peak_idx])
    peak_p = float(band_power[peak_idx])

    total_band = float(np.sum(band_power)) + 1e-9
    median_band = float(np.median(band_power)) + 1e-12
    rel = peak_p / total_band
    q   = peak_p / median_band

    # Score : concentration × proéminence, plafonné.
    score = min(1.0, rel * 1.3 + max(0.0, (q - 3) / 20))
    aa.pid_osc_score = float(score)
    aa.pid_osc_freq_hz = peak_f
    # Drapeau : pic clairement séparé du bruit de fond
    aa.has_pid_oscillation = (q > 4.0 and rel > 0.10) or score > 0.35


def _detect_punch_wobble(aa: AxisAnalysis, df: pd.DataFrame, gyro: np.ndarray,
                          fly_mask: np.ndarray, fs: float):
    """Détecte les rebonds du nez sur les coups de gaz (anti-gravity insuffisant
    ou iterm_relax trop agressif sur pitch).

    Méthode : repérer les "punch-outs" (throttle qui monte fort), regarder
    le pic d'écart gyro-vs-zéro dans les 200ms suivantes. Si le drone plonge
    ou rebondit systématiquement, le score grimpe.

    Pertinent surtout sur l'axe Pitch (axis=1).
    """
    if 'rcCommand[3]' not in df.columns or fs < 100:
        return

    thr = df['rcCommand[3]'].to_numpy(dtype=np.float64)
    # Lissage léger pour éviter de réagir au bruit de stick
    win = max(1, int(fs * 0.05))
    if win > 1:
        kernel = np.ones(win) / win
        thr_smooth = np.convolve(thr, kernel, mode='same')
    else:
        thr_smooth = thr

    # Jerk normalisé : variation throttle sur ~150ms
    horizon = max(1, int(fs * 0.15))
    if horizon >= len(thr_smooth):
        return
    djerk = np.zeros_like(thr_smooth)
    djerk[horizon:] = thr_smooth[horizon:] - thr_smooth[:-horizon]
    djerk_norm = djerk / 1000.0  # plage stick brute

    # Punch out = montée throttle > 25% en 150ms et fly_mask actif
    punch_idx = np.where((djerk_norm > 0.25) & fly_mask)[0]
    if len(punch_idx) == 0:
        return

    # Dédupliquer : un punch peut s'étaler sur plusieurs samples
    merged = [int(punch_idx[0])]
    for i in punch_idx[1:]:
        if i - merged[-1] > int(fs * 0.4):
            merged.append(int(i))
    if len(merged) < 2:
        return

    look_after = int(fs * 0.25)
    deviations = []
    for idx in merged:
        end = min(idx + look_after, len(gyro) - 1)
        if end - idx < int(fs * 0.05):
            continue
        seg = gyro[idx:end]
        deviations.append(float(np.max(np.abs(seg - seg[0]))))

    if not deviations:
        return

    mean_dev = float(np.mean(deviations))
    # Calibration empirique : 30 deg/s = peu, 120 deg/s = wobble franc.
    aa.punch_wobble_score = float(min(1.0, max(0.0, (mean_dev - 30) / 90)))


def _detect_propwash(aa: AxisAnalysis, gyro: np.ndarray, sp: np.ndarray,
                     fly_mask: np.ndarray, fs: float):
    """Détecte l'oscillation amortie 15-80 Hz après un input fort.

    Cherche les moments où |setpoint| passe d'une valeur forte à proche de 0,
    et regarde l'oscillation résiduelle sur 100-400ms après.
    """
    # Transitions : sp passe de > 200 à < 80 en < 100ms
    abs_sp = np.abs(sp)
    mov_win = max(1, int(fs * 0.1))
    # Cherche les pics de sp et le retour calme
    transitions = []
    i = mov_win
    while i < len(sp) - int(fs * 0.4):
        if fly_mask[i] and abs_sp[i] > 250:
            # Cherche le prochain retour sous 80 dans les 300ms
            horizon = min(len(sp) - 1, i + int(fs * 0.3))
            below = np.where(abs_sp[i:horizon] < 80)[0]
            if len(below):
                zero_idx = i + int(below[0])
                transitions.append(zero_idx)
                i = zero_idx + int(fs * 0.4)
                continue
        i += mov_win

    if len(transitions) < 2:
        return

    # Fenêtre 50-350ms après la transition, FFT 15-80 Hz
    win_len = int(fs * 0.3)
    offset  = int(fs * 0.05)
    clips = []
    for t_idx in transitions:
        start = t_idx + offset
        end = start + win_len
        if end < len(gyro):
            clips.append(gyro[start:end])
    if not clips:
        return

    gyro_after = np.concatenate(clips)
    if len(gyro_after) < 256:
        return

    freqs, psd = _welch_psd(gyro_after, fs, nperseg=256)
    if len(freqs) == 0:
        return
    band = (freqs >= PROPWASH_BAND[0]) & (freqs <= PROPWASH_BAND[1])
    if not band.any():
        return

    band_power = psd[band]
    total_power = float(np.sum(psd)) + 1e-9
    propwash_p = float(np.sum(band_power))
    aa.propwash_score = float(min(1.0, propwash_p / total_power * 2.5))


def _detect_low_throttle_rebound(aa: AxisAnalysis, df: pd.DataFrame,
                                 gyro: np.ndarray, sp: np.ndarray,
                                 fly_mask: np.ndarray, fs: float):
    """Détecte les rebonds après flips/rolls gaz coupés.

    En freestyle/bangers, le throttle peut être bas pendant la figure, puis le
    rebond apparaît à la récupération. Cette signature doit rester visible.
    """
    if 'rcCommand[3]' not in df.columns or fs < 100:
        return

    thr = df['rcCommand[3]'].to_numpy(dtype=np.float64)
    abs_sp = np.abs(sp)
    active_flip = (abs_sp > 260) & (thr < THROTTLE_LOW_CUT) & fly_mask
    runs = _find_runs(active_flip, min_len=max(2, int(fs * 0.05)))
    if not runs:
        return

    clips = []
    max_devs = []
    for _start, end in runs:
        a = min(end + int(fs * 0.04), len(gyro) - 1)
        b = min(end + int(fs * 0.42), len(gyro))
        if b - a < int(fs * 0.12):
            continue
        seg = gyro[a:b]
        clips.append(seg - np.mean(seg))
        max_devs.append(float(np.max(np.abs(seg - seg[0]))))

    if not clips:
        return
    sig = np.concatenate(clips)
    if len(sig) < 128:
        return

    freqs, psd = _welch_psd(sig, fs, nperseg=512)
    if len(freqs) == 0:
        return
    band = (freqs >= 8) & (freqs <= 80)
    if not band.any():
        return

    band_power = psd[band]
    band_freqs = freqs[band]
    peak_idx = int(np.argmax(band_power))
    total_power = float(np.sum(psd)) + 1e-9
    spectral = float(np.sum(band_power)) / total_power
    amp = float(np.mean(max_devs)) if max_devs else 0.0
    amp_score = max(0.0, min(1.0, (amp - 35.0) / 120.0))
    aa.low_throttle_rebound_score = float(min(1.0, spectral * 2.2 + amp_score * 0.7))
    aa.low_throttle_rebound_freq_hz = float(band_freqs[peak_idx])


def _find_runs(mask: np.ndarray, min_len: int) -> list[tuple[int, int]]:
    """Retourne les (start, end) des runs de True >= min_len."""
    if not mask.any():
        return []
    diff = np.diff(mask.astype(int))
    starts = np.where(diff == 1)[0] + 1
    ends   = np.where(diff == -1)[0] + 1
    if mask[0]:
        starts = np.r_[0, starts]
    if mask[-1]:
        ends = np.r_[ends, len(mask)]
    return [(int(s), int(e)) for s, e in zip(starts, ends) if e - s >= min_len]


def _welch_psd(signal: np.ndarray, fs: float,
               nperseg: int = 2048) -> tuple[np.ndarray, np.ndarray]:
    n = len(signal)
    nperseg = min(nperseg, n // 4)
    if nperseg < 64:
        return np.array([]), np.array([])

    step = nperseg // 2
    hann = np.hanning(nperseg)
    windows = []
    for start in range(0, n - nperseg, step):
        seg = signal[start:start + nperseg] * hann
        windows.append(np.abs(np.fft.rfft(seg)) ** 2)
    if not windows:
        return np.array([]), np.array([])
    psd   = np.mean(windows, axis=0)
    freqs = np.fft.rfftfreq(nperseg, d=1.0 / fs)
    return freqs, psd


def _fly_mask(df: pd.DataFrame) -> np.ndarray:
    """Sections en vol, y compris les figures gaz coupés.

    Un flip à bas gaz est encore du vol réel. On combine moteur, throttle,
    setpoint et gyro, puis on garde un peu de contexte avant/après manoeuvre
    pour ne pas perdre les rebonds de récupération.
    """
    n = len(df)
    if n == 0:
        return np.zeros(0, dtype=bool)
    fs = _infer_sample_rate(df)

    throttle_active = np.zeros(n, dtype=bool)
    motor_active = np.zeros(n, dtype=bool)
    gyro_active = np.zeros(n, dtype=bool)
    stick_active = np.zeros(n, dtype=bool)

    if 'rcCommand[3]' in df.columns:
        thr = df['rcCommand[3]'].to_numpy(dtype=np.float64)
        throttle_active = (thr > THROTTLE_FLY_MIN)

    motor_cols = [f'motor[{i}]' for i in range(4) if f'motor[{i}]' in df.columns]
    if motor_cols:
        motors = np.vstack([df[c].to_numpy(dtype=np.float64) for c in motor_cols])
        mean_motor = np.nanmean(motors, axis=0)
        valid = mean_motor[np.isfinite(mean_motor) & (mean_motor > 0)]
        if len(valid):
            idle = float(np.percentile(valid, 5))
            high = float(np.percentile(valid, 99))
            threshold = idle + 0.06 * max(1.0, high - idle)
            motor_active = mean_motor > threshold

    # Rotation active : flip / roll / rotation marquée
    for ax in range(3):
        col = f'gyroADC[{ax}]'
        if col in df.columns:
            g = df[col].to_numpy(dtype=np.float64)
            gyro_active |= (np.abs(g) > 100.0)

    # Commande pilote active : stick clairement déplacé
    for ax in range(3):
        col = f'setpoint[{ax}]'
        if col in df.columns:
            sp = df[col].to_numpy(dtype=np.float64)
            stick_active |= (np.abs(sp) > 80.0)

    maneuver = stick_active | gyro_active
    powered_context = _dilate_mask(throttle_active | motor_active, int(fs * 0.8))
    maneuver_context = _dilate_mask(maneuver, int(fs * 0.35))
    base = throttle_active | motor_active | (maneuver & (powered_context | maneuver_context))
    base = _dilate_mask(base, int(fs * 0.25))
    if base.sum() > 100:
        return base

    fallback = throttle_active | motor_active | maneuver
    if fallback.sum() > 0:
        return _dilate_mask(fallback, int(fs * 0.25))
    return np.ones(n, dtype=bool)


def _infer_sample_rate(df: pd.DataFrame) -> float:
    if len(df) > 1 and 'time_s' in df.columns:
        dt = np.diff(df['time_s'].to_numpy(dtype=np.float64))
        dt = dt[dt > 0]
        if len(dt):
            return max(1.0, float(1.0 / np.median(dt)))
    return 1000.0


def _dilate_mask(mask: np.ndarray, radius: int) -> np.ndarray:
    if radius <= 0 or not mask.any():
        return mask
    radius = min(radius, max(1, (len(mask) - 1) // 2))
    kernel = np.ones(radius * 2 + 1, dtype=int)
    return np.convolve(mask.astype(int), kernel, mode='same') > 0


def _low_throttle_maneuver_pct(df: pd.DataFrame, fly_mask: np.ndarray) -> float:
    if 'rcCommand[3]' not in df.columns or not fly_mask.any():
        return 0.0
    thr = df['rcCommand[3]'].to_numpy(dtype=np.float64)
    maneuver = np.zeros(len(df), dtype=bool)
    for ax in range(3):
        sp_col = f'setpoint[{ax}]'
        gyro_col = f'gyroADC[{ax}]'
        if sp_col in df.columns:
            maneuver |= np.abs(df[sp_col].to_numpy(dtype=np.float64)) > 180
        if gyro_col in df.columns:
            maneuver |= np.abs(df[gyro_col].to_numpy(dtype=np.float64)) > 180
    low_maneuver = (thr < THROTTLE_LOW_CUT) & maneuver & fly_mask
    return float(np.mean(low_maneuver[fly_mask])) if fly_mask.any() else 0.0


def _motor_imbalance(df: pd.DataFrame, fly_mask: np.ndarray) -> float:
    means = []
    for i in range(4):
        col = f'motor[{i}]'
        if col in df.columns:
            vals = df[col].to_numpy(dtype=np.float64)[fly_mask]
            if len(vals):
                means.append(float(np.mean(vals)))
    return float(np.std(means)) if len(means) == 4 else 0.0


def _guess_cell_count(vbat: float, vbat_max: float | None = None) -> int:
    """Choisit le nombre de cellules le plus plausible pour la tension moyenne
    observée en vol.

    Ancienne version : `vbat > cells * 3.3` testée du plus grand au plus petit.
    Bug : un 6S à 19.76 V (3.29 V/cell, batterie épuisée) tombait en dessous
    du seuil 19.8 V → classé 4S, alors qu'un 4S ne peut physiquement pas
    dépasser ~17 V (4 × 4.25 V max).

    Nouveau : on cherche la configuration qui place vbat dans une plage
    plausible 3.0–4.25 V/cell, et on prend la plus probable (vbat/cells
    proche de 3.7 V).
    """
    if vbat <= 0:
        return 0
    observed_max = vbat if vbat_max is None or vbat_max <= 0 else vbat_max
    candidates = []
    # Plage 2.55-4.25 V/cell : couvre LiPo et Li-ion. On refuse les hypothèses
    # physiquement impossibles sur la tension max observée.
    for cells in (1, 2, 3, 4, 6, 8, 10, 12):
        v_per_cell = vbat / cells
        max_per_cell = observed_max / cells
        if 2.55 <= v_per_cell <= 4.25 and max_per_cell <= 4.28:
            # Quand 4S plein et 6S Li-ion bas se recouvrent, préférer le pack
            # le plus haut évite de sous-estimer dangereusement les alertes/cell.
            score = abs(v_per_cell - 3.65) - cells * 0.015
            candidates.append((score, cells))
    if candidates:
        candidates.sort()
        return candidates[0][1]
    # Fallback : ancienne logique (vol vide ou config non standard)
    for cells in (12, 10, 8, 6, 4, 3, 2, 1):
        if vbat > cells * 3.3:
            return cells
    return 0


def _avg_erpm(df: pd.DataFrame, fly_mask: np.ndarray) -> list[float]:
    result = []
    for i in range(4):
        col = f'eRPM[{i}]'
        if col in df.columns:
            v = df[col].to_numpy(dtype=np.float64)[fly_mask]
            active = v[v > 5]
            result.append(float(np.median(active)) * 100.0 if len(active) else 0.0)
    return result


def _erpm_to_motor_hz(erpm: float, cfg: FlightConfig) -> float:
    """Convertit eRPM reel en fréquence mécanique moteur."""
    pole_pairs = max(1.0, float(cfg.motor_poles or 14) / 2.0)
    return erpm / pole_pairs / 60.0


def _detect_vibrations(aa: AxisAnalysis, df: pd.DataFrame, cfg: FlightConfig,
                        fly_mask: np.ndarray, fs: float, avg_motor_hz: float):
    raw_col = f'gyroUnfilt[{aa.axis}]'
    if raw_col not in df.columns or fs < 200 or len(aa.fft_freqs) == 0:
        return

    raw_sig = df[raw_col].to_numpy(dtype=np.float64)[fly_mask]
    if len(raw_sig) < 512:
        return

    freqs, psd = _welch_psd(raw_sig, fs)
    if len(freqs) == 0:
        return

    db = 10.0 * np.log10(np.clip(psd, 1e-12, None))
    band = (freqs >= 40) & (freqs <= 1000)
    db_band   = db[band]
    freq_band = freqs[band]
    if len(db_band) < 10:
        return

    noise_floor = float(np.percentile(db_band, 30))
    peak_thresh = noise_floor + 6.0   # plus sensible (6 dB vs 8 précédemment)

    peaks = []
    for i in range(1, len(db_band) - 1):
        if db_band[i] > peak_thresh and db_band[i] > db_band[i-1] and db_band[i] > db_band[i+1]:
            peaks.append((float(freq_band[i]), float(db_band[i])))

    merged: list[tuple[float, float]] = []
    for f, p in sorted(peaks):
        if merged and f - merged[-1][0] < 20:
            if p > merged[-1][1]:
                merged[-1] = (f, p)
        else:
            merged.append((f, p))

    rpm_freqs: list[float] = []
    if cfg.dshot_bidir and avg_motor_hz > 0:
        for h in range(1, cfg.rpm_filter_harmonics + 2):
            rpm_freqs.append(avg_motor_hz * h)

    rpm_tol = 0.12

    for f, p in merged:
        covered = False
        harmonic = 0
        for h, rf in enumerate(rpm_freqs, 1):
            if rf > 0 and abs(f - rf) / rf < rpm_tol:
                covered = True
                harmonic = h
                break
        label = f"RPM×{harmonic}" if covered else _classify_vibration(f)
        aa.vibration_peaks.append(VibrationPeak(
            freq_hz=f, power_db=p,
            covered_by_rpm_filter=covered,
            harmonic=harmonic, label=label
        ))
        if not covered and p > noise_floor + 10:
            aa.has_unfiltered_vibration = True


def _classify_vibration(freq_hz: float) -> str:
    if freq_hz < 80:
        return "Prop wash / basse fréq"
    elif freq_hz < 200:
        return "Rés. cadre"
    elif freq_hz < 400:
        return "Rés. hélice"
    else:
        return "Bruit HF"
