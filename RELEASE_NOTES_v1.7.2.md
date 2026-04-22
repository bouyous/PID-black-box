# BlackBox Analyzer v1.7.2 — Fix installation Mac (fix_mac.sh dans le zip)

**Date :** 22 avril 2026

## 📥 Installation

### 🪟 Windows — recommandé, le plus simple

1. Téléchargez **`BlackBoxAnalyzer_v1.7.2.exe`** depuis la section *Assets* ci-dessous.
2. **Double-cliquez** sur le fichier téléchargé.
3. C'est tout. Aucune installation, aucune dépendance Python.

> Si Windows SmartScreen affiche un avertissement : *Informations complémentaires* → *Exécuter quand même*.

### 🍎 macOS

1. Téléchargez **`BlackBoxAnalyzer-macOS.zip`** depuis la section *Assets* ci-dessous.
2. Double-cliquez sur le `.zip` pour le dézipper — vous obtenez 3 fichiers :
   - `BlackBoxAnalyzer.app`
   - `fix_mac.sh`
   - `LISEZ-MOI.txt`
3. **Première fois seulement** — ouvrez le **Terminal** et copiez-collez cette ligne :
   ```bash
   xattr -cr ~/Downloads/BlackBoxAnalyzer.app
   ```
   > 💡 **Alternative encore plus simple :** dans Terminal, tapez `bash ` (avec espace),
   > puis **glissez-déposez `fix_mac.sh` dans le Terminal**, puis appuyez sur Entrée.
4. **Double-cliquez** sur `BlackBoxAnalyzer.app`. ✅

> **⚠️ Si votre ami a eu l'erreur `bash: fix_mac.sh: No such file or directory`** sur la v1.7.1 :
> c'est parce que le script n'était PAS dans le .zip (il n'était que dans le repo git).
> **Cette v1.7.2 corrige le bug** : `fix_mac.sh` et `LISEZ-MOI.txt` sont maintenant livrés
> à l'intérieur du `.zip` à côté du `.app`.

### 🐧 Linux

```bash
tar -xzf BlackBoxAnalyzer-Linux.tar.gz
chmod +x BlackBoxAnalyzer
./BlackBoxAnalyzer
```

---

## 🛠️ Ce qui change dans cette version

### Fix critique Mac : `fix_mac.sh` manquait dans le .zip

Sur la v1.7.1, le `.zip` macOS ne contenait que `BlackBoxAnalyzer.app` — le script
`fix_mac.sh` existait seulement dans le repo git. Résultat : les utilisateurs
Mac qui téléchargeaient le .zip obtenaient une erreur `bash: fix_mac.sh: No such
file or directory` au moment d'essayer de débloquer Gatekeeper.

**Correctif :** le workflow `build-mac.yml` intègre maintenant dans le .zip :
- `BlackBoxAnalyzer.app` (l'application)
- `fix_mac.sh` (script autonome de déblocage Gatekeeper, n'a pas besoin du repo)
- `LISEZ-MOI.txt` (instructions courtes en français)

### Nouveau script `fix_mac_standalone.sh` (source)

Script autonome à côté du .app dans le zip — ne dépend plus du reste du repo.
Il fait :
- `xattr -cr` sur le `.app` pour supprimer la quarantaine Gatekeeper
- `chmod +x` sur le contenu `Contents/MacOS/`

### Template release notes mis à jour

`docs/RELEASE_NOTES_TEMPLATE.md` propose maintenant la ligne de commande
**one-liner** `xattr -cr ~/Downloads/BlackBoxAnalyzer.app` comme alternative
prioritaire — fonctionne même sans le script.

## Contenu fonctionnel (inchangé depuis v1.7.0)

Matrice diagnostique Jello / Jitter officielle — voir les notes de la v1.7.0
pour le détail.
