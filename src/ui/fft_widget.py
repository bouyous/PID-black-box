"""
Widget Vibrations : analyse fréquentielle du gyroscope.
- Gyro filtré vs brut sur le même graphe
- Lignes verticales : LPF gyro, LPF D-term, harmoniques RPM filter
- Echelle log Y (dB)
- Onglet Spectrogram : évolution temporelle du bruit
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox, QHBoxLayout, QLabel, QTabWidget, QVBoxLayout, QWidget,
)

from analysis.header_parser import FlightConfig

ROLL_COLOR  = '#e74c3c'
PITCH_COLOR = '#2ecc71'
YAW_COLOR   = '#3498db'
AXIS_COLORS = [ROLL_COLOR, PITCH_COLOR, YAW_COLOR]
AXIS_NAMES  = ['Roll', 'Pitch', 'Yaw']

MAX_FFT_HZ  = 1000   # fréquence max affichée
WELCH_SEG   = 4096   # taille fenêtre Welch


# ---------------------------------------------------------------------------
# Calcul FFT / PSD
# ---------------------------------------------------------------------------

def _welch(signal: np.ndarray, fs: float) -> tuple[np.ndarray, np.ndarray]:
    n = len(signal)
    nperseg = min(WELCH_SEG, n // 4)
    if nperseg < 128:
        return np.array([0.0]), np.array([0.0])
    step = nperseg // 2
    hann = np.hanning(nperseg)
    segs = []
    for start in range(0, n - nperseg, step):
        s = signal[start:start + nperseg] * hann
        segs.append(np.abs(np.fft.rfft(s)) ** 2)
    if not segs:
        return np.array([0.0]), np.array([0.0])
    psd   = np.mean(segs, axis=0)
    freqs = np.fft.rfftfreq(nperseg, 1.0 / fs)
    return freqs, psd


def _db(power: np.ndarray) -> np.ndarray:
    return 10.0 * np.log10(np.clip(power, 1e-12, None))


def _erpm_to_motor_hz(erpm: float, cfg: FlightConfig) -> float:
    poles = max(int(getattr(cfg, 'motor_poles', 14) or 14), 2)
    return float(erpm) / 60.0 / max(poles / 2.0, 1.0)


def _estimate_fs(df: pd.DataFrame) -> float:
    if 'time_s' not in df.columns or len(df) < 2:
        return 2000.0
    dt = np.diff(df['time_s'].to_numpy(dtype=np.float64))
    dt = dt[dt > 1e-6]
    return float(1.0 / np.median(dt)) if len(dt) else 2000.0


def _fly_mask(df: pd.DataFrame) -> np.ndarray:
    if 'rcCommand[3]' in df.columns:
        v = df['rcCommand[3]'].to_numpy(dtype=np.float64)
        m = v > 1100
        if m.sum() > 200:
            return m
    if 'motor[0]' in df.columns:
        v = df['motor[0]'].to_numpy(dtype=np.float64)
        vv = v[v > 0]
        if len(vv):
            thr = float(np.percentile(vv, 2)) + 0.15 * (float(np.percentile(vv, 99)) - float(np.percentile(vv, 2)))
            return v > thr
    return np.ones(len(df), dtype=bool)


def _avg_erpm(df: pd.DataFrame, fly_mask: np.ndarray) -> list[float]:
    rpms = []
    for i in range(4):
        col = f'eRPM[{i}]'
        if col in df.columns:
            v = df[col].to_numpy(dtype=np.float64)[fly_mask]
            rpms.append(float(np.median(v[v > 100])) if (v > 100).any() else 0.0)
    return rpms


# ---------------------------------------------------------------------------
# Widget principal
# ---------------------------------------------------------------------------

class FftWidget(QWidget):
    def __init__(self, df: pd.DataFrame, cfg: FlightConfig):
        super().__init__()
        self.df  = df
        self.cfg = cfg
        self.fs  = _estimate_fs(df)
        self.fly = _fly_mask(df)
        self.avg_erpm = _avg_erpm(df, self.fly)

        tabs = QTabWidget()
        tabs.addTab(self._build_spectrum_tab(), "Vibrations")
        tabs.addTab(self._build_spectrogram_tab(), "Carte temps/fréquences")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(tabs)

    # ------------------------------------------------------------------
    # Onglet Spectre
    # ------------------------------------------------------------------

    def _build_spectrum_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(4)

        # Barre de cases
        bar = QHBoxLayout()
        title = QLabel("Vibrations - fréquences, résonances et harmoniques moteur")
        title.setStyleSheet("color:#e0e0e0; font-size:15px; font-weight:bold; padding:2px 8px;")
        bar.addWidget(title)
        self._checks: dict[str, QCheckBox] = {}
        for label, color in [('Roll', ROLL_COLOR), ('Pitch', PITCH_COLOR), ('Yaw', YAW_COLOR)]:
            cb = QCheckBox(label)
            cb.setChecked(True)
            cb.setStyleSheet(f"color:{color}; font-weight:bold;")
            cb.stateChanged.connect(self._update_visibility)
            bar.addWidget(cb)
            self._checks[label] = cb
        cb_raw = QCheckBox("Brut (tirets)")
        cb_raw.setChecked(True)
        cb_raw.setStyleSheet("color:#888;")
        cb_raw.stateChanged.connect(self._update_visibility)
        bar.addWidget(cb_raw)
        self._checks['Brut'] = cb_raw
        bar.addStretch()
        layout.addLayout(bar)

        # Légende filtres
        legend = self._filter_legend()
        if legend:
            layout.addWidget(legend)

        # Plot
        self._psd_plot = pg.PlotWidget()
        self._psd_plot.setLabel('bottom', 'Fréquence (Hz)')
        self._psd_plot.setLabel('left', 'Puissance (dB)')
        self._psd_plot.showGrid(x=True, y=True, alpha=0.2)
        self._psd_plot.setXRange(0, MAX_FFT_HZ)
        layout.addWidget(self._psd_plot)

        self._psd_curves: dict[str, pg.PlotDataItem] = {}
        self._draw_filter_lines()
        self._draw_rpm_lines()
        self._draw_spectra()

        return widget

    def _draw_spectra(self):
        t = self.df['time_s'].to_numpy(dtype=np.float64)
        for ax, (name, color) in enumerate(zip(AXIS_NAMES, AXIS_COLORS)):
            for is_raw in (False, True):
                col = f'gyroUnfilt[{ax}]' if is_raw else f'gyroADC[{ax}]'
                if col not in self.df.columns:
                    continue
                sig = self.df[col].to_numpy(dtype=np.float64)[self.fly]
                if len(sig) < 512:
                    continue
                freqs, psd = _welch(sig, self.fs)
                mask = freqs <= MAX_FFT_HZ
                db = _db(psd[mask])

                if is_raw:
                    pen = pg.mkPen(color, width=1, style=Qt.PenStyle.DashLine, alpha=100)
                    key = f'Brut_{name}'
                else:
                    pen = pg.mkPen(color, width=1.5)
                    key = name

                curve = self._psd_plot.plot(freqs[mask], db, pen=pen, name=key)
                curve.setVisible(not is_raw or self._checks['Brut'].isChecked())
                self._psd_curves[key] = curve
                if not is_raw:
                    self._draw_resonance_labels(freqs[mask], db, color, name)

    def _draw_resonance_labels(self, freqs: np.ndarray, db: np.ndarray,
                               color: str, axis_name: str):
        band = (freqs >= 80) & (freqs <= 600)
        if not band.any():
            return
        bf = freqs[band]
        bd = db[band]
        floor = float(np.percentile(bd, 65))
        candidates = []
        for i in range(2, len(bd) - 2):
            if bd[i] <= floor + 6:
                continue
            if bd[i] >= bd[i - 1] and bd[i] >= bd[i + 1]:
                candidates.append((float(bd[i]), float(bf[i])))
        for _power, hz in sorted(candidates, reverse=True)[:3]:
            line = pg.InfiniteLine(
                pos=hz, angle=90,
                pen=pg.mkPen(color, width=1, style=Qt.PenStyle.DotLine, alpha=90),
                label=f'{axis_name} réso {hz:.0f}Hz',
                labelOpts={'color': color, 'position': 0.18}
            )
            self._psd_plot.addItem(line)

    def _draw_filter_lines(self):
        cfg = self.cfg
        filters = []
        if cfg.gyro_lpf1_hz and cfg.gyro_lpf1_hz > 0:
            filters.append((cfg.gyro_lpf1_hz, '#888', 'Gyro LPF1'))
        if cfg.gyro_lpf2_hz and cfg.gyro_lpf2_hz > 0:
            filters.append((cfg.gyro_lpf2_hz, '#666', 'Gyro LPF2'))
        if cfg.dterm_lpf1_hz and cfg.dterm_lpf1_hz > 0:
            filters.append((cfg.dterm_lpf1_hz, '#9b59b6', 'D LPF1'))
        if cfg.dterm_lpf2_hz and cfg.dterm_lpf2_hz > 0:
            filters.append((cfg.dterm_lpf2_hz, '#7d3c98', 'D LPF2'))

        for hz, color, label in filters:
            if hz <= MAX_FFT_HZ:
                line = pg.InfiniteLine(
                    pos=hz, angle=90,
                    pen=pg.mkPen(color, width=1, style=Qt.PenStyle.DotLine),
                    label=label, labelOpts={'color': color, 'position': 0.95}
                )
                self._psd_plot.addItem(line)

    def _draw_rpm_lines(self):
        if not self.avg_erpm or not self.cfg.dshot_bidir:
            return
        rpms = [r for r in self.avg_erpm if r > 500]
        if not rpms:
            return
        avg = float(np.mean(rpms))
        fund_hz = _erpm_to_motor_hz(avg, self.cfg)

        for h in range(1, self.cfg.rpm_filter_harmonics + 1):
            hz = fund_hz * h
            if hz > MAX_FFT_HZ:
                break
            line = pg.InfiniteLine(
                pos=hz, angle=90,
                pen=pg.mkPen('#f39c12', width=1, style=Qt.PenStyle.DashLine, alpha=120),
                label=f'Moteur ×{h}' if h <= 4 else '',
                labelOpts={'color': '#f39c12', 'position': 0.85 - h * 0.05}
            )
            self._psd_plot.addItem(line)

    def _filter_legend(self) -> QLabel | None:
        parts = []
        if self.cfg.dterm_lpf1_hz:
            parts.append(f"D LPF1={self.cfg.dterm_lpf1_hz}Hz")
        if self.cfg.dterm_lpf2_hz:
            parts.append(f"D LPF2={self.cfg.dterm_lpf2_hz}Hz")

        if self.cfg.dshot_bidir and self.avg_erpm:
            valid = [r for r in self.avg_erpm if r > 0]
            if valid:
                avg_erpm = float(np.mean(valid))
                fund_hz  = _erpm_to_motor_hz(avg_erpm, self.cfg)
                if fund_hz > MAX_FFT_HZ:
                    parts.append(
                        f"Harmoniques moteur : fondamentale ~{fund_hz:.0f}Hz "
                        f"(hors fenêtre — pics 0-{MAX_FFT_HZ}Hz = résonances mécaniques)"
                    )
                else:
                    parts.append(
                        f"Harmoniques moteur ~{fund_hz:.0f}Hz fond. "
                        f"({self.cfg.rpm_filter_harmonics} harmoniques)"
                    )

        if not parts:
            return None
        lbl = QLabel("  |  ".join(parts))
        lbl.setStyleSheet("color:#888; font-size:10px; padding:2px 4px;")
        return lbl

    def _update_visibility(self):
        for ax, name in enumerate(AXIS_NAMES):
            v = self._checks.get(name, None)
            if v is None:
                continue
            if name in self._psd_curves:
                self._psd_curves[name].setVisible(v.isChecked())
            raw_key = f'Brut_{name}'
            if raw_key in self._psd_curves:
                self._psd_curves[raw_key].setVisible(
                    v.isChecked() and self._checks['Brut'].isChecked()
                )

    # ------------------------------------------------------------------
    # Onglet Carte temps/fréquences Roll
    # ------------------------------------------------------------------

    def _build_spectrogram_tab(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 4, 4, 4)

        col = 'gyroADC[0]'
        if col not in self.df.columns:
            layout.addWidget(QLabel("Données gyro indisponibles."))
            return widget

        layout.addWidget(QLabel(
            "Carte temps/fréquences Roll — évolution des vibrations dans le temps. "
            "Axe X = temps, axe Y = fréquence (Hz), couleur = puissance.",
            wordWrap=True
        ))

        plot = pg.PlotWidget()
        plot.setLabel('left', 'Fréquence (Hz)')
        plot.setLabel('bottom', 'Temps (s)')

        img = self._compute_spectrogram(col)
        if img is not None:
            arr, t_range, f_range = img
            item = pg.ImageItem(image=arr)
            item.setRect(pg.QtCore.QRectF(
                float(t_range[0]), 0,
                float(t_range[1] - t_range[0]),
                float(f_range)
            ))
            # Colormap chaud
            cm = pg.colormap.get('inferno')
            item.setColorMap(cm)
            plot.addItem(item)
            plot.setYRange(0, min(f_range, MAX_FFT_HZ))

        layout.addWidget(plot)
        return widget

    def _compute_spectrogram(self, col: str):
        sig  = self.df[col].to_numpy(dtype=np.float64)
        t    = self.df['time_s'].to_numpy(dtype=np.float64)
        if len(sig) < 1024:
            return None

        # Sous-échantillonnage si trop long (max 60 000 points pour le spectro)
        target = 60_000
        if len(sig) > target:
            step = len(sig) // target
            sig  = sig[::step]
            t    = t[::step]
            fs   = self.fs / step
        else:
            fs   = self.fs

        nperseg = min(512, len(sig) // 20)
        if nperseg < 64:
            return None

        step    = nperseg // 2
        hann    = np.hanning(nperseg)
        freqs   = np.fft.rfftfreq(nperseg, 1.0 / fs)
        f_mask  = freqs <= MAX_FFT_HZ
        freqs   = freqs[f_mask]

        specs = []
        times = []
        for start in range(0, len(sig) - nperseg, step):
            seg   = sig[start:start + nperseg] * hann
            power = np.abs(np.fft.rfft(seg)) ** 2
            specs.append(_db(power[f_mask]))
            times.append(float(t[start + nperseg // 2]))

        if not specs:
            return None

        arr = np.array(specs).T   # shape: (freq_bins, time_bins)
        # Normalise pour l'affichage
        arr -= arr.min()
        mx = arr.max()
        if mx > 0:
            arr /= mx

        return arr, (times[0], times[-1]), float(freqs[-1])
