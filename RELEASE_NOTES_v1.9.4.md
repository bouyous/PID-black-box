# BlackBox Analyzer v1.9.4 — Stop aux hausses d'I injustifiées (faux drift, vent fort)

**Date :** 30 avril 2026

> 🩹 **Bug critique** : sur des vols stationnaires calmes ou sur drone qui
> subit du vent, l'analyseur recommandait des hausses de I de l'ordre
> de +20% à chaque BBL. Erreur de logique : le `drift_score` est un
> score *relatif* du PSD, pas une mesure d'amplitude absolue.
> v1.9.4 ajoute deux garde-fous.

## 🩹 Le bug

`drift_score` mesure la concentration d'un pic dans la bande 3-30 Hz
relativement au reste du spectre. Conséquence : un drone immobile à
±15 °/s peut quand même afficher `drift_score = 0.60` si l'énergie de
ce gyro résiduel est concentrée vers 4 Hz. Le code interprétait ça comme
"il manque de l'I pour tenir la trajectoire" et recommandait `I +21%`.

Sur un vol stationnaire avec **vent fort**, c'est encore pire : le drone
*subit* des perturbations externes que la boucle PID combat avec P/D.
Augmenter I sature l'I-term, génère de l'overshoot, et **amplifie le
tremblement** au lieu de le réduire.

Confirmé sur 3 BBL terrain (Liam, 30/04/2026, drone qui "tremble comme
une patate" en vent fort, moteurs PAS chauds → pas de surcharge moteur).

## ✨ Nouveau

### 1. Détecteur d'amplitude réelle gyro en sections calmes

`AxisAnalysis` expose désormais `gyro_std_calm` et `sp_std_calm` (écart-type
mesurés sur les sections où `|setpoint| < 80 °/s`). Le recommender
**refuse toute hausse de I** si `gyro_std_calm < 25 °/s` (le drone est
quasi immobile, le drift est dans le bruit).

Message visible dans le résumé :

> 📏 Pitch : drift_score 0.60 mais amplitude gyro réelle faible
> (σ=17°/s < 25). Le 'drift' détecté est dans le bruit — hausse de I
> REFUSÉE (inutile).

### 2. Détecteur "perturbation externe" (vent / rafales)

Nouveau champ `wind_disturbance_score` : ratio `gyro_std / sp_std` en
sections calmes. Si stick calme (`sp_std < 30`) ET gyro très agité
(`gyro_std > 30`), avec ratio > 3 → score élevé → **hausse de I refusée**.

> 🌬 Roll : gyro agité (σ=80°/s) alors que le stick est calme (σ=12°/s)
> → perturbation externe (vent/rafales). Hausse de I REFUSÉE — augmenter
> I ici sature l'I-term et amplifie le tremblement au lieu de le réduire.

### 3. Test sur les BBL terrain

Avant v1.9.4, sur 3 BBL identiques (config stock BF 4.5, P=45/47/45
I=80/84/80 D=40/46/0 F=120/125/120) :

```
BBL #1 : ⚠️ I_PITCH : 84 → 102 (+21%)   ← faux positif
BBL #2 : ⚠️ I_PITCH : 84 → 102 (+21%)   ← faux positif
BBL #3 : (pitch oscillation HF, hausse bloquée par autre garde-fou)
```

Après v1.9.4 :

```
BBL #1 : aucune hausse de I + message 📏 amplitude trop faible
BBL #2 : aucune hausse de I + message 📏 amplitude trop faible
BBL #3 : (inchangé — déjà bloqué)
```

## 📦 Fichiers modifiés

- `src/analysis/analyzer.py` — `_detect_drift` calcule désormais
  `gyro_std_calm`, `sp_std_calm`, `wind_disturbance_score`.
- `src/analysis/recommender.py` — deux garde-fous dans le bloc drift→I
  (amplitude + vent), message info explicite quand on refuse une hausse.

## 📥 Installation

### 🪟 Windows
1. `BlackBoxAnalyzer_v1.9.4.exe` depuis *Assets* ci-dessous.
2. Double-clic, c'est tout.

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
