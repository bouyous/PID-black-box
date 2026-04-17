import numpy as np
import pandas as pd
import pyqtgraph as pg
from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QVBoxLayout, QWidget

AXIS_COLORS = {'Roll': '#e74c3c', 'Pitch': '#2ecc71', 'Yaw': '#3498db'}
GYRO_FIELDS = ['gyroADC[0]', 'gyroADC[1]', 'gyroADC[2]']
AXIS_LABELS = ['Roll', 'Pitch', 'Yaw']

pg.setConfigOption('background', '#1e1e1e')
pg.setConfigOption('foreground', '#aaaaaa')


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
        for axis in AXIS_LABELS:
            cb = QCheckBox(axis)
            cb.setChecked(True)
            cb.setStyleSheet(f"color: {AXIS_COLORS[axis]}; font-weight: bold;")
            cb.stateChanged.connect(self._update_visibility)
            toggle_bar.addWidget(cb)
            self.checks[axis] = cb
        toggle_bar.addStretch()
        layout.addLayout(toggle_bar)

        self.plot = pg.PlotWidget()
        self.plot.setLabel('left', 'Gyro (deg/s)')
        self.plot.setLabel('bottom', 'Temps (s)')
        self.plot.addLegend(offset=(10, 10))
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        layout.addWidget(self.plot)

    def _plot(self):
        t = self.df['time_s'].to_numpy(dtype=np.float64)
        for field, label in zip(GYRO_FIELDS, AXIS_LABELS):
            if field not in self.df.columns:
                continue
            y = self.df[field].to_numpy(dtype=np.float64)
            pen = pg.mkPen(color=AXIS_COLORS[label], width=1)
            curve = self.plot.plot(t, y, pen=pen, name=label)
            self.curves[label] = curve

    def _update_visibility(self):
        for label, cb in self.checks.items():
            if label in self.curves:
                self.curves[label].setVisible(cb.isChecked())


class PidPlotWidget(QWidget):
    """Affiche les termes P, I, D pour un axe donné."""

    TERM_COLORS = {'P': '#f39c12', 'I': '#9b59b6', 'D': '#1abc9c'}

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
        for term in ('P', 'I', 'D'):
            cb = QCheckBox(term)
            cb.setChecked(True)
            cb.setStyleSheet(f"color: {self.TERM_COLORS[term]}; font-weight: bold;")
            cb.stateChanged.connect(self._update_visibility)
            toggle_bar.addWidget(cb)
            self.checks[term] = cb
        toggle_bar.addStretch()
        layout.addLayout(toggle_bar)

        self.plot = pg.PlotWidget()
        self.plot.setLabel('left', f'PID {self.axis_name}')
        self.plot.setLabel('bottom', 'Temps (s)')
        self.plot.addLegend(offset=(10, 10))
        self.plot.showGrid(x=True, y=True, alpha=0.25)
        layout.addWidget(self.plot)

    def _plot(self):
        t = self.df['time_s'].to_numpy(dtype=np.float64)
        i = self.axis_index
        for term, field_prefix in (('P', 'axisP'), ('I', 'axisI'), ('D', 'axisD')):
            field = f'{field_prefix}[{i}]'
            if field not in self.df.columns:
                continue
            y = self.df[field].to_numpy(dtype=np.float64)
            pen = pg.mkPen(color=self.TERM_COLORS[term], width=1)
            curve = self.plot.plot(t, y, pen=pen, name=term)
            self.curves[term] = curve

    def _update_visibility(self):
        for term, cb in self.checks.items():
            if term in self.curves:
                self.curves[term].setVisible(cb.isChecked())
