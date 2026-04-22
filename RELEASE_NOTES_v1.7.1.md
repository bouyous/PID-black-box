# BlackBox Analyzer v1.7.1 — Builds Windows/Linux corrigés + template install

**Date :** 22 avril 2026

## 📥 Installation

### 🪟 Windows — recommandé, le plus simple

1. Téléchargez **`BlackBoxAnalyzer_v1.7.1.exe`** depuis la section *Assets* ci-dessous.
2. **Double-cliquez** sur le fichier téléchargé.
3. C'est tout. Aucune installation, aucune dépendance Python.

> Si Windows SmartScreen affiche un avertissement : *Informations complémentaires* → *Exécuter quand même*.

### 🍎 macOS

1. Téléchargez **`BlackBoxAnalyzer-macOS.zip`** depuis la section *Assets*.
2. Double-cliquez sur le `.zip` pour le dézipper.
3. **Première fois seulement** — ouvrez le Terminal dans le dossier et lancez :
   ```bash
   bash fix_mac.sh
   ```
   (contourne Gatekeeper, rend le binaire exécutable)
4. Double-cliquez sur `BlackBoxAnalyzer.app`.

**Alternative depuis les sources :**
```bash
git clone https://github.com/bouyous/PID-black-box.git
cd PID-black-box
bash fix_mac.sh
brew install blackbox-tools
python3 src/main.py
```

### 🐧 Linux

```bash
tar -xzf BlackBoxAnalyzer-Linux.tar.gz
chmod +x BlackBoxAnalyzer
./BlackBoxAnalyzer
```

---

## 🛠️ Ce qui change dans cette version

Cette version est une **hotfix** des workflows CI qui empêchaient la génération
automatique des binaires Windows et Linux depuis la v1.6.0.

### Build Windows corrigé
- `tools/blackbox_decode.exe` (108 KB) est désormais commité dans le repo.
- Le workflow n'essaie plus de télécharger depuis une release inexistante
  (`blackbox-tools` n'a pas de release publiée sur GitHub).
- Résultat : `BlackBoxAnalyzer_v1.7.1.exe` généré automatiquement à chaque tag.

### Build Linux corrigé
- Installation des dépendances manquantes : `libcairo2-dev`, `libfreetype6-dev`, `pkg-config`.
- Fallback vers la cible `obj/blackbox_decode` seule si le `make` complet échoue
  (évite d'avoir à compiler `blackbox_render` qui n'est pas utilisé).

### Nouveau template `docs/RELEASE_NOTES_TEMPLATE.md`
- Chaque nouvelle release aura systématiquement la section installation en haut,
  avec Windows en priorité (le plus simple : télécharger + double-clic), puis Mac,
  puis Linux.

## 🎯 Rappel du contenu fonctionnel (inchangé depuis v1.7.0)

- **Jello Effect** défini officiellement comme *Rolling Shutter / Vibration-Induced
  Blurring* — symptôme vidéo, pas défaut de contrôle. Souvent non corrigeable par
  Gyroflow. Cause n°1 = mécanique (dampers monture caméra).
- **Jitter** = *High-Frequency Vibration* — défaut de contrôle IMU/PID, distinct du Jello.
- Matrice diagnostique 3 vecteurs (Software / Mechanical / Electrical) par symptôme.
