# Mémo projet — décisions prises et contexte

Ce fichier sert à reprendre le projet d'une machine à l'autre. Il consolide les décisions, l'état d'avancement, et les choix à faire.

---

## Décisions validées

### Plateforme (17/04/2026)
**Windows desktop avec PyQt6.**
- Raison : cohérent avec l'environnement VoixClaire déjà en place (Python 3.11.9 + PyQt6 dispos).
- Alternative écartée : application web locale (ajoute une complexité backend/frontend inutile).
- Alternative écartée : CLI + rapport HTML (moins convivial pour un usage "drag & drop fichier").

### Niveau d'automatisation (17/04/2026)
**Afficher un diff lisible + explications en français.**
- L'utilisateur applique les changements lui-même dans Betaflight Configurator.
- Raison : sécurité (pas de risque de bricker le drone) et pédagogique.
- Alternative écartée (v1) : génération automatique de CLI dump Betaflight — à considérer en v2.
- Alternative écartée : écriture directe via MSP — trop risqué, hors scope.

### Scope v1 (17/04/2026)
**Lire + décoder + visualiser le blackbox.**
- v2 = FFT + alertes mécaniques (vibrations, moteur HS, frame desserrée).
- v3 = recommandations PID/filtres avec explication en français.

### Firmware cible (17/04/2026)
**Betaflight 4.5 et plus récent.** Quadcopter uniquement (4 moteurs).

### Q1 — Parser blackbox : subprocess + blackbox_decode.exe ✅ TRANCHÉ (17/04/2026)
**Option A retenue : subprocess vers `blackbox_decode.exe`.**
- Outil officiel Betaflight, même approche que Plasmatree PID-Analyzer.
- L'exécutable va dans `tools/blackbox_decode.exe` (exclu du git).
- Téléchargement : https://github.com/betaflight/blackbox-tools/releases
- Raison du choix : fiabilité, support de tous les cas edge, pas de maintenance parser.

### Q2 — Bibliothèque de plotting : pyqtgraph ✅ TRANCHÉ (17/04/2026)
**pyqtgraph retenu.**
- Intégration native PyQt6, performances supérieures pour données denses (50–8000 Hz).
- matplotlib envisageable en v3 pour export de rapports statiques.

### Q3 — Fichiers blackbox de test (17/04/2026)
- Dossier `samples/` local, exclu du git (.gitignore).
- À récupérer sur le drone réel (MAMBA F722 2022B).

---

## État d'avancement

### v1 — Prototype fonctionnel (17/04/2026) ✅

Structure de code posée :
```
src/
├── main.py                  ← point d'entrée
├── parser/
│   └── blackbox_parser.py   ← subprocess + CSV parsing
└── ui/
    ├── main_window.py       ← fenêtre drag & drop
    └── plot_widget.py       ← GyroPlotWidget + PidPlotWidget (pyqtgraph)
tools/
└── README.md                ← instructions pour blackbox_decode.exe
docs/
└── research/
    └── blackbox_format.md   ← notes format + décisions techniques
```

**Pour tester :** il faut `blackbox_decode.exe` dans `tools/` et un vrai fichier `.bbl`/`.bfl`.

---

## Prochaines étapes

1. **Récupérer un fichier blackbox** depuis le drone MAMBA F722 2022B (SD card).
2. **Télécharger `blackbox_decode.exe`** depuis https://github.com/betaflight/blackbox-tools/releases et le placer dans `tools/`.
3. **Tester le prototype** : `python src/main.py`, glisser le fichier, vérifier les courbes gyro.
4. **v1 complète** : corriger les bugs éventuels, affiner l'UX (zoom, sélection de plage de temps).
5. **v2** : FFT sur gyro pour détecter vibrations, alertes mécaniques.

---

## Environnements

### Machine principale — Papa (DESKTOP-QCBKGND)
- Développement principal. Python 3.11+ à confirmer.
- Pour installer les dépendances : `pip install -r requirements.txt`

### Machine secondaire — Liam (DESKTOP-8CA9R8L)
- Windows 10, Python 3.11.9 (via VoixClaire : `C:\Users\liam0\AppData\Local\VoixClaire\python\python.exe`).
- Git 2.53.0 installé. PyQt6 déjà présent.

---

## Reprendre le projet sur l'autre machine

```bash
# 1. Cloner
git clone https://github.com/bouyous/PID-black-box.git blackbox-analyzer
cd blackbox-analyzer

# 2. Lire README.md puis ce fichier

# 3. Installer les dépendances
pip install -r requirements.txt

# 4. Placer blackbox_decode.exe dans tools/  (voir tools/README.md)

# 5. Lancer
python src/main.py
```
