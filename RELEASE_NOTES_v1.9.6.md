# BlackBox Analyzer v1.9.6 — Sliders saturés → fallback PID brut

**Date :** 1er mai 2026

> 🩹 **Bug** : sur la BBL Liam 14:19, le dump sliders proposait
> `simplified_d_gain = 200` (le maximum absolu) alors que la recommandation
> réelle était D × 1.15 sur l'effective PID. Cause : le slider de D était
> déjà à 1.76, et un delta de +14.7 % le clampait au plafond, sans
> indication ni alternative.

## 🩹 Les bugs

### 1. Doublons de recos additionnés dans le delta du slider

Quand deux blocs du recommender ajoutent une reco sur le **même paramètre**
(ex : `D_PITCH +17%` pour oscillation 9 Hz, `D_PITCH +9%` pour propwash),
`compute_sliders` mettait les deux dans `deltas['d']`. Le calcul du slider
prenait la moyenne — mais avec d'autres recos `d_*` la pondération était
faussée et le delta global gonflait.

**Fix :** dédupliquer par `param` exact AVANT d'agréger : on garde la
reco de plus grande amplitude (en valeur absolue) par paramètre distinct.

### 2. Slider clampé silencieusement

Le slider D allait de `1.76` à `2.00` (clamp à max) sans signaler que la
recommandation **n'était pas appliquée jusqu'au bout**. L'utilisateur
voyait `simplified_d_gain = 200` et pensait à une dérive du logiciel.

**Fix :** `SliderAdjustments` expose maintenant un `set saturated` :
chaque clamp est tracé. Quand un slider sature, le dump :
- **n'émet plus la ligne slider** (qui serait incomplète)
- bascule sur les **PID bruts** : `set d_pitch = 54`, etc.
- préfixe d'un commentaire explicite « Slider X sature — bascule en PID brut »

### 3. Yaw oublié en mode sliders

Les sliders simplifiés de Betaflight 4.5 ne pilotent **que roll + pitch**
pour P/I/D/FF. Le yaw était donc complètement ignoré en mode sliders.
Sur la BBL Liam, la reco `D_YAW : 15 → 26` (cause #1 du wobble yaw 9 Hz)
n'apparaissait nulle part dans le dump.

**Fix :** section dédiée `# YAW (non couvert par les sliders) :` qui
émet en PID brut toutes les recos yaw non encore couvertes.

## 🧪 Avant / après sur BBL 14:19

**Avant v1.9.6 :**
```
set simplified_pids_mode = RPY
set simplified_dterm_filter = OFF
set simplified_gyro_filter = OFF
set simplified_d_gain = 200
save
```
(D_yaw absent, FF non émis non plus, doublons cachés)

**Après v1.9.6 :**
```
set simplified_pids_mode = RPY
set simplified_dterm_filter = OFF
set simplified_gyro_filter = OFF

# Slider simplified_d_gain sature — bascule en PID brut :
set d_roll = 47    # était 40 (+18%) — oscillation 9 Hz
set d_pitch = 54   # était 46 (+17%) — oscillation 9 Hz

# Slider simplified_feedforward_gain sature — bascule en PID brut :
set f_roll = 138   # était 120 (+15%)
set f_pitch = 144  # était 125 (+15%)

# YAW (non couvert par les sliders) :
set d_yaw = 26     # était 15 (+73%) — D yaw amortit le wobble 9 Hz

save
```

Lisible, dédupliqué, exécutable tel quel.

## 📦 Fichiers modifiés

- `src/analysis/sliders.py` — déduplication par paramètre, détection
  saturation, fallback PID brut, section YAW.
- `src/analysis/recommender.py` — `cli_dump_sliders` passe la liste
  `recommendations` à `dump_sliders_cli`.

## 📥 Installation

### 🪟 Windows
1. `BlackBoxAnalyzer_v1.9.6.exe` depuis *Assets*.
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
