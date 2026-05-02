import sys
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from analysis.analyzer import (  # noqa: E402
    AxisAnalysis,
    SessionAnalysis,
    _erpm_to_motor_hz,
    _fill_pid_balance,
    _fly_mask,
    _guess_cell_count,
)
from analysis.header_parser import FlightConfig  # noqa: E402
from analysis.recommender import DiagnosticReport, Recommendation, Severity  # noqa: E402


class AnalyzerRegressionTests(unittest.TestCase):
    def test_low_throttle_flip_stays_in_fly_mask(self):
        n = 1000
        t = np.arange(n) / 1000.0
        df = pd.DataFrame({
            "time_s": t,
            "rcCommand[3]": np.full(n, 1000.0),
            "gyroADC[0]": np.zeros(n),
            "gyroADC[1]": np.zeros(n),
            "gyroADC[2]": np.zeros(n),
            "setpoint[0]": np.zeros(n),
            "setpoint[1]": np.zeros(n),
            "setpoint[2]": np.zeros(n),
            "motor[0]": np.full(n, 1050.0),
            "motor[1]": np.full(n, 1050.0),
            "motor[2]": np.full(n, 1050.0),
            "motor[3]": np.full(n, 1050.0),
        })
        df.loc[430:560, "setpoint[1]"] = 520.0
        df.loc[430:560, "gyroADC[1]"] = 480.0
        mask = _fly_mask(df)
        self.assertTrue(mask[450:540].all())

    def test_liion_6s_low_voltage_not_classified_as_4s(self):
        self.assertEqual(_guess_cell_count(17.0, 18.0), 6)

    def test_erpm_uses_motor_poles(self):
        cfg = FlightConfig(motor_poles=14)
        self.assertAlmostEqual(_erpm_to_motor_hz(42000, cfg), 100.0)

    def test_pid_balance_reads_blackbox_pid_traces(self):
        n = 200
        df = pd.DataFrame({
            "gyroADC[0]": np.full(n, 180.0),
            "setpoint[0]": np.full(n, 220.0),
            "axisP[0]": np.full(n, 100.0),
            "axisI[0]": np.full(n, 30.0),
            "axisD[0]": np.full(n, 55.0),
            "axisF[0]": np.full(n, 80.0),
        })
        aa = AxisAnalysis(axis=0, name="Roll")
        _fill_pid_balance(aa, df, np.ones(n, dtype=bool))

        self.assertAlmostEqual(aa.pid_balance.d_to_p_ratio, 0.55)
        self.assertEqual(aa.pid_balance.verdict, "OK")


class RecommenderRegressionTests(unittest.TestCase):
    def test_raw_cli_dedupes_duplicate_params(self):
        report = DiagnosticReport()
        report.recommendations = [
            Recommendation("p_roll", 70, 60, Severity.INFO, "small"),
            Recommendation("p_roll", 70, 52, Severity.WARNING, "large"),
        ]
        cli = report.cli_dump()
        self.assertEqual(cli.count("set p_roll"), 1)
        self.assertIn("set p_roll = 52", cli)

    def test_low_throttle_rebound_affects_health(self):
        aa = AxisAnalysis(axis=1, name="Pitch", low_throttle_rebound_score=0.6)
        session = SessionAnalysis(axes=[aa])
        from analysis.recommender import compute_health_score

        self.assertLess(compute_health_score(session), 100)


class HeaderRegressionTests(unittest.TestCase):
    def test_size_hint_recognizes_pouce(self):
        cfg = FlightConfig(craft_name="6pouceTMOTORVELOXF7SE")
        self.assertEqual(cfg.size_hint(), '6"')


if __name__ == "__main__":
    unittest.main()
