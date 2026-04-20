"""
Script de build cross-platform : produit un exécutable standalone.

Windows : dist/BlackBoxAnalyzer.exe
macOS   : dist/BlackBoxAnalyzer.app (+ .zip pour distribution)
Linux   : dist/BlackBoxAnalyzer (binaire onefile)

Usage :
    python build_exe.py

L'utilisateur final n'a besoin d'installer RIEN (Python embarqué).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / 'src'
TOOLS = ROOT / 'tools'

IS_WIN = sys.platform.startswith('win')
IS_MAC = sys.platform == 'darwin'

DECODER_NAME = 'blackbox_decode.exe' if IS_WIN else 'blackbox_decode'
DECODER = TOOLS / DECODER_NAME

# Séparateur pour --add-binary : ';' sur Windows, ':' ailleurs (syntaxe PyInstaller)
ADDSEP = ';' if IS_WIN else ':'


def main():
    if not DECODER.exists():
        print(f"ERREUR : {DECODER} introuvable.")
        if IS_WIN:
            print("Placez blackbox_decode.exe dans tools/")
        elif IS_MAC:
            print("Placez blackbox_decode (binaire macOS) dans tools/")
            print("Source : https://github.com/betaflight/blackbox-tools/releases")
        else:
            print("Placez blackbox_decode (binaire Linux) dans tools/")
        sys.exit(1)

    # Nettoyage des builds précédents
    for d in ('build', 'dist'):
        p = ROOT / d
        if p.exists():
            print(f"Nettoyage de {p} ...")
            shutil.rmtree(p)
    for spec in ROOT.glob('*.spec'):
        spec.unlink()

    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--onefile',
        '--windowed',
        '--name', 'BlackBoxAnalyzer',
        '--paths', str(SRC),
        '--add-binary', f'{DECODER}{ADDSEP}tools',
        '--hidden-import', 'PyQt6.QtCore',
        '--hidden-import', 'PyQt6.QtGui',
        '--hidden-import', 'PyQt6.QtWidgets',
        '--hidden-import', 'pyqtgraph',
        '--collect-submodules', 'pyqtgraph',
        str(SRC / 'main.py'),
    ]

    print("Commande PyInstaller :")
    print("  " + " ".join(cmd))
    print()

    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print("BUILD ÉCHOUÉ.")
        sys.exit(result.returncode)

    dist = ROOT / 'dist'
    if IS_WIN:
        artifact = dist / 'BlackBoxAnalyzer.exe'
    elif IS_MAC:
        artifact = dist / 'BlackBoxAnalyzer.app'
        if not artifact.exists():
            # --windowed sur mac produit parfois juste le binaire
            artifact = dist / 'BlackBoxAnalyzer'
    else:
        artifact = dist / 'BlackBoxAnalyzer'

    if artifact.exists():
        if artifact.is_dir():
            # .app bundle
            import os
            size = sum(f.stat().st_size for f in artifact.rglob('*') if f.is_file())
        else:
            size = artifact.stat().st_size
        print()
        print(f"[OK] Build reussi : {artifact}")
        print(f"  Taille : {size / (1024 * 1024):.1f} Mo")
    else:
        print("ERREUR : l'artefact n'a pas ete produit.")
        sys.exit(1)


if __name__ == '__main__':
    main()
