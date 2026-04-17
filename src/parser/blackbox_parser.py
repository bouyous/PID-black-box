import shutil
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

WANTED_FIELDS = [
    'time (us)',
    'gyroADC[0]', 'gyroADC[1]', 'gyroADC[2]',
    'rcCommand[0]', 'rcCommand[1]', 'rcCommand[2]', 'rcCommand[3]',
    'axisP[0]', 'axisP[1]', 'axisP[2]',
    'axisI[0]', 'axisI[1]', 'axisI[2]',
    'axisD[0]', 'axisD[1]', 'axisD[2]',
    'motor[0]', 'motor[1]', 'motor[2]', 'motor[3]',
]


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
        """Décode un fichier .bbl/.bfl et retourne une DataFrame par session."""
        if not self.is_ready():
            raise FileNotFoundError(
                "blackbox_decode.exe introuvable.\n"
                "Téléchargez-le depuis https://github.com/betaflight/blackbox-tools/releases\n"
                "et placez-le dans le dossier tools/ du projet."
            )

        bbl_path = Path(bbl_path)

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_bbl = Path(tmpdir) / bbl_path.name
            shutil.copy2(bbl_path, tmp_bbl)

            result = subprocess.run(
                [str(self.decoder), str(tmp_bbl)],
                capture_output=True,
                text=True,
                cwd=tmpdir,
            )

            if result.returncode != 0:
                raise RuntimeError(
                    f"Échec du décodage blackbox :\n{result.stderr or result.stdout}"
                )

            csv_files = sorted(Path(tmpdir).glob(f"{bbl_path.stem}.*.csv"))
            if not csv_files:
                csv_files = sorted(Path(tmpdir).glob(f"{bbl_path.stem}.csv"))

            sessions = [self._read_csv(f) for f in csv_files]
            sessions = [df for df in sessions if df is not None]

        if not sessions:
            raise ValueError(
                "Aucune session de vol valide trouvée dans ce fichier.\n"
                "Vérifiez que le fichier n'est pas corrompu."
            )

        return sessions

    def _read_csv(self, csv_path: Path) -> pd.DataFrame | None:
        try:
            df = pd.read_csv(csv_path, skipinitialspace=True)
        except Exception:
            return None

        df.columns = df.columns.str.strip()

        if 'time (us)' not in df.columns:
            return None

        keep = [c for c in WANTED_FIELDS if c in df.columns]
        df = df[keep].copy()

        df['time_s'] = (df['time (us)'] - df['time (us)'].iloc[0]) / 1_000_000.0

        for col in df.columns:
            if col != 'time_s':
                df[col] = pd.to_numeric(df[col], errors='coerce')

        return df
