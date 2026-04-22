# BlackBox Analyzer v1.7.0 — Matrice diagnostique officielle Jello / Jitter

**Date :** 22 avril 2026

## 🎯 Clarification : Jello Effect ≠ Jitter

Cette version intègre la **Diagnostic Matrix v1.0** (scope : *Flight Controller &
Advanced Filtering for Betaflight v4.5+*). Les définitions officielles des deux
symptômes principaux ont été clarifiées et corrigées dans toute la base de
connaissances :

### Jello Effect — *Rolling Shutter / Vibration-Induced Blurring*

> Apparence de **flou**, de **tremblement horizontal ou vertical** dans le flux vidéo.
> Causé par la vibration du châssis transmise à la caméra, qui perturbe l'acquisition
> image du capteur CMOS (effet **rolling shutter**).
>
> **Ce n'est PAS un défaut de contrôle en vol** — c'est un symptôme **vidéo**.
> Ce défaut est souvent **NON corrigeable en post-traitement, même avec Gyroflow**.

**Remède n°1 (mécanique, pas logiciel) :** installer des **amortisseurs (dampers)
spécifiques sur la monture caméra**. Vérifier le serrage du cadre et l'équilibrage
des hélices. Aucun réglage PID ne peut corriger un Jello purement mécanique.

### Jitter — *High-Frequency Vibration*

> Mouvements erratiques et très fréquents, souvent perceptibles même en vol stable.
> Défaut de **contrôle** (IMU / PID trop réactif), à distinguer du Jello qui est
> un symptôme vidéo.

## 📋 Matrice diagnostique : 3 vecteurs de cause par symptôme

Chaque symptôme est maintenant analysé selon les 3 vecteurs de cause officiels :

| Vecteur | Exemples |
|---------|----------|
| **Software / Filtering** | PID trop agressif, filtres IMU mal calibrés |
| **Mechanical** | Vibrations châssis, vis desserrées, hélices déséquilibrées, dampers caméra |
| **Electrical / Power** | EMI, ripple voltage, défaillance ESC/MOSFET |

Pour chacun : description technique, paramètres à ajuster, action recommandée,
et **niveau de risque au sur-réglage**.

## 📂 Nouveau fichier de référence

- `docs/research/diagnostic_matrix_v1.json` — la matrice diagnostique complète
  (source officielle utilisée par `symptom_db.py`).

## 🗑️ Corrections de fausses informations

- L'ancienne définition du Jello comme « oscillation 50–200 Hz de la cellule »
  est désormais secondaire — la **cause primaire est mécanique** (vibrations
  transmises à la caméra).
- La solution « réduire D / optimiser filtres » passe en cause secondaire,
  **après** l'inspection mécanique et l'installation de dampers caméra.
- Le Jitter ne se confond plus avec le Jello : le premier est un défaut de
  contrôle, le second un artefact vidéo.

## 📦 Builds multi-plateformes (inchangé depuis v1.6.0)

- 🪟 `BlackBoxAnalyzer_v1.7.0.exe`
- 🍎 `BlackBoxAnalyzer-macOS.zip`
- 🐧 `BlackBoxAnalyzer-Linux.tar.gz`

## Mise à jour

```bash
cd ~/Documents/PID-black-box
git pull
python3 src/main.py     # Mac/Linux
python src\main.py      # Windows
```
