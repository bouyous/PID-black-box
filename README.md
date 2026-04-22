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

---

## Télécharger le logiciel

Les versions compilées (`.exe` Windows, standalone — aucune installation requise) sont disponibles sur la page des releases :

**👉 [Toutes les versions — BlackBox Analyzer Releases](https://github.com/bouyous/PID-black-box/releases)**

Chaque release contient :
- L'exécutable Windows autonome (`BlackBoxAnalyzer_vX.X.X.exe`)
- Les notes de version (ce qui a changé, ce qui a été corrigé)

> Le logiciel est en développement actif. Les versions se succèdent régulièrement.

---

## 🍎 Installation et lancement sur macOS

> **Nouveau dans la v1.5.0** — Support Mac natif + correction du chargement infini lors du drag & drop.

### Prérequis

- **Python 3.11 ou supérieur** ([télécharger](https://www.python.org/downloads/macos/))
- **Homebrew** (recommandé pour installer le décodeur)

### Étape 1 — Récupérer le code

```bash
cd ~/Documents
git clone https://github.com/bouyous/PID-black-box.git
cd PID-black-box
```

### Étape 2 — Lancer le script de fix Mac (UNE SEULE FOIS)

```bash
bash fix_mac.sh
```

Ce script :
- Supprime la quarantaine macOS (Gatekeeper) — **plus besoin de clic droit pour ouvrir**
- Rend les binaires exécutables (`chmod +x`)
- Vérifie Python 3 et installe les dépendances Python manquantes
- Vérifie la présence du décodeur `blackbox_decode`

### Étape 3 — Installer le décodeur Betaflight (si absent)

**Option A — Homebrew (recommandé) :**
```bash
brew install blackbox-tools
```

**Option B — Manuel :** téléchargez le binaire Mac depuis
https://github.com/betaflight/blackbox-tools/releases, renommez-le `blackbox_decode_mac`
et placez-le dans le dossier `tools/` du projet.

### Étape 4 — Lancer l'application

```bash
python3 src/main.py
```

L'application s'ouvre. Glissez un fichier `.bbl` ou `.bfl` dans la zone de dépôt
et le diagnostic apparaît automatiquement.

### Mise à jour vers une nouvelle version

```bash
cd ~/Documents/PID-black-box
git pull
python3 src/main.py
```

### Dépannage Mac

| Problème | Solution |
|----------|----------|
| « L'app ne s'ouvre pas » au double-clic | Lancer `bash fix_mac.sh` une fois |
| « blackbox_decode introuvable » | `brew install blackbox-tools` |
| « ModuleNotFoundError: PyQt6 » | `pip3 install PyQt6 pyqtgraph numpy pandas scipy` |
| Chargement infini sur drag & drop | Mettez à jour vers la **v1.5.0+** (`git pull`) |

---

## 🐧 Installation et lancement sur Linux

```bash
git clone https://github.com/bouyous/PID-black-box.git
cd PID-black-box
pip3 install -r requirements.txt

# Décodeur blackbox
sudo apt install blackbox-tools   # Debian/Ubuntu
# ou téléchargez le binaire depuis https://github.com/betaflight/blackbox-tools/releases
# placez 'blackbox_decode' dans tools/ et : chmod +x tools/blackbox_decode

python3 src/main.py
```

---

## 💻 Installation et lancement sur Windows depuis les sources

Si vous préférez lancer depuis les sources plutôt que l'`.exe` standalone :

```cmd
git clone https://github.com/bouyous/PID-black-box.git
cd PID-black-box
pip install -r requirements.txt

REM Téléchargez blackbox_decode.exe depuis :
REM https://github.com/betaflight/blackbox-tools/releases
REM Placez-le dans le dossier tools/

python src\main.py
```
