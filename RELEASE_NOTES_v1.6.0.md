# BlackBox Analyzer v1.6.0 — Multi-plateforme + terminologie corrigée

**Date :** 21 avril 2026

## 📦 Builds automatiques pour Windows, macOS et Linux

À partir de cette version, **chaque release contient les 3 plateformes**, construites
automatiquement par GitHub Actions :

| Plateforme | Artefact | Comment lancer |
|------------|----------|----------------|
| 🪟 Windows | `BlackBoxAnalyzer_v1.6.0.exe` | Double-clic |
| 🍎 macOS   | `BlackBoxAnalyzer-macOS.zip`   | Dézipper, double-clic (après `bash fix_mac.sh` la 1re fois) |
| 🐧 Linux   | `BlackBoxAnalyzer-Linux.tar.gz`| `tar -xzf`, puis `./BlackBoxAnalyzer` |

Les workflows `.github/workflows/build-windows.yml`, `build-mac.yml` et `build-linux.yml`
se déclenchent automatiquement sur chaque tag `vX.Y.Z` poussé.

## 🏷️ Terminologie corrigée : Jello / Jitter

Les anciens termes **« Gelo »** et **« Geno »** (qui n'étaient pas des termes officiels)
ont été remplacés par les vrais termes utilisés par la communauté FPV :

- **Jello** — Ondulation visible sur la vidéo, ressemblant à de la gelée qui tremble.
  Causée par les vibrations transmises au capteur caméra combinées au rolling shutter
  du capteur CMOS. **Souvent NON corrigeable en post-traitement, même avec Gyroflow.**

- **Jitter** — Mouvements erratiques haute fréquence sur tous les axes (l'ancien « Geno »).

Les règles diagnostiques, les cartes de l'onglet Symptômes et la base de connaissances
ont été mises à jour en conséquence.

## Mise à jour

```bash
cd ~/Documents/PID-black-box
git pull
python3 src/main.py     # Mac/Linux
python src\main.py      # Windows
```

Ou téléchargez directement le binaire de votre plateforme depuis la page des releases.
