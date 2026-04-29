# BlackBox Analyzer v1.9.2 — FF / D_yaw désactivés + détection cellules Li-ion

**Date :** 29 avril 2026

> 🐛 **3 bugs critiques corrigés**, identifiés sur le terrain (3 BBL Liam,
> 5" SPDX SPEDIXF405, oscillation 9 Hz qui ne convergeait plus).

## 🩹 Les bugs

### 1. Feedforward désactivé (`F=[0,0,0]`) jamais réactivé

Si le pilote (ou un preset) avait laissé `F=0`, l'analyseur **ne le remontait
jamais** parce que toutes ses recos étaient en delta multiplicatif :
`new = current * (1 + delta)`. Avec `current=0`, le calcul reste à 0.

Conséquence concrète : **cause #1 des "rebonds" sur freestyle**. Sans FF,
le drone ne lit pas les sticks → P/I rattrapent en retard → wobble
permanent à ~9 Hz que le pilote ressent comme des rebonds — et qu'il
attribue à tort à un manque de I.

**Fix :** nouvelle fonction `_check_disabled_critical_params` exécutée
**avant** les analyses par axe. Elle ajoute des recommandations explicites
`f_roll/f_pitch = 110` (CRITIQUE) et `f_yaw = 93` (warning) avec valeurs
de démarrage adaptées au style de vol.

### 2. `D_yaw=0` jamais réactivé

Même bug : `D_yaw=0` dans la config = pas d'amortissement yaw, oscillation
yaw quasi garantie à 9 Hz. Confirmé sur les 3 BBL terrain (PID_OSC yaw
montant à 1.00).

**Fix :** recommandation explicite `d_yaw = 15` ajoutée quand `D_yaw=0`.

### 3. Détection cellules : Li-ion 6S confondue avec 4S

Ancien algorithme : `vbat > cells * 3.3` testé du grand au petit. Pour
un **6S Li-ion à 19.76 V** (=3.29 V/cell, batterie partiellement déchargée
mais saine), 19.76 < 19.8 → tombait à 4S. Or à 4S, 19.76 V représenterait
4.94 V/cell — **physiquement impossible**.

Conséquence : sag mal calculé, recos batterie incohérentes, profil de
puissance moteur faux.

**Fix :** nouvelle logique qui cherche la configuration plaçant `vbat`
dans une plage **plausible 2.7–4.25 V/cell** (couvre LiPo standard ET
Li-ion 6S qui descend à ~2.7 V/cell). Score = distance à 3.7 V (nominal)
— le candidat le plus cohérent gagne.

## 💡 Avertissement « Tu penses que c'est I, c'est pas I »

Quand le pilote répond **« Y a-t-il des rebonds : OUI »** dans le panneau
ressenti, l'analyseur vérifie maintenant si `I_roll/pitch ≥ 140` (au-dessus
du plafond freestyle typique). Si oui, message explicite en tête des
warnings :

> 🔍 I roll/pitch déjà très haut (180/176) — monter I encore amplifierait
> le wobble basse fréquence. Ton vrai problème ici : Feedforward DÉSACTIVÉ
> (F=0). Sans FF, la boucle PID rattrape toujours en retard → wobble
> permanent que tu ressens comme des « rebonds ». Active FF avant toute
> autre modif.

## 🧪 Validé sur 3 BBL terrain

Avant v1.9.2, la BBL #1 (16:46) générait 5 recos PID, aucune ne mentionnant
le FF. Le pilote n'a vu qu'une oscillation 9 Hz qui empirait à chaque vol.

Après v1.9.2, la même BBL génère 9 recos dont **les 4 premières en CRITIQUE
ou WARNING** :

```
🔴 F_ROLL  : désactivé → 110
🔴 F_PITCH : désactivé → 110
⚠️ F_YAW   : désactivé → 93
⚠️ D_YAW   : désactivé → 15
ℹ️ P_ROLL  : 49 → 40 (-18%)
…
```

Et la batterie est désormais correctement détectée comme **6S** sur les 3
BBL (au lieu de 4S sur la première par erreur).

## 📥 Installation

### 🪟 Windows
1. Téléchargez **`BlackBoxAnalyzer_v1.9.2.exe`** depuis *Assets* ci-dessous.
2. Double-cliquez. C'est tout.

### 🍎 macOS
`uname -m` dans Terminal :
- `arm64` → `BlackBoxAnalyzer-macOS-AppleSilicon.zip`
- `x86_64` → `BlackBoxAnalyzer-macOS-Intel.zip`

Puis : double-clic sur le `.zip`, et une fois :
```bash
xattr -cr ~/Downloads/BlackBoxAnalyzer.app
```

### 🐧 Linux
```bash
tar -xzf BlackBoxAnalyzer-Linux.tar.gz
chmod +x BlackBoxAnalyzer
./BlackBoxAnalyzer
```

## 📦 Fichiers modifiés

- `src/analysis/analyzer.py` — `_guess_cell_count` revu (plage 2.7–4.25 V/cell)
- `src/analysis/recommender.py` — `_check_disabled_critical_params` (FF/D_yaw),
  message anti-confusion sur l'I quand le pilote signale des rebonds.

Aucun changement de format BBL ni de fichier de config. Mise à jour transparente.
