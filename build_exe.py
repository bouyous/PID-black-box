"""
Script de build Windows : produit dist/BlackBoxAnalyzer.exe standalone.

Ce .exe embarque :
  - L'interpréteur Python 3.14
  - PyQt6 + pyqtgraph + pandas + numpy
  - blackbox_decode.exe (dans tools/)
  - Tout le code src/

L'utilisateur final n'a besoin d'installer RIEN sur sa machine :
il copie l'exe, double-clique, ça tourne.

Usage :
    python build_exe.py

Résultat : dist/BlackBoxAnalyzer.exe  (environ 120-180 Mo)
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC  = ROOT / 'src'
TOOLS = ROOT / 'tools'
DECODER = TOOLS / 'blackbox_decode.exe'


def main():
    if not DECODER.exists():
        print(f"ERREUR : {DECODER} introuvable.")
        print("Copiez blackbox_decode.exe depuis PIDtoolboxPro_v0.81_win/main/")
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
        # Intègre blackbox_decode.exe à côté de l'exe final
        '--add-binary', f'{DECODER};tools',
        # Hidden imports PyQt6 que PyInstaller rate parfois
        '--hidden-import', 'PyQt6.QtCore',
        '--hidden-import', 'PyQt6.QtGui',
        '--hidden-import', 'PyQt6.QtWidgets',
        '--hidden-import', 'pyqtgraph',
        '--collect-submodules', 'pyqtgraph',
        # Pas d'icône pour l'instant (ajoutable via --icon=path.ico)
        str(SRC / 'main.py'),
    ]

    print("Commande PyInstaller :")
    print("  " + " ".join(cmd))
    print()

    result = subprocess.run(cmd, cwd=ROOT)
    if result.returncode != 0:
        print("BUILD ÉCHOUÉ.")
        sys.exit(result.returncode)

    exe = ROOT / 'dist' / 'BlackBoxAnalyzer.exe'
    if exe.exists():
        size_mo = exe.stat().st_size / (1024 * 1024)
        print()
        print(f"[OK] Build reussi : {exe}")
        print(f"  Taille : {size_mo:.1f} Mo")
        print()
        print("Pour l'installer sur une autre machine Windows :")
        print("  1. Copiez dist/BlackBoxAnalyzer.exe")
        print("  2. Double-cliquez — pas besoin de Python ni de dépendances")
    else:
        print("ERREUR : l'exe n'a pas été produit.")
        sys.exit(1)


if __name__ == '__main__':
    main()
