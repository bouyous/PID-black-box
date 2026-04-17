import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

# Champs voulus — noms APRÈS normalisation (_strip_unit enlève les suffixes d'unité).
# 'time (us)' devient 'time', 'gyroADC[0] (deg/s)' devient 'gyroADC[0]', etc.
WANTED_FIELDS = [
    'time',
    'gyroADC[0]', 'gyroADC[1]', 'gyroADC[2]',
    'gyroUnfilt[0]', 'gyroUnfilt[1]', 'gyroUnfilt[2]',
    'rcCommand[0]', 'rcCommand[1]', 'rcCommand[2]', 'rcCommand[3]',
    'setpoint[0]', 'setpoint[1]', 'setpoint[2]',
    'axisP[0]', 'axisP[1]', 'axisP[2]',
    'axisI[0]', 'axisI[1]', 'axisI[2]',
    'axisD[0]', 'axisD[1]', 'axisD[2]',
    'axisF[0]', 'axisF[1]', 'axisF[2]',
    'motor[0]', 'motor[1]', 'motor[2]', 'motor[3]',
    'eRPM[0]', 'eRPM[1]', 'eRPM[2]', 'eRPM[3]',
    'vbatLatest', 'amperageLatest',
]

MIN_ROWS = 50  # sessions avec moins de points = vides/corrompues, ignorées

_UNIT_RE = re.compile(r'\s*\([^)]+\)$')


def _strip_unit(name: str) -> str:
    """'gyroADC[0] (deg/s)' → 'gyroADC[0]'"""
    return _UNIT_RE.sub('', name).strip()


def find_decoder() -> Path | None:
    """Cherche blackbox_decode.exe dans tools/ puis dans le PATH."""
    tools_dir = Path(__file__).resolve().parent.parent.parent / 'tools'
    local = tools_dir / 'blackbox_decode.exe'
    if local.exists():
        return local
    found = shutil.which('blackbox_decode') or shutil.which('blackbox_decode.exe')
    return Path(found) if found else None


class BlackboxParser:
    def __init__(self, decoder_path: Path | None = None):
        self.decoder = decoder_path or find_decoder()

    def is_ready(self) -> bool:
        return self.decoder is not None and Path(self.decoder).exists()

    def decode(self, bbl_path: str | Path) -> list[pd.DataFrame]:
        """Décode un fichier .bbl/.bfl et retourne une DataFrame par session valide."""
        if not self.is_ready():
            raise FileNotFoundError(
                "blackbox_decode.exe introuvable.\n"
                "Placez-le dans le dossier tools/ du projet.\n"
                "(Source : PIDtoolboxPro_v0.81_win/main/blackbox_decode.exe)"
            )

        bbl_path = Path(bbl_path)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_bbl = Path(tmpdir) / bbl_path.name
            shutil.copy2(bbl_path, tmp_bbl)

            result = subprocess.run(
                [
                    str(self.decoder),
                    '--unit-rotation', 'deg/s',
                    '--unit-vbat', 'V',
                    '--unit-amperage', 'A',
                    str(tmp_bbl),
                ],
                capture_output=True,
                text=True,
                cwd=tmpdir,
            )

            # returncode != 0 n'est pas toujours fatal (sessions partiellement corrompues)
            # On lit ce qui a été généré quoi qu'il arrive

            csv_files = sorted(Path(tmpdir).glob(f"{bbl_path.stem}.*.csv"))
            if not csv_files:
                csv_files = sorted(Path(tmpdir).glob(f"{bbl_path.stem}.csv"))

            sessions = [self._read_csv(f) for f in csv_files]
            sessions = [df for df in sessions if df is not None]

        if not sessions:
            detail = result.stderr or result.stdout or "pas de détail"
            raise ValueError(
                f"Aucune session de vol valide trouvée dans ce fichier.\n{detail}"
            )

        return sessions

    def _read_csv(self, csv_path: Path) -> pd.DataFrame | None:
        try:
            df = pd.read_csv(csv_path, skipinitialspace=True)
        except Exception:
            return None

        # Normalise les noms : retire les suffixes d'unité entre parenthèses
        df.columns = [_strip_unit(c) for c in df.columns]

        if 'time' not in df.columns or len(df) < MIN_ROWS:
            return None

        keep = [c for c in WANTED_FIELDS if c in df.columns]
        df = df[keep].copy()

        df['time_s'] = (df['time'] - df['time'].iloc[0]) / 1_000_000.0

        for col in df.columns:
            if col != 'time_s':
                df[col] = pd.to_numeric(df[col], errors='coerce')

        return df
