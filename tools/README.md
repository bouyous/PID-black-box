# tools/

Placez ici le décodeur Betaflight Blackbox Tools.

**Téléchargement :** https://github.com/betaflight/blackbox-tools/releases

---

## Windows

Prenez `blackbox_decode.exe` dans les assets de la dernière release.  
Nommez-le exactement `blackbox_decode.exe` et placez-le dans ce dossier.

---

## macOS

**Option 1 — Homebrew (recommandé) :**
```bash
brew install blackbox-tools
```
Le binaire sera trouvé automatiquement dans le PATH.

**Option 2 — Manuel :**
1. Téléchargez le binaire Mac depuis les releases GitHub
2. Renommez-le `blackbox_decode_mac`
3. Placez-le dans ce dossier `tools/`
4. Depuis le dossier racine du projet, exécutez une fois :
   ```bash
   bash fix_mac.sh
   ```
   Ce script supprime la quarantaine macOS et rend le binaire exécutable.

> ⚠️ **Problème : l'app ne s'ouvre pas en double-cliquant ?**  
> C'est la protection Gatekeeper de macOS. Exécutez `bash fix_mac.sh`  
> depuis le Terminal pour résoudre ça une bonne fois pour toutes.

---

## Linux

Prenez `blackbox_decode` dans les assets de la dernière release  
(ou compilez depuis les sources) et placez-le dans ce dossier.

```bash
chmod +x tools/blackbox_decode
```

---

Ces fichiers sont exclus du git (voir `.gitignore`).
