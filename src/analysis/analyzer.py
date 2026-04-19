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

# Prop wash : oscillation 20-80 Hz après un input
PROPWASH_BAND = (15, 80)

# Seuil throttle stick (échelle 1000-2000µs)
THROTTLE_FLY_MIN = 1100
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

    # Prop wash (oscillation amortie après input)
    propwash_score: float = 0.0      # 0-1

    # Vibrations mécaniques
    vibration_peaks: list[VibrationPeak] = field(default_factory=list)
    has_unfiltered_vibration: bool = False

    # Suivi setpoint
    step_count: int = 0
    avg_rise_time_ms: float = 0.0
    avg_overshoot_pct: float = 0.0
    avg_error_rms: float = 0.0
    tracking_lag_ms: float = 0.0     # retard gyro vs setpoint (indique FF bas)

    # Équilibre moteurs
    motor_imbalance: float = 0.0


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
class SessionAnalysis:
    axes: list[AxisAnalysis] = field(default_factory=list)
    sample_rate_hz: float = 0.0
    fly_duration_s: float = 0.0
    battery_voltage: float = 0.0
    cell_count: int = 0
    avg_erpm: list[float] = field(default_factory=list)
    avg_motor_hz: float = 0.0
    throttle_avg: float = 0.0        # moyenne de la manette en vol (0-1)
    throttle_p2p: float = 0.0        # variation crête-crête (jerk)
    warnings: list[str] = field(default_factory=list)
    flight_type: FlightTypeResult | None = None


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
            result.cell_count = _guess_cell_count(result.battery_voltage)

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

    for axis in range(3):
        result.axes.append(_analyze_axis(df, cfg, axis, fly_mask, result.sample_rate_hz))

    result.avg_erpm = _avg_erpm(df, fly_mask)
    if result.avg_erpm:
        valid = [r for r in result.avg_erpm if r > 500]
        result.avg_motor_hz = float(np.mean(valid)) / 60.0 if valid else 0.0

    for aa in result.axes:
        _detect_vibrations(aa, df, cfg, fly_mask, result.sample_rate_hz,
                           result.avg_motor_hz)

    result.axes[0].motor_imbalance = _motor_imbalance(df, fly_mask)
    result.flight_type = detect_flight_type(df, fly_mask)

    return result


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
        _detect_propwash(aa, gyro, sp, fly_mask, fs)

    return aa


def _fill_step_response(aa: AxisAnalysis, t: np.ndarray, gyro: np.ndarray,
                        sp: np.ndarray, fly_mask: np.ndarray, fs: float):
    dsp = np.abs(np.diff(sp, prepend=sp[0]))
    threshold = max(50.0, np.percentile(dsp[fly_mask], 95) * 0.3)
    step_starts = np.where((dsp > threshold) & fly_mask)[0]

    if len(step_starts) == 0:
        return
    merged = [step_starts[0]]
    for s in step_starts[1:]:
        if s - merged[-1] > int(fs * 0.15):
            merged.append(s)
    step_starts = np.array(merged)

    win = int(fs * 0.25)
    rise_times, overshoots, errors, lags = [], [], [], []

    for idx in step_starts:
        end = min(idx + win, len(gyro) - 1)
        if end - idx < int(fs * 0.05):
            continue
        sp_target = sp[end]
        sp_start  = sp[idx]
        delta     = sp_target - sp_start
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

    aa.step_count       = len(step_starts)
    aa.avg_rise_time_ms  = float(np.mean(rise_times))  if rise_times  else 0.0
    aa.avg_overshoot_pct = float(np.mean(overshoots)) if overshoots else 0.0
    aa.avg_error_rms     = float(np.mean(errors))     if errors     else 0.0
    aa.tracking_lag_ms   = float(np.mean(lags))       if lags       else 0.0


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
    if 'rcCommand[3]' in df.columns:
        vals = df['rcCommand[3]'].to_numpy(dtype=np.float64)
        mask = vals > THROTTLE_FLY_MIN
        if mask.sum() > 100:
            return mask
    if 'motor[0]' in df.columns:
        vals = df['motor[0]'].to_numpy(dtype=np.float64)
        valid = vals[vals > 0]
        if len(valid):
            idle  = float(np.percentile(valid, 2))
            max_v = float(np.percentile(valid, 99))
            threshold = idle + MOTOR_FLY_RATIO * (max_v - idle)
            return vals > threshold
    return np.ones(len(df), dtype=bool)


def _motor_imbalance(df: pd.DataFrame, fly_mask: np.ndarray) -> float:
    means = []
    for i in range(4):
        col = f'motor[{i}]'
        if col in df.columns:
            vals = df[col].to_numpy(dtype=np.float64)[fly_mask]
            if len(vals):
                means.append(float(np.mean(vals)))
    return float(np.std(means)) if len(means) == 4 else 0.0


def _guess_cell_count(vbat: float) -> int:
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
