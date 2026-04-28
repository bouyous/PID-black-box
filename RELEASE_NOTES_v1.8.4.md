# BlackBox Analyzer v1.8.4 — Le diagnostic qui ne ment plus

**Date :** 28 avril 2026

> ⚠️ **Bug critique corrigé** : les versions 1.7.x et 1.8.0–1.8.3 pouvaient
> recommander d'**augmenter le I gain** sur un drone qui oscillait déjà
> en ligne droite (10–40 Hz). Résultat : drone plus nerveux, oscillations
> *plus fortes*, et message "drone réglé" affiché malgré tout.
> **La v1.8.4 corrige tout ça** et ajoute trois retours pilote structurés.

## 🩹 Le bug critique en détail

Sur un 5" freestyle volant en ligne droite, l'oscillation typique d'un
P trop haut / D trop bas tombe à **8–40 Hz**. Or l'analyseur :

- considérait `OSCILLATION_BAND = (40, 400 Hz)` pour la détection HF,
- considérait `DRIFT_BAND = (3, 30 Hz)` mais la traitait comme un manque de I,
- → **les oscillations 10–40 Hz tombaient dans un trou** et étaient
  interprétées à tort comme "drone qui dérive parce qu'il manque de I".

Conséquence : le pilote suivait les recos, augmentait I, et empirait
le drone. La v1.8.4 ajoute une bande dédiée `PID_OSC_BAND = (8, 40 Hz)`
avec un détecteur strict (concentration × proéminence du pic).

## ✨ Nouveautés

### 1. Détection oscillation PID 8–40 Hz
Nouveau champ `AxisAnalysis.has_pid_oscillation`. Quand il est vrai :
- **Augmenter I est interdit** (garde-fou explicite).
- Le logiciel recommande **P↓ + D↑** + resserrage du `dterm_lpf1` si pertinent.
- Pénalité jusqu'à -25 points sur le score santé.

### 2. Détection des rebonds sur les gaz (punch wobble)
Corrèle `dThrottle/dt` avec |gyro pitch| sur fenêtres de punch-out.
Quand le score dépasse 0.25, le logiciel :
- Avertit explicitement (« Pitch plonge sur les punch-outs »).
- Propose un bump de `anti_gravity_gain` et `iterm_relax_cutoff` si trop bas.

### 3. Sélecteur température moteurs (post-vol)
Trois boutons : **❄ Froids / 🌡 Tièdes / 🔥 Chauds**. Quand le pilote
sélectionne *Chauds* (limite tolérable au doigt) :
- Toute reco qui augmenterait `P/D/F/dmax/master`, `anti_gravity_gain`,
  `dshot_idle_value` ou élargirait un cutoff filtre est **supprimée**.
- Repli automatique : -8% sur `dshot_idle` si > 5.5%, -20% sur
  `anti_gravity_gain` si ≥ 100, -10% sur `simplified_master`.
- Bannière 🔥 critique en tête des warnings.

### 4. Ressenti pilote — 5 questions Oui/Non
Après le vol de test, le pilote répond :
1. Y a-t-il eu une amélioration ?
2. Y a-t-il des rebonds (punch / sortie de virage) ?
3. Y a-t-il encore du propwash ?
4. Le drone est-il suffisamment locké ?
5. Le drone est-il suffisamment réactif ?

Ces réponses sont injectées dans la génération du CLI :
- **Pas d'amélioration** → tous les deltas existants sont divisés par 2 et
  un avertissement demande au pilote de revenir aux PIDs précédents si la
  prochaine BBL est encore pire.
- **Rebonds OUI** → `anti_gravity_gain` poussé à 100+, `iterm_relax_cutoff` ≥ 22.
- **Propwash OUI** → reco `D_min` ajoutée + resserrage `dterm_lpf1`.
- **Pas assez locké** → `FF +10%` et `D +7%` sur Roll/Pitch (sans
  contrarier une baisse déjà recommandée).
- **Pas assez réactif** → `P +6%` (sauf si une baisse de P est déjà recommandée
  pour cause d'oscillation).
- **Tout OK** → bannière "drone réglé pour de vrai", recos passées en INFO.

### 5. Verrou strict sur le message "drone réglé"
Plus jamais affiché tant que `health_score < 85` ou qu'un détecteur
(oscillation PID, drift, propwash, punch wobble) reste allumé. À la place,
un message dédié liste ce qui ne va pas malgré l'absence de reco chiffrée.

## 🧪 Validé sur BBL réelle

Test sur une BBL `SPDX SPEDIXF405` 5" freestyle qui faisait remonter
l'analyseur en mode "drone réglé" :

| Métrique | v1.8.3 | v1.8.4 |
|---|---|---|
| Oscillation 9 Hz détectée (Roll) | non | **oui** (score 0.33) |
| Oscillation 9 Hz détectée (Yaw) | non | **oui** (score 0.68) |
| Punch wobble Pitch | non détecté | **0.33** |
| Score santé | élevé (~"OK") | **0/100** |
| Reco I_yaw augmenté | OUI (faux positif) | **NON** |
| Reco P_yaw -18% | aucune | **présente** |

## 📥 Installation

### 🪟 Windows — le plus simple

1. Téléchargez **`BlackBoxAnalyzer_v1.8.4.exe`** depuis *Assets* ci-dessous.
2. **Double-cliquez**. C'est tout.

### 🍎 macOS

**Étape 0 — vérifier l'architecture :** dans Terminal : `uname -m`

| `uname -m` | À télécharger |
|------------|---------------|
| `arm64`    | `BlackBoxAnalyzer-macOS-AppleSilicon.zip` |
| `x86_64`   | `BlackBoxAnalyzer-macOS-Intel.zip` |

Puis :
1. Double-clic sur le `.zip` pour dézipper.
2. Dans Terminal (une seule fois) :
   ```bash
   xattr -cr ~/Downloads/BlackBoxAnalyzer.app
   ```
3. Double-clic sur `BlackBoxAnalyzer.app`. ✅

### 🐧 Linux

```bash
tar -xzf BlackBoxAnalyzer-Linux.tar.gz
chmod +x BlackBoxAnalyzer
./BlackBoxAnalyzer
```

## 🔧 Détails techniques

- `analysis/analyzer.py` : nouveaux détecteurs `_detect_pid_oscillation`
  (Welch PSD sur tout le vol, bande 8–40 Hz, exigence q-factor > 4 et
  rel > 0.10) et `_detect_punch_wobble` (jerk throttle 25% sur 150 ms,
  pic gyro dans les 250 ms qui suivent).
- `analysis/recommender.py` : nouvelle classe `PilotFeedback`, enum
  `MotorTemp`, fonctions `_apply_pilot_feedback` et `_apply_hot_motors_safety`,
  garde-fou explicite contre l'augmentation de I.
- `ui/main_window.py` : widgets `MotorTempBox` et `PilotFeedbackBox` ajoutés
  sous le panneau de ressenti existant.

Pas de changement de format BBL ni de fichier de config — la mise à jour
est transparente côté pilote.
