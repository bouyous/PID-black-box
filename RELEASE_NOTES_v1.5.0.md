# BlackBox Analyzer v1.5.0 — Support Mac + Diagnostic symptomatique

**Date :** 22 avril 2026

## 🍎 Support macOS natif

Cette version corrige les deux problèmes bloquants signalés par les utilisateurs Mac :

### Bug 1 — « L'app ne s'ouvre pas en double-cliquant, je dois faire clic droit → Ouvrir »

C'est la protection Gatekeeper de macOS qui bloque les binaires non signés.
**Solution** : un nouveau script `fix_mac.sh` à exécuter une seule fois après le téléchargement :

```bash
bash fix_mac.sh
```

Il supprime l'attribut de quarantaine (`xattr -cr`), rend les binaires exécutables (`chmod +x`),
vérifie l'installation Python et les dépendances. Après ça, l'app s'ouvre normalement.

### Bug 2 — « Quand je glisse une blackbox, ça charge à l'infini et ça bugge »

Deux causes identifiées et corrigées :

1. **Le parser cherchait uniquement `blackbox_decode.exe`** (binaire Windows) — sur Mac il faut
   `blackbox_decode` ou `blackbox_decode_mac`. La fonction `find_decoder()` est maintenant
   multi-plateforme et cherche aussi dans Homebrew (`/opt/homebrew/bin/`).

2. **Le décodage bloquait le thread Qt principal**, ce qui gelait l'UI. Le décodage tourne
   maintenant dans un `QThread` (`DecodeWorker`) séparé. L'UI reste réactive, le statut
   indique l'avancement, et un timeout de 2 minutes empêche les freezes infinis sur fichiers corrompus.

## 🩺 Nouvelle base de connaissances symptomatique

Nouveau module `analysis/symptom_db.py` avec 5 règles diagnostiques complètes basées sur
la base de connaissances DeerFlow :

- **Gelo** — Oscillations nez à basse altitude / Flutter
- **Geno** — Mouvements erratiques / Jitter toutes directions
- **Slug** — Drone mou / Réponse lente
- **Over** — Overshoot / Dépassement excessif
- **Vib mécanique** — Vibrations non filtrées

Chaque règle décompose le symptôme en :
- **Causes par vecteur** : Software, PID, Électrique, Mécanique, Gyro
- **Tests quantifiables** (ex : Vripple > 1.2 × V_nominal, settling time < 0.3s)
- **Actions correctives** précises
- **Niveaux de risque** au sur-réglage
- **Arbre de décision** étape par étape

## 🩺 Nouvel onglet « Symptômes » dans l'UI

Un nouvel onglet apparaît dans le panneau de diagnostic, avec des cartes colorées par
vecteur de cause. Si un symptôme est détecté dans la blackbox, l'onglet s'ouvre
automatiquement.

## 📚 Documentation Mac complète dans le README

Le README contient maintenant une section pas-à-pas pour l'installation Mac, Linux
et Windows depuis les sources, avec les lignes de commande exactes pour cloner,
installer les dépendances, et lancer l'application.

## Compatibilité

- ✅ Windows 10/11 (.exe standalone ou source)
- ✅ macOS (Apple Silicon + Intel)
- ✅ Linux (Debian/Ubuntu testé)
- ✅ Python 3.11+

## Mise à jour

```bash
cd ~/Documents/PID-black-box
git pull
python3 src/main.py     # Mac/Linux
python src\main.py      # Windows
```
