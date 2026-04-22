# Template de release notes

**À copier/coller au début de chaque nouveau `RELEASE_NOTES_vX.Y.Z.md`.**
La section « Installation » doit TOUJOURS être présente, dans cet ordre :
Windows d'abord (le plus simple : double-clic), Mac ensuite, Linux en dernier.

---

## 📥 Installation

### 🪟 Windows — recommandé, le plus simple

1. Téléchargez **`BlackBoxAnalyzer_vX.Y.Z.exe`** depuis la section *Assets* ci-dessous.
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
   (contourne Gatekeeper, rend exécutable)
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

## Ce qui change dans cette version

<!-- … détails de la version … -->
