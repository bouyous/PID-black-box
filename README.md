# BlackBox Analyzer

Logiciel desktop Windows qui lit les fichiers blackbox d'un drone FPV quadcopter sous **Betaflight 4.5+**, diagnostique les problèmes de vol, et propose des ajustements PID/filtres **expliqués en français**.

L'objectif : l'utilisateur n'a pas besoin de comprendre ce que fait chaque paramètre. Il glisse le fichier blackbox, le logiciel lui dit quoi changer et pourquoi.

## État du projet

**En cours d'initialisation** (17/04/2026). Exploration du firmware Betaflight et du format blackbox en cours.

## Fonctionnalités cibles

### v1 — Fondation (priorité actuelle)
- Drag & drop d'un fichier `.bbl` / `.bfl` dans l'interface
- Lecture et décodage correct du fichier blackbox
- Affichage des données brutes : gyro, PID, RC, moteurs
- Interface PyQt6 (cohérente avec l'environnement existant)

### v2 — Diagnostic
- FFT sur les axes gyro pour détecter les vibrations
- Alertes mécaniques : hélices à vérifier, moteur HS suspecté, frame desserrée
- Détection d'oscillations PID (P trop haut, D bruité)

### v3 — Recommandations
- Analyse de la réponse de la boucle PID
- Propositions de PID/filtres avec **explication en français pour chaque changement**
- Diff lisible affiché à l'utilisateur (pas de modification directe du drone)
- L'utilisateur applique lui-même les changements via Betaflight Configurator

## Hors scope

- Écriture directe sur le drone via MSP (trop risqué pour la v1)
- Génération automatique de CLI dump Betaflight
- Support tricoptère / hexa / avion aile fixe
- Betaflight < 4.5 (format blackbox différent, complexité non justifiée)

## Stack technique (prévue)

- **Langage** : Python 3.11
- **UI** : PyQt6
- **Plotting** : pyqtgraph ou matplotlib (à décider)
- **Calcul scientifique** : numpy, scipy (FFT, filtres)
- **Parser blackbox** : à déterminer après exploration (binding vers `blackbox_decode.exe` ou parser Python pur)

## Environnement de développement

- **Machine principale** (Papa / Bouyou) : `DESKTOP-QCBKGND`
- **Machine secondaire** (Liam) : `DESKTOP-8CA9R8L` — Windows 10, Python 3.11.9 dispo via l'install VoixClaire

## Organisation

```
blackbox-analyzer/
├── README.md              ← ce fichier
├── docs/                  ← notes techniques, rapports de recherche
│   └── research/          ← exploration du firmware Betaflight
├── src/                   ← code Python (à venir)
├── tests/                 ← tests unitaires (à venir)
└── samples/               ← fichiers blackbox d'exemple pour développer (à venir)
```

## Ressources de référence

- Firmware Betaflight : https://github.com/betaflight/betaflight
- Dossier blackbox du firmware : https://github.com/betaflight/betaflight/tree/master/src/main/blackbox
- blackbox-tools (décodeur officiel C) : https://github.com/betaflight/blackbox-tools
- Plasmatree PID-Analyzer (Python, inspiration) : https://github.com/Plasmatree/PID-Analyzer
- PIDtoolbox (Matlab, inspiration) : https://github.com/bw1129/PIDtoolbox
