"""
Widgets de visualisation — inspirés de Blackbox Explorer.
Principe : chaque signal dans sa propre lane, axes X synchronisés.
"""
import numpy as np
import pandas as pd
import pyqtgraph as pg
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

pg.setConfigOption('background', '#1a1a1a')
pg.setConfigOption('foreground', '#cccccc')

MAX_DISPLAY_POINTS = 150_000

ROLL_COLOR  = '#e74c3c'
PITCH_COLOR = '#2ecc71'
YAW_COLOR   = '#3498db'
AXIS_COLORS = [ROLL_COLOR, PITCH_COLOR, YAW_COLOR]
AXIS_NAMES  = ['Roll', 'Pitch', 'Yaw']

MOTOR_COLORS = ['#e74c3c', '#2ecc71', '#3498db', '#f39c12']


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _decimate(t: np.ndarray, y: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    n = len(t)
    if n <= MAX_DISPLAY_POINTS:
        return t, y
    step = max(1, n // MAX_DISPLAY_POINTS)
    return t[::step], y[::step]


def _lane(title: str, unit: str, color: str, height: int = 160) -> pg.PlotWidget:
    """Crée une 'lane' style Blackbox Explorer."""
    p = pg.PlotWidget()
    p.setFixedHeight(height)
    p.setLabel('left', title, units=unit, color=color)
    p.getAxis('left').setWidth(70)
    p.showGrid(x=True, y=True, alpha=0.15)
    p.getPlotItem().setContentsMargins(0, 0, 0, 0)
    p.setMenuEnabled(False)
    return p


def _link_x(plots: list[pg.PlotWidget]):
    """Synchronise l'axe X de toutes les lanes."""
    for p in plots[1:]:
        p.setXLink(plots[0])
    for p in plots[:-1]:
        p.getAxis('bottom').setStyle(showValues=False)
    plots[-1].setLabel('bottom', 'Temps (s)')


def _toggle_bar(*items: tuple[str, str, bool]) -> tuple[QWidget, dict[str, QCheckBox]]:
    """Barre de cases à cocher. items = (label, color, checked)."""
    bar = QWidget()
    bar.setFixedHeight(30)
    layout = QHBoxLayout(bar)
    layout.setContentsMargins(4, 2, 4, 2)
    layout.setSpacing(12)
    checks = {}
    for label, color, checked in items:
        cb = QCheckBox(label)
        cb.setChecked(checked)
        cb.setStyleSheet(f"color: {color}; font-size: 12px;")
        layout.addWidget(cb)
        checks[label] = cb
    layout.addStretch()
    return bar, checks


# ---------------------------------------------------------------------------
# Widget gyroscope — 2 lanes séparées (filtré / brut)
# ---------------------------------------------------------------------------

class GyroPlotWidget(QWidget):
    def __init__(self, df: pd.DataFrame):
        super().__init__()
        self.df = df
        self.curves: dict[str, pg.PlotDataItem] = {}
        self._build_ui()
        self._plot()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Barre d'options
        bar, self.checks = _toggle_bar(
            ('Roll',       ROLL_COLOR,  True),
            ('Pitch',      PITCH_COLOR, True),
            ('Yaw',        YAW_COLOR,   True),
            ('Brut Roll',  ROLL_COLOR,  False),
            ('Brut Pitch', PITCH_COLOR, False),
            ('Brut Yaw',   YAW_COLOR,   False),
        )
        for label in ('Brut Roll', 'Brut Pitch', 'Brut Yaw'):
            self.checks[label].setStyleSheet(
                self.checks[label].styleSheet() + ' font-style: italic;'
            )
        layout.addWidget(bar)

        # Lane gyro filtré
        self.lane_filt = _lane('Gyro filtré', 'deg/s', '#aaa', height=200)
        layout.addWidget(self.lane_filt)

        # Lane gyro brut (masquée par défaut)
        self.lane_raw = _lane('Gyro brut', 'deg/s', '#888', height=160)
        self.lane_raw.setVisible(False)
        layout.addWidget(self.lane_raw)

        _link_x([self.lane_filt, self.lane_raw])

        for label in ('Brut Roll', 'Brut Pitch', 'Brut Yaw'):
            self.checks[label].stateChanged.connect(self._on_raw_toggle)
        for label in ('Roll', 'Pitch', 'Yaw'):
            self.checks[label].stateChanged.connect(self._update_visibility)

    def _plot(self):
        t = self.df['time_s'].to_numpy(dtype=np.float64)

        filt_pairs = [
            ('Roll',  'gyroADC[0]', ROLL_COLOR),
            ('Pitch', 'gyroADC[1]', PITCH_COLOR),
            ('Yaw',   'gyroADC[2]', YAW_COLOR),
        ]
        raw_pairs = [
            ('Brut Roll',  'gyroUnfilt[0]', ROLL_COLOR),
            ('Brut Pitch', 'gyroUnfilt[1]', PITCH_COLOR),
            ('Brut Yaw',   'gyroUnfilt[2]', YAW_COLOR),
        ]

        for label, field, color in filt_pairs:
            if field not in self.df.columns:
                continue
            y = self.df[field].to_numpy(dtype=np.float64)
            td, yd = _decimate(t, y)
            c = self.lane_filt.plot(td, yd, pen=pg.mkPen(color, width=1), name=label)
            self.curves[label] = c

        for label, field, color in raw_pairs:
            if field not in self.df.columns:
                continue
            y = self.df[field].to_numpy(dtype=np.float64)
            td, yd = _decimate(t, y)
            pen = pg.mkPen(color, width=1, style=Qt.PenStyle.DashLine)
            c = self.lane_raw.plot(td, yd, pen=pen, name=label)
            c.setVisible(self.checks[label].isChecked())
            self.curves[label] = c

    def _on_raw_toggle(self):
        any_raw = any(
            self.checks[l].isChecked()
            for l in ('Brut Roll', 'Brut Pitch', 'Brut Yaw')
        )
        self.lane_raw.setVisible(any_raw)
        self._update_visibility()

    def _update_visibility(self):
        for label, cb in self.checks.items():
            if label in self.curves:
                self.curves[label].setVisible(cb.isChecked())


# ---------------------------------------------------------------------------
# Widget PID — une lane par terme (P / I / D / F)
# ---------------------------------------------------------------------------

TERM_COLORS = {'P': '#f39c12', 'I': '#9b59b6', 'D': '#1abc9c', 'F': '#e67e22'}
TERM_UNITS  = {'P': '', 'I': '', 'D': '', 'F': ''}


class PidPlotWidget(QWidget):
    def __init__(self, df: pd.DataFrame, axis_index: int, axis_name: str):
        super().__init__()
        self.df = df
        self.axis_index = axis_index
        self.axis_name = axis_name
        self.lanes: dict[str, pg.PlotWidget] = {}
        self.curves: dict[str, pg.PlotDataItem] = {}
        self._build_ui()
        self._plot()

    def _build_ui(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(scroll.Shape.NoFrame)

        inner = QWidget()
        self.inner_layout = QVBoxLayout(inner)
        self.inner_layout.setContentsMargins(0, 0, 0, 0)
        self.inner_layout.setSpacing(0)

        i = self.axis_index
        toggle_items = []
        available_terms = []

        for term in ('P', 'I', 'D', 'F'):
            field = f'axis{term}[{i}]'
            if field in self.df.columns:
                available_terms.append(term)
                toggle_items.append((term, TERM_COLORS[term], True))

        # Setpoint
        sp_field = f'setpoint[{i}]'
        if sp_field in self.df.columns:
            toggle_items.append(('Setpoint', '#ffffff', False))

        bar, self.checks = _toggle_bar(*toggle_items)
        self.inner_layout.addWidget(bar)

        # Une lane par terme
        all_lanes = []
        for term in available_terms:
            lane = _lane(f'{term} {self.axis_name}', '', TERM_COLORS[term], height=150)
            self.lanes[term] = lane
            self.inner_layout.addWidget(lane)
            all_lanes.append(lane)

        # Lane setpoint + gyro (superposés sur la même lane)
        if sp_field in self.df.columns or f'gyroADC[{i}]' in self.df.columns:
            lane_resp = _lane(f'Setpoint vs Gyro {self.axis_name}', 'deg/s', '#aaa', height=160)
            self.lanes['response'] = lane_resp
            self.inner_layout.addWidget(lane_resp)
            all_lanes.append(lane_resp)

        if all_lanes:
            _link_x(all_lanes)

        scroll.setWidget(inner)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _plot(self):
        t = self.df['time_s'].to_numpy(dtype=np.float64)
        i = self.axis_index

        for term, lane in self.lanes.items():
            if term == 'response':
                continue
            field = f'axis{term}[{i}]'
            if field not in self.df.columns:
                continue
            y = self.df[field].to_numpy(dtype=np.float64)
            td, yd = _decimate(t, y)
            c = lane.plot(td, yd, pen=pg.mkPen(TERM_COLORS[term], width=1), name=term)
            self.curves[term] = c

        # Lane setpoint vs gyro
        if 'response' in self.lanes:
            lane = self.lanes['response']
            sp_field = f'setpoint[{i}]'
            gy_field = f'gyroADC[{i}]'
            if sp_field in self.df.columns:
                y = self.df[sp_field].to_numpy(dtype=np.float64)
                td, yd = _decimate(t, y)
                c = lane.plot(td, yd, pen=pg.mkPen('#ffffff', width=1), name='Setpoint')
                c.setVisible(self.checks.get('Setpoint', QCheckBox()).isChecked())
                self.curves['Setpoint'] = c
            if gy_field in self.df.columns:
                color = AXIS_COLORS[i]
                y = self.df[gy_field].to_numpy(dtype=np.float64)
                td, yd = _decimate(t, y)
                c = lane.plot(td, yd, pen=pg.mkPen(color, width=1, alpha=180), name='Gyro')
                self.curves['Gyro'] = c

        for label, cb in self.checks.items():
            cb.stateChanged.connect(self._update_visibility)

    def _update_visibility(self):
        for label, cb in self.checks.items():
            if label in self.curves:
                self.curves[label].setVisible(cb.isChecked())


# ---------------------------------------------------------------------------
# Widget moteurs
# ---------------------------------------------------------------------------

class MotorPlotWidget(QWidget):
    def __init__(self, df: pd.DataFrame):
        super().__init__()
        self.df = df
        self.curves: dict[str, pg.PlotDataItem] = {}
        self._build_ui()
        self._plot()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        items = []
        for i, color in enumerate(MOTOR_COLORS):
            if f'motor[{i}]' in self.df.columns:
                items.append((f'M{i+1}', color, True))
        for i, color in enumerate(MOTOR_COLORS):
            if f'eRPM[{i}]' in self.df.columns:
                items.append((f'RPM{i+1}', color, False))

        bar, self.checks = _toggle_bar(*items)
        layout.addWidget(bar)

        self.lane_motor = _lane('Moteurs (DSHOT)', '', '#aaa', height=200)
        self.lane_rpm = _lane('eRPM', '', '#aaa', height=180)
        layout.addWidget(self.lane_motor)
        layout.addWidget(self.lane_rpm)
        _link_x([self.lane_motor, self.lane_rpm])

    def _plot(self):
        t = self.df['time_s'].to_numpy(dtype=np.float64)
        for i, color in enumerate(MOTOR_COLORS):
            for prefix, lane, field_tpl in [
                ('M',   self.lane_motor, f'motor[{i}]'),
                ('RPM', self.lane_rpm,   f'eRPM[{i}]'),
            ]:
                label = f'{prefix}{i+1}'
                if field_tpl not in self.df.columns:
                    continue
                y = self.df[field_tpl].to_numpy(dtype=np.float64)
                td, yd = _decimate(t, y)
                pen = pg.mkPen(color, width=1,
                               style=(Qt.PenStyle.DashLine if prefix == 'RPM'
                                      else Qt.PenStyle.SolidLine))
                c = lane.plot(td, yd, pen=pen, name=label)
                if prefix == 'RPM':
                    c.setVisible(False)
                self.curves[label] = c

        for label, cb in self.checks.items():
            cb.stateChanged.connect(self._update_visibility)

    def _update_visibility(self):
        for label, cb in self.checks.items():
            if label in self.curves:
                self.curves[label].setVisible(cb.isChecked())
