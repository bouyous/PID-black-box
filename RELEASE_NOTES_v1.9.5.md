# BlackBox Analyzer v1.9.5 — Détection des flips et freestyle agressif

**Date :** 30 avril 2026

> 🐛 **Bug majeur** : l'analyseur ratait la moitié des vols freestyle.
> Les flips et rolls qui se font *gaz coupés* (en chute libre) étaient
> exclus du `fly_mask` (seuil throttle > 1100), donc l'analyseur classait
> les vols comme "Stationnaire / Hover" et ignorait le pic du setpoint
> à 600+ °/s.

## 🩹 Le bug

`_fly_mask` filtrait avec un seul critère : `rcCommand[3] > 1100`.

Sur un vol freestyle classique :
- Pitch flip avant = on coupe les gaz pour ne pas perdre d'altitude
- Roll = idem, gaz coupés pour ne pas remonter
- Pendant ces 200-500 ms, throttle descend à 1000 → exclu du fly_mask
- → l'analyseur ne voit que les sections "calmes entre les figures"
- → label "Stationnaire / Hover", `max_setpoint = 230 °/s` au lieu de 667
- → toutes les analyses (FFT, drift, oscillation) ratent la moitié du vol

Confirmé sur les 3 BBL terrain Liam 30/04/2026 : pitch setpoint réel
**max 667 °/s**, mais l'analyseur reportait **107 °/s** (sections gaz
coupés exclues).

## ✨ Correction

`_fly_mask` étendu : on est "en vol" si **au moins UN** des critères :

1. `throttle > 1100` (vol normal)
2. `|gyro| > 100 °/s` sur un axe (rotation marquée — flip/roll)
3. `|setpoint| > 80 °/s` sur un axe (stick poussé)

Le pilote peut maintenant flipper gaz coupés sans rendre l'analyse aveugle.

## 🧪 Avant / après sur les 3 BBL terrain

| | Avant (v1.9.4) | Après (v1.9.5) |
|---|---|---|
| BBL #1 type vol | Stationnaire / Hover | **Vol mixte (score 5)** |
| BBL #2 type vol | Stationnaire / Hover | **Freestyle (score 6)** |
| BBL #3 type vol | Stationnaire / Hover | **Vol mixte (score 4)** |
| max setpoint pitch | 230 °/s | **667 °/s** |
| Recos pertinentes | OK | OK + cibles freestyle correctement appliquées |

## 📦 Fichiers modifiés

- `src/analysis/analyzer.py` — `_fly_mask` accepte 3 critères au lieu d'1.

## 📥 Installation

### 🪟 Windows
1. `BlackBoxAnalyzer_v1.9.5.exe` depuis *Assets*.
2. Double-clic.

### 🍎 macOS
- `arm64` → `BlackBoxAnalyzer-macOS-AppleSilicon.zip`
- `x86_64` → `BlackBoxAnalyzer-macOS-Intel.zip`
- Une fois : `xattr -cr ~/Downloads/BlackBoxAnalyzer.app`

### 🐧 Linux
```bash
tar -xzf BlackBoxAnalyzer-Linux.tar.gz
chmod +x BlackBoxAnalyzer
./BlackBoxAnalyzer
```
