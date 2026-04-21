import os
import platform
import re
import shutil
import subprocess
import sys
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

_PLATFORM = platform.system()   # 'Windows', 'Darwin' (Mac), 'Linux'


def _strip_unit(name: str) -> str:
    """'gyroADC[0] (deg/s)' → 'gyroADC[0]'"""
    return _UNIT_RE.sub('', name).strip()


def _decoder_names() -> list[str]:
    """Noms de binaire à chercher selon l'OS."""
    if sys.platform.startswith('win'):
        return ['blackbox_decode.exe']
    # macOS / Linux : pas d'extension
    return ['blackbox_decode']


def find_decoder() -> Path | None:
    """Cherche le binaire blackbox_decode (Windows .exe, macOS/Linux sans ext.)
    dans : bundle PyInstaller, tools/ du repo, à côté de l'exe, puis PATH."""
    names = _decoder_names()
    roots: list[Path] = []
    # 1. Bundle PyInstaller (--onefile extrait dans sys._MEIPASS)
    meipass = getattr(sys, '_MEIPASS', None)
    if meipass:
        roots.append(Path(meipass) / 'tools')
        roots.append(Path(meipass))
    # 2. À côté de l'exe (.app/Contents/MacOS, onedir, etc.)
    exe_dir = Path(sys.executable).resolve().parent
    roots.append(exe_dir / 'tools')
    roots.append(exe_dir)
    # 3. Repo dev : tools/ à la racine
    roots.append(Path(__file__).resolve().parent.parent.parent / 'tools')

    for root in roots:
        for name in names:
            c = root / name
            if c.exists():
                return c

    for name in names + ['blackbox_decode']:
        found = shutil.which(name)
        if found:
            return Path(found)
    return None


class BlackboxParser:
    def __init__(self, decoder_path: Path | None = None):
        self.decoder = decoder_path or find_decoder()

    def is_ready(self) -> bool:
        return self.decoder is not None and Path(self.decoder).exists()

    def decode(self, bbl_path: str | Path) -> list[pd.DataFrame]:
        """Décode un fichier .bbl/.bfl et retourne une DataFrame par session valide."""
        if not self.is_ready():
            platform_hint = {
                'Darwin':  (
                    "Téléchargez le binaire Mac depuis :\n"
                    "https://github.com/betaflight/blackbox-tools/releases\n"
                    "Prenez 'blackbox_decode_mac' et placez-le dans le dossier tools/.\n"
                    "Ou installez via Homebrew : brew install blackbox-tools"
                ),
                'Linux':   (
                    "Téléchargez le binaire Linux depuis :\n"
                    "https://github.com/betaflight/blackbox-tools/releases\n"
                    "Placez 'blackbox_decode' dans le dossier tools/."
                ),
            }.get(_PLATFORM, (
                "Placez blackbox_decode.exe dans le dossier tools/ du projet.\n"
                "(Source : https://github.com/betaflight/blackbox-tools/releases)"
            ))
            raise FileNotFoundError(
                f"Décodeur blackbox introuvable sur {_PLATFORM}.\n{platform_hint}"
            )

        bbl_path = Path(bbl_path)

        # Sur Mac : supprimer l'attribut de quarantaine du décodeur s'il est présent
        if _PLATFORM == 'Darwin':
            try:
                subprocess.run(
                    ['xattr', '-d', 'com.apple.quarantine', str(self.decoder)],
                    capture_output=True, timeout=5
                )
            except Exception:
                pass  # xattr absent ou déjà propre

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_bbl = Path(tmpdir) / bbl_path.name
            shutil.copy2(bbl_path, tmp_bbl)

            try:
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
                    timeout=120,  # 2 min max — évite le freeze infini
                )
            except subprocess.TimeoutExpired:
                raise ValueError(
                    "Le décodeur a mis trop de temps (>2 min).\n"
                    "Le fichier est peut-être trop volumineux ou corrompu."
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
