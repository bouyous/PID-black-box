# Mémo projet — décisions prises et contexte

Ce fichier sert à reprendre le projet d'une machine à l'autre. Il consolide les décisions, l'état d'avancement, et les choix à faire.

---

## Décisions validées

### Plateforme (17/04/2026)
**Windows desktop avec PyQt6.** Python 3.14, pyqtgraph, pandas, numpy.
- Mac compatible plus tard avec la même codebase (PyQt6 = cross-platform).
- Distribution finale : PyInstaller → `.exe` standalone (pas de signature requise, la communauté FPV est habituée).

### Parser blackbox (17/04/2026)
**subprocess + `blackbox_decode.exe`** (outil officiel Betaflight, même approche que Plasmatree).
- Source locale : `PIDtoolboxPro_v0.81_win/main/blackbox_decode.exe` (déjà copié dans `tools/`).
- Appel avec `--unit-rotation deg/s --unit-vbat V --unit-amperage A`.
- eRPM loggé = eRPM_réel / 100 → multiplier ×100 pour retrouver la vraie valeur.

### Plotting (17/04/2026)
**pyqtgraph** — natif PyQt6, rapide pour 1M+ points. matplotlib pour exports PDF si besoin en v3.

### Sécurité recommandations (17/04/2026)
- Limites de changement calibrées par taille : 3"=±45%, 5"=±25%, 6"=±35%, 7"=±45%, 10"=±55%.
- CLI dump en lecture seule — l'utilisateur applique manuellement dans BF Configurator.
- **Jamais d'écriture directe sur le drone.**

---

## État du code (commit ea772ce — 17/04/2026)

```
src/
├── main.py
├── parser/blackbox_parser.py      ← subprocess + CSV, filtre sessions vides
├── analysis/
│   ├── header_parser.py           ← parse tous les H fields du BBL (PIDs, filtres, bidir DSHOT...)
│   ├── analyzer.py                ← FFT Welch, oscillations, bruit D, vibrations mécaniques
│   └── recommender.py             ← recommandations par axe, CLI dump sécurisé
└── ui/
    ├── main_window.py             ← drag & drop, sélecteur profil drone, onglets sessions
    ├── plot_widget.py             ← lanes séparées filtré/brut, PID par terme, moteurs
    ├── fft_widget.py              ← spectre PSD + spectrogramme Roll, marqueurs filtres RPM
    └── recommendation_panel.py   ← onglets Contexte / Diagnostic / CLI Dump
tools/
└── blackbox_decode.exe            ← présent localement, exclu du git
samples/
├── BTFL_TMOTORVELOXF7SE.BBL       ← 7" 6S TMOTOR, 1 session 105s
└── 6pouceTMOTORVELOXF7SE.BBL     ← 6", 3 sessions
```

Pour lancer : `python src/main.py`

---

## Contexte terrain — profils de vol à intégrer (v3)

### "Bangers" / vol en intérieur exigu (17/04/2026)
**Terme américain : "bangers"** (ou "bandeau" en français FPV) = vol dans bâtiments abandonnés,
passages très étroits (fenêtres, barres métalliques, plafonds bas). Crash quasi-garantis.

**Problème identifié** : un tune très strict (fort D, filtre serré) est catastrophique en bangers.
Quand une pale est légèrement faussée après un crash :
- Le PID corrige en permanence la vibration → corrections énormes
- Les moteurs chauffent, risque de griller un moteur ou un ESC
- Impossible de ramener le drone

**Profil "Loquet" (v3)** — tune tolérant pour vol en intérieur risqué :
- Feed-forward élevé pour la réactivité
- Filtres D moins agressifs (laisser passer un peu de bruit)
- D_min plus bas (moins de correction sur les micro-vibrations)
- Objectif : le drone reste pilotable même avec une pale abîmée, sans brûler les moteurs
- **Paradoxe** : on tolère volontairement plus de bruit pour avoir moins de chaleur moteur

**À implémenter en v3** : ajouter "Style de vol" dans le profil drone :
- Freestyle / Long Range / Racing → tune standard
- Bangers / Intérieur → profil "Loquet" (recommandations différentes, seuils plus lâches)

### Altitude (17/04/2026)
**Le pilote vole à 1200m d'altitude** — différence de tune par rapport au niveau de la mer
est significative (densité de l'air, efficacité des hélices, réponse moteur).

**À implémenter en v3** :
- Le BBL contient les données GPS (altitude GPS dans les frames G).
- Lire l'altitude GPS moyenne → si > 800m, afficher une alerte :
  "Vous volez en altitude — les recommandations sont calibrées pour le niveau de la mer.
   Votre drone peut nécessiter des PIDs différents (P légèrement plus haut, D plus bas)."
- Éventuellement : correction automatique des seuils de recommandation selon l'altitude.

---

## Prochaines étapes

### v2 (en cours)
- [x] FFT spectre PSD avec marqueurs filtres
- [x] Spectrogramme Roll
- [x] Détection vibrations mécaniques (peaks non couverts par RPM filter)
- [ ] Affiner les seuils de recommandations sur plusieurs vols réels
- [ ] Step-response graph zoomable (setpoint vs gyro, lecture intuitive)
- [ ] Améliorer fly_mask (exclusion des décollages/atterrissages)

### v3
- [ ] Profil "Style de vol" : Freestyle / Racing / Long Range / Bangers
- [ ] Lecture altitude GPS depuis frames G du BBL → alerte haute altitude
- [ ] CLI dump complet (toutes les valeurs, pas juste les modifiées)
- [ ] Affichage PID avant/après côte à côte
- [ ] Export PDF du rapport de diagnostic

### Distribution
- [ ] PyInstaller → `.exe` Windows standalone (~120 Mo)
- [ ] Test sur machine Liam (DESKTOP-8CA9R8L, Python 3.11.9)
- [ ] Mac : tester avec la même codebase PyQt6

---

## Environnements

### Machine principale — Papa (DESKTOP-QCBKGND)
- Python 3.14, PyQt6, pyqtgraph, pandas, numpy installés.
- `blackbox_decode.exe` dans `tools/`.

### Machine secondaire — Liam (DESKTOP-8CA9R8L)
- Windows 10, Python 3.11.9 (via VoixClaire : `C:\Users\liam0\AppData\Local\VoixClaire\python\python.exe`).
- PyQt6 déjà présent. À tester.

---

## Reprendre le projet

```bash
git clone https://github.com/bouyous/PID-black-box.git blackbox-analyzer
cd blackbox-analyzer
pip install -r requirements.txt
# Copier blackbox_decode.exe dans tools/
# (source : PIDtoolboxPro_v0.81_win/PIDtoolboxPro_v0.81_win/main/blackbox_decode.exe)
python src/main.py
```
