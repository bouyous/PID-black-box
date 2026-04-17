import numpy as np
import pandas as pd
import pyqtgraph as pg
from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

pg.setConfigOption('background', '#1e1e1e')
pg.setConfigOption('foreground', '#aaaaaa')

# Au-delà de ce seuil, on sous-échantillonne pour la fluidité
MAX_DISPLAY_POINTS = 200_000


def _downsample(t: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Sous-échantillonnage simple par décimation si trop de points."""
    n = len(t)
    if n <= MAX_DISPLAY_POINTS:
        return t, y
    step = n // MAX_DISPLAY_POINTS
    return t[::step], y[::step]


def _make_plot() -> pg.PlotWidget:
    p = pg.PlotWidget()
    p.showGrid(x=True, y=True, alpha=0.2)
    p.addLegend(offset=(10, 10))
    return p


# ---------------------------------------------------------------------------
# Gyroscope
# ---------------------------------------------------------------------------

GYRO_AXES = [
    ('Roll',  'gyroADC[0]', '#e74c3c'),
    ('Pitch', 'gyroADC[1]', '#2ecc71'),
    ('Yaw',   'gyroADC[2]', '#3498db'),
]
GYRO_UNFILT_AXES = [
    ('Roll brut',  'gyroUnfilt[0]', '#e74c3c'),
    ('Pitch brut', 'gyroUnfilt[1]', '#2ecc71'),
    ('Yaw brut',   'gyroUnfilt[2]', '#3498db'),
]


class GyroPlotWidget(QWidget):
    def __init__(self, df: pd.DataFrame):
        super().__init__()
        self.df = df
        self.curves: dict[str, pg.PlotDataItem] = {}
        self._build_ui()
        self._plot()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        toggle_bar = QHBoxLayout()
        self.checks: dict[str, QCheckBox] = {}

        for label, _, color in GYRO_AXES:
            cb = QCheckBox(label)
            cb.setChecked(True)
            cb.setStyleSheet(f"color: {color}; font-weight: bold;")
            cb.stateChanged.connect(self._update_visibility)
            toggle_bar.addWidget(cb)
            self.checks[label] = cb

        # Gyro non filtré en option (tirets)
        for label, _, color in GYRO_UNFILT_AXES:
            cb = QCheckBox(label)
            cb.setChecked(False)
            cb.setStyleSheet(f"color: {color};")
            cb.stateChanged.connect(self._update_visibility)
            toggle_bar.addWidget(cb)
            self.checks[label] = cb

        toggle_bar.addStretch()
        layout.addLayout(toggle_bar)

        self.plot = _make_plot()
        self.plot.setLabel('left', 'Gyro (deg/s)')
        self.plot.setLabel('bottom', 'Temps (s)')
        layout.addWidget(self.plot)

    def _plot(self):
        t = self.df['time_s'].to_numpy(dtype=np.float64)

        for label, field, color in GYRO_AXES:
            if field not in self.df.columns:
                continue
            y = self.df[field].to_numpy(dtype=np.float64)
            td, yd = _downsample(t, y)
            curve = self.plot.plot(td, yd, pen=pg.mkPen(color, width=1), name=label)
            self.curves[label] = curve

        for label, field, color in GYRO_UNFILT_AXES:
            if field not in self.df.columns:
                continue
            y = self.df[field].to_numpy(dtype=np.float64)
            td, yd = _downsample(t, y)
            pen = pg.mkPen(color, width=1, style=pg.QtCore.Qt.PenStyle.DashLine)
            curve = self.plot.plot(td, yd, pen=pen, name=label)
            curve.setVisible(False)
            self.curves[label] = curve

    def _update_visibility(self):
        for label, cb in self.checks.items():
            if label in self.curves:
                self.curves[label].setVisible(cb.isChecked())


# ---------------------------------------------------------------------------
# PID (P, I, D, F pour un axe)
# ---------------------------------------------------------------------------

class PidPlotWidget(QWidget):
    TERMS = [
        ('P', '#f39c12'),
        ('I', '#9b59b6'),
        ('D', '#1abc9c'),
        ('F', '#e67e22'),
    ]

    def __init__(self, df: pd.DataFrame, axis_index: int, axis_name: str):
        super().__init__()
        self.df = df
        self.axis_index = axis_index
        self.axis_name = axis_name
        self.curves: dict[str, pg.PlotDataItem] = {}
        self._build_ui()
        self._plot()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        toggle_bar = QHBoxLayout()
        self.checks: dict[str, QCheckBox] = {}
        for term, color in self.TERMS:
            field = f'axis{term}[{self.axis_index}]'
            if field not in self.df.columns:
                continue
            cb = QCheckBox(term)
            cb.setChecked(True)
            cb.setStyleSheet(f"color: {color}; font-weight: bold;")
            cb.stateChanged.connect(self._update_visibility)
            toggle_bar.addWidget(cb)
            self.checks[term] = cb

        # Setpoint en pointillés
        sp_field = f'setpoint[{self.axis_index}]'
        if sp_field in self.df.columns:
            cb = QCheckBox('Setpoint')
            cb.setChecked(False)
            cb.setStyleSheet("color: #ffffff;")
            cb.stateChanged.connect(self._update_visibility)
            toggle_bar.addWidget(cb)
            self.checks['Setpoint'] = cb

        toggle_bar.addStretch()
        layout.addLayout(toggle_bar)

        self.plot = _make_plot()
        self.plot.setLabel('left', f'PID {self.axis_name}')
        self.plot.setLabel('bottom', 'Temps (s)')
        layout.addWidget(self.plot)

    def _plot(self):
        t = self.df['time_s'].to_numpy(dtype=np.float64)
        i = self.axis_index

        for term, color in self.TERMS:
            field = f'axis{term}[{i}]'
            if field not in self.df.columns:
                continue
            y = self.df[field].to_numpy(dtype=np.float64)
            td, yd = _downsample(t, y)
            curve = self.plot.plot(td, yd, pen=pg.mkPen(color, width=1), name=term)
            self.curves[term] = curve

        sp_field = f'setpoint[{i}]'
        if sp_field in self.df.columns:
            y = self.df[sp_field].to_numpy(dtype=np.float64)
            td, yd = _downsample(t, y)
            pen = pg.mkPen('#ffffff', width=1, style=pg.QtCore.Qt.PenStyle.DashLine)
            curve = self.plot.plot(td, yd, pen=pen, name='Setpoint')
            curve.setVisible(False)
            self.curves['Setpoint'] = curve

    def _update_visibility(self):
        for label, cb in self.checks.items():
            if label in self.curves:
                self.curves[label].setVisible(cb.isChecked())


# ---------------------------------------------------------------------------
# Moteurs
# ---------------------------------------------------------------------------

MOTOR_COLORS = ['#e74c3c', '#2ecc71', '#3498db', '#f39c12']


class MotorPlotWidget(QWidget):
    def __init__(self, df: pd.DataFrame):
        super().__init__()
        self.df = df
        self.curves: dict[str, pg.PlotDataItem] = {}
        self._build_ui()
        self._plot()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)

        toggle_bar = QHBoxLayout()
        self.checks: dict[str, QCheckBox] = {}

        for i, color in enumerate(MOTOR_COLORS):
            for prefix, suffix in [('M', 'motor'), ('RPM', 'eRPM')]:
                label = f'{prefix}{i + 1}'
                field = f'{suffix}[{i}]'
                if field not in self.df.columns:
                    continue
                cb = QCheckBox(label)
                cb.setChecked(prefix == 'M')
                cb.setStyleSheet(f"color: {color}; {'font-weight: bold;' if prefix == 'M' else ''}")
                cb.stateChanged.connect(self._update_visibility)
                toggle_bar.addWidget(cb)
                self.checks[label] = cb

        toggle_bar.addStretch()
        layout.addLayout(toggle_bar)

        self.plot_motor = _make_plot()
        self.plot_motor.setLabel('left', 'Moteur (DSHOT)')
        self.plot_motor.setLabel('bottom', 'Temps (s)')

        self.plot_rpm = _make_plot()
        self.plot_rpm.setLabel('left', 'eRPM')
        self.plot_rpm.setLabel('bottom', 'Temps (s)')
        self.plot_rpm.setXLink(self.plot_motor)

        layout.addWidget(QLabel("Valeurs moteur (DSHOT)"))
        layout.addWidget(self.plot_motor, stretch=1)
        layout.addWidget(QLabel("RPM électronique"))
        layout.addWidget(self.plot_rpm, stretch=1)

    def _plot(self):
        t = self.df['time_s'].to_numpy(dtype=np.float64)

        for i, color in enumerate(MOTOR_COLORS):
            field_m = f'motor[{i}]'
            field_r = f'eRPM[{i}]'
            label_m = f'M{i + 1}'
            label_r = f'RPM{i + 1}'

            if field_m in self.df.columns:
                y = self.df[field_m].to_numpy(dtype=np.float64)
                td, yd = _downsample(t, y)
                c = self.plot_motor.plot(td, yd, pen=pg.mkPen(color, width=1), name=label_m)
                self.curves[label_m] = c

            if field_r in self.df.columns:
                y = self.df[field_r].to_numpy(dtype=np.float64)
                td, yd = _downsample(t, y)
                pen = pg.mkPen(color, width=1, style=pg.QtCore.Qt.PenStyle.DashLine)
                c = self.plot_rpm.plot(td, yd, pen=pen, name=label_r)
                c.setVisible(False)
                self.curves[label_r] = c

    def _update_visibility(self):
        for label, cb in self.checks.items():
            if label in self.curves:
                self.curves[label].setVisible(cb.isChecked())
