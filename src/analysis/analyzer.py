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
OSCILLATION_BAND = (50, 400)

# Seuil de throttle stick (rcCommand[3], échelle 1000-2000µs)
THROTTLE_FLY_MIN = 1100   # throttle > 10%
# Seuil moteur DSHOT : motorOutput header = "idle,max" (ex: "48,2047")
# On considère en vol si motor > idle + 15% de la plage
MOTOR_FLY_RATIO  = 0.15   # 15% au-dessus de idle = en vol

# Durée minimale d'une section de vol utilisable
MIN_FLY_SECONDS  = 2.0


@dataclass
class AxisAnalysis:
    axis: int
    name: str

    # --- FFT / oscillations ---
    fft_freqs: np.ndarray = field(default_factory=lambda: np.array([]))
    fft_power: np.ndarray = field(default_factory=lambda: np.array([]))
    dominant_freq_hz: float = 0.0
    oscillation_score: float = 0.0   # 0–1, >0.4 = problématique
    has_oscillation: bool = False

    # --- Bruit ---
    gyro_noise_rms: float = 0.0      # bruit résiduel sur gyro filtré (vol stable)
    d_noise_rms: float = 0.0         # bruit sur terme D
    noise_ratio: float = 0.0         # std(brut) / std(filtré), >5 = bruyant

    # --- Suivi setpoint ---
    step_count: int = 0
    avg_rise_time_ms: float = 0.0
    avg_overshoot_pct: float = 0.0
    avg_error_rms: float = 0.0       # erreur RMS setpoint-gyro en vol

    # --- Équilibre moteurs ---
    motor_imbalance: float = 0.0     # std des moyennes moteur (0 = parfait)


@dataclass
class SessionAnalysis:
    axes: list[AxisAnalysis] = field(default_factory=list)
    sample_rate_hz: float = 0.0
    fly_duration_s: float = 0.0
    battery_voltage: float = 0.0
    cell_count: int = 0
    warnings: list[str] = field(default_factory=list)


def analyze(df: pd.DataFrame, cfg: FlightConfig) -> SessionAnalysis:
    result = SessionAnalysis()

    # Fréquence d'échantillonnage réelle
    if len(df) > 1 and 'time_s' in df.columns:
        dt = np.diff(df['time_s'].to_numpy(dtype=np.float64))
        dt = dt[dt > 0]
        if len(dt):
            result.sample_rate_hz = 1.0 / np.median(dt)

    # Tension batterie
    if 'vbatLatest' in df.columns:
        vbat = df['vbatLatest'].dropna()
        if len(vbat):
            result.battery_voltage = float(vbat.mean())
            result.cell_count = _guess_cell_count(result.battery_voltage)

    # Sections en vol (moteur actif)
    fly_mask = _fly_mask(df)
    result.fly_duration_s = float(fly_mask.sum()) / max(result.sample_rate_hz, 1)

    if result.fly_duration_s < MIN_FLY_SECONDS:
        result.warnings.append(
            "Session trop courte pour une analyse fiable "
            f"({result.fly_duration_s:.1f}s de vol détecté)."
        )

    for axis in range(3):
        result.axes.append(_analyze_axis(df, cfg, axis, fly_mask, result.sample_rate_hz))

    # Équilibre moteurs
    result.axes[0].motor_imbalance = _motor_imbalance(df, fly_mask)

    return result


# ---------------------------------------------------------------------------
# Analyse par axe
# ---------------------------------------------------------------------------

def _analyze_axis(df: pd.DataFrame, cfg: FlightConfig, axis: int,
                  fly_mask: np.ndarray, fs: float) -> AxisAnalysis:
    aa = AxisAnalysis(axis=axis, name=AXIS_NAMES[axis])

    gyro_col   = f'gyroADC[{axis}]'
    raw_col    = f'gyroUnfilt[{axis}]'
    d_col      = f'axisD[{axis}]'
    sp_col     = f'setpoint[{axis}]'

    if gyro_col not in df.columns:
        return aa

    gyro = df[gyro_col].to_numpy(dtype=np.float64)
    t    = df['time_s'].to_numpy(dtype=np.float64)

    # Données en vol uniquement
    gyro_fly = gyro[fly_mask]

    if len(gyro_fly) < 256 or fs < 100:
        return aa

    # --- FFT sur gyro filtré (sections en vol) ---
    freqs, power = _welch_psd(gyro_fly, fs)
    aa.fft_freqs = freqs
    aa.fft_power = power

    # Cherche le pic dominant dans la bande d'oscillation PID
    band = (freqs >= OSCILLATION_BAND[0]) & (freqs <= OSCILLATION_BAND[1])
    if band.any():
        band_power = power[band]
        band_freqs = freqs[band]
        peak_idx   = np.argmax(band_power)
        aa.dominant_freq_hz = float(band_freqs[peak_idx])
        # Score = puissance du pic / puissance totale dans la bande
        total_p = float(band_power.sum()) + 1e-9
        aa.oscillation_score = float(band_power[peak_idx]) / total_p
        aa.has_oscillation = aa.oscillation_score > 0.35 and aa.dominant_freq_hz > 60

    # --- Bruit gyro ---
    aa.gyro_noise_rms = float(np.std(gyro_fly))
    if raw_col in df.columns:
        raw_fly = df[raw_col].to_numpy(dtype=np.float64)[fly_mask]
        raw_std  = float(np.std(raw_fly))
        filt_std = float(np.std(gyro_fly)) + 1e-9
        aa.noise_ratio = raw_std / filt_std

    # --- Bruit D-term ---
    if d_col in df.columns:
        d_fly = df[d_col].to_numpy(dtype=np.float64)[fly_mask]
        aa.d_noise_rms = float(np.std(d_fly))

    # --- Suivi setpoint ---
    if sp_col in df.columns:
        sp = df[sp_col].to_numpy(dtype=np.float64)
        _fill_step_response(aa, t, gyro, sp, fly_mask, fs)

    return aa


def _fill_step_response(aa: AxisAnalysis, t: np.ndarray, gyro: np.ndarray,
                        sp: np.ndarray, fly_mask: np.ndarray, fs: float):
    """Détecte les échelons de setpoint et mesure la réponse gyro."""
    # Dérivée du setpoint = détection de mouvement de stick
    dsp = np.abs(np.diff(sp, prepend=sp[0]))
    threshold = max(50.0, np.percentile(dsp[fly_mask], 95) * 0.3)
    step_starts = np.where((dsp > threshold) & fly_mask)[0]

    # Anti-rebond : regrouper les starts proches
    if len(step_starts) == 0:
        return
    merged = [step_starts[0]]
    for s in step_starts[1:]:
        if s - merged[-1] > int(fs * 0.15):  # min 150ms entre deux steps
            merged.append(s)
    step_starts = np.array(merged)

    win = int(fs * 0.25)   # fenêtre d'analyse : 250ms
    rise_times, overshoots, errors = [], [], []

    for idx in step_starts:
        end = min(idx + win, len(gyro) - 1)
        if end - idx < int(fs * 0.05):
            continue
        sp_target = sp[end]
        sp_start  = sp[idx]
        delta     = sp_target - sp_start
        if abs(delta) < 30:   # ignore les micro-inputs
            continue

        window_gyro = gyro[idx:end]
        window_sp   = sp[idx:end]

        # Erreur RMS
        errors.append(float(np.sqrt(np.mean((window_gyro - window_sp) ** 2))))

        # Temps de montée : temps pour atteindre 90% du setpoint final
        target90 = sp_start + 0.9 * delta
        reached  = np.where(
            (delta > 0 and window_gyro >= target90) or
            (delta < 0 and window_gyro <= target90)
        )
        # Simplifié pour éviter les bugs de broadcasting
        if delta > 0:
            above = np.where(window_gyro >= target90)[0]
        else:
            above = np.where(window_gyro <= target90)[0]
        if len(above):
            rise_times.append(float(above[0]) / fs * 1000)

        # Overshoot
        if abs(delta) > 0:
            if delta > 0:
                peak = float(np.max(window_gyro))
            else:
                peak = float(np.min(window_gyro))
            overshoot = abs(peak - sp_target) / abs(delta) * 100
            if overshoot < 200:  # filtre les valeurs aberrantes
                overshoots.append(overshoot)

    aa.step_count       = len(step_starts)
    aa.avg_rise_time_ms = float(np.mean(rise_times))  if rise_times   else 0.0
    aa.avg_overshoot_pct = float(np.mean(overshoots)) if overshoots   else 0.0
    aa.avg_error_rms    = float(np.mean(errors))      if errors       else 0.0


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _welch_psd(signal: np.ndarray, fs: float,
               nperseg: int = 2048) -> tuple[np.ndarray, np.ndarray]:
    """Estimation de densité spectrale par la méthode de Welch."""
    n = len(signal)
    nperseg = min(nperseg, n // 4)
    if nperseg < 64:
        return np.array([]), np.array([])

    step = nperseg // 2
    windows = []
    hann = np.hanning(nperseg)
    for start in range(0, n - nperseg, step):
        seg = signal[start:start + nperseg] * hann
        windows.append(np.abs(np.fft.rfft(seg)) ** 2)

    if not windows:
        return np.array([]), np.array([])

    psd   = np.mean(windows, axis=0)
    freqs = np.fft.rfftfreq(nperseg, d=1.0 / fs)
    return freqs, psd


def _fly_mask(df: pd.DataFrame) -> np.ndarray:
    """True pour les lignes où le drone est en vol (au moins un moteur actif)."""
    # Priorité 1 : throttle stick RC (échelle 1000-2000µs)
    if 'rcCommand[3]' in df.columns:
        vals = df['rcCommand[3]'].to_numpy(dtype=np.float64)
        mask = vals > THROTTLE_FLY_MIN
        if mask.sum() > 100:
            return mask

    # Priorité 2 : valeur moteur DSHOT
    if 'motor[0]' in df.columns:
        vals = df['motor[0]'].to_numpy(dtype=np.float64)
        valid = vals[vals > 0]
        if len(valid):
            idle  = float(np.percentile(valid, 2))   # approximation du ralenti
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
