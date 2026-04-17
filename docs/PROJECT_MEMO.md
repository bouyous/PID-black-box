# Mémo projet — décisions prises et contexte

Ce fichier sert à reprendre le projet d'une machine à l'autre. Il consolide les décisions, l'état d'avancement, et les choix à faire.

---

## Décisions validées (17/04/2026)

### Plateforme
**Windows desktop avec PyQt6.**
- Raison : cohérent avec l'environnement VoixClaire déjà en place (Python 3.11.9 + PyQt6 dispos).
- Alternative écartée : application web locale (ajoute une complexité backend/frontend inutile).
- Alternative écartée : CLI + rapport HTML (moins convivial pour un usage "drag & drop fichier").

### Niveau d'automatisation
**Afficher un diff lisible + explications en français.**
- L'utilisateur applique les changements lui-même dans Betaflight Configurator.
- Raison : sécurité (pas de risque de bricker le drone) et pédagogique (l'utilisateur peut apprendre progressivement).
- Alternative écartée (v1) : génération automatique de CLI dump Betaflight — à considérer en v2 si demandé.
- Alternative écartée : écriture directe via MSP — trop risqué, nécessite le drone branché, hors scope.

### Scope v1
**Lire + décoder correctement le blackbox.**
- Fondation technique avant tout.
- Les recommandations PID/filtres viendront seulement une fois qu'on sait lire les données de façon fiable.
- v2 = détection de vibrations + alertes mécaniques.
- v3 = recommandations PID/filtres complètes.

### Firmware cible
**Betaflight 4.5 et plus récent.** Quadcopter uniquement (4 moteurs).

---

## Questions ouvertes (à trancher)

### Q1 — Parser blackbox : binding C ou Python pur ?
- Option A : invoquer `blackbox_decode.exe` (fourni par blackbox-tools) en subprocess, parser sa sortie CSV.
  - ✅ Rapide à mettre en place, fiable (outil officiel).
  - ❌ Dépendance à un binaire externe, moins portable, plus lent sur gros fichiers.
- Option B : parser Python pur (comme Plasmatree PID-Analyzer).
  - ✅ Distribution plus simple (pip install ... et c'est tout).
  - ❌ À maintenir soi-même si le format évolue.
- **Décision reportée** — dépend du rapport de recherche en cours.

### Q2 — Bibliothèque de plotting
- `pyqtgraph` — rapide, intégration native PyQt.
- `matplotlib` — standard, plus riche, un peu plus lent.
- **Décision reportée** — commencer avec pyqtgraph sauf contre-indication.

### Q3 — Où stocker les fichiers blackbox de test ?
- Ils font souvent plusieurs Mo chacun → exclus du git (via `.gitignore`).
- Décision : dossier `samples/` local, non commité. À documenter la source dans `samples/README.md` quand on en aura.

---

## Environnements

### Machine principale — Papa (DESKTOP-QCBKGND)
- Là où le développement principal a lieu.
- Setup à confirmer quand on bascule dessus.

### Machine secondaire — Liam (DESKTOP-8CA9R8L)
- Windows 10, Python 3.11.9 (via install VoixClaire : `C:\Users\liam0\AppData\Local\VoixClaire\python\python.exe`).
- Git 2.53.0 installé.
- PyQt6 déjà installé via l'environnement VoixClaire.

---

## Reprendre le projet depuis zéro sur l'autre machine

```bash
# 1. Cloner
git clone <URL_GITHUB> blackbox-analyzer
cd blackbox-analyzer

# 2. Lire README.md puis ce fichier (docs/PROJECT_MEMO.md)

# 3. Consulter les rapports de recherche
ls docs/research/

# 4. Continuer le travail là où on l'a laissé (voir section "Prochaines étapes" ci-dessous)
```

---

## Prochaines étapes (à faire sur la machine principale)

1. Explorer le firmware Betaflight (dossier `src/main/blackbox/`) et les outils existants (blackbox-tools, Plasmatree PID-Analyzer, PIDtoolbox) pour comprendre le format du fichier.
2. Trancher Q1 (parser C vs Python pur) à partir de cette exploration.
3. Récupérer 2-3 fichiers blackbox de test réels depuis un drone.
4. Poser un premier prototype : fenêtre PyQt6 avec drag & drop, parsing du fichier, affichage d'une courbe gyro basique.
5. Itérer.

> Note : l'exploration du firmware n'a **pas** été faite sur la machine Liam. Elle est à lancer depuis la machine principale (DESKTOP-QCBKGND).
