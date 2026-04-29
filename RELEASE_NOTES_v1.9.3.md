# BlackBox Analyzer v1.9.3 — Profil de châssis + diagnostic condensateur affiné

**Date :** 29 avril 2026

> 🛠️ Patch demandé après v1.9.2 : l'alerte "vibration / vis desserrées"
> sortait en rouge sur quasiment chaque BBL, même sur des châssis dont
> la vibration plus élevée est *normale*.

## ✨ Nouveautés

### 1. Sélecteur "Type de châssis" dans le panneau Profil

Trois choix dans un nouveau combo à côté de Taille / Style / Batterie :

- **Standard** — châssis FPV moderne 5 mm, bras détachés (ImpulseRC, GepRC,
  iFlight la plupart). Comportement identique à avant.
- **Unibody (Marmotte, etc.)** — monobloc taillé masse Armattan Marmotte
  4 mm, Source One v5 unibody, etc. **Pas de bras à serrer** : si les
  4 vis moteur sont OK, un pic vibration n'est pas un problème de visserie.
- **Souple / Ancien (Lumenier 4-5 ans, copie)** — frames carbone fatigués,
  fines (3 mm), copies chinoises. Vibrations structurelles ; à filtrer
  plutôt qu'à serrer.

### 2. Seuil d'alerte vibrations adapté au châssis

| Type de frame | Ancien seuil | Nouveau seuil |
|---|---|---|
| Standard | 4 pics | **6 pics** (réduit le bruit visuel) |
| Unibody  | 4 pics | **9 pics** |
| Souple/Ancien | 4 pics | **12 pics** |

Entre `threshold-3` et `threshold` : message **informatif** dans le résumé
(« quelques pics — normal sur ce type de frame, filtres notch suffiront »)
au lieu d'un warning rouge.

### 3. Texte d'alerte spécifique par châssis

- **Unibody** : "Si les 4 vis moteur sont serrées, ce N'EST PAS un problème
  de visserie. Pistes à vérifier dans l'ordre : hélices fissurées/déséquilibrées,
  cloches moteur ou roulements, résonance naturelle du carbone — à filtrer
  (notch) plutôt qu'à serrer."
- **Souple/Ancien** : "Sur ce type de frame, les vibrations sont en grande
  partie STRUCTURELLES (carbone fatigué qui résonne). À TRAITER PAR FILTRAGE
  (notch dynamique élargi, dterm_lpf serré) plutôt que par serrage."
- **Standard** : ancien message légèrement remanié.

### 4. Diagnostic condensateur multi-signaux

Au lieu d'une mention unique en cas de bruit HF, l'analyseur **agrège
maintenant 5 signaux** et n'alerte que si la combinaison est convaincante :

| Signal | Points |
|---|---|
| Sag batterie > 0.5 V/cell | +2 |
| Bruit HF excessif sans D-term explosé | +2 |
| ≥ 3 pics 100-500 Hz hors RPM filter | +2 |
| Vmin très bas (< 3.2 V/cell pour la chimie déclarée) | +1 |
| Oscillation freq fixe sur ≥ 2 axes (VCC ripple) | +2 |

- **Score ≥ 4 et ≥ 2 signaux distincts** → warning ciblé "Condensateur
  défaillant ou absent" avec **liste des signaux détectés** et procédure
  (1000-2200 µF / 35 V directement sur les pads batterie, vérifier ESR si
  déjà présent).
- **Score 2-3** → mention informative dans le résumé, sans alerter.

Évite les faux positifs sur les BBL "saines mais bruyantes".

## 📦 Fichiers modifiés

- `src/analysis/recommender.py` — `FrameType` enum, paramètre dans
  `generate_report`, `_check_vibrations` adapté, diag condensateur enrichi.
- `src/ui/main_window.py` — combo "Type de châssis" + propagation jusqu'à
  `generate_report`.

## 📥 Installation

### 🪟 Windows
1. `BlackBoxAnalyzer_v1.9.3.exe` depuis *Assets*.
2. Double-cliquez.

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
