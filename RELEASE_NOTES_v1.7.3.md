# BlackBox Analyzer v1.7.3 — Deux versions Mac : Intel + Apple Silicon

**Date :** 22 avril 2026

## 📥 Installation

### 🪟 Windows — recommandé, le plus simple

1. Téléchargez **`BlackBoxAnalyzer_v1.7.3.exe`** depuis la section *Assets*.
2. **Double-cliquez** sur le fichier.
3. C'est tout.

> Si SmartScreen avertit : *Informations complémentaires* → *Exécuter quand même*.

### 🍎 macOS — **CHOISIR la bonne version selon votre Mac**

**Étape 0 — vérifier l'architecture de votre Mac :** ouvrez *Terminal* et tapez :
```bash
uname -m
```

| Résultat | Votre Mac | Téléchargez ce fichier |
|----------|-----------|------------------------|
| `arm64`  | Apple Silicon (M1/M2/M3/M4, à partir de fin 2020) | **`BlackBoxAnalyzer-macOS-AppleSilicon.zip`** |
| `x86_64` | Intel (MacBook avant fin 2020)                    | **`BlackBoxAnalyzer-macOS-Intel.zip`** |

Ensuite :

1. Double-cliquez sur le `.zip` pour le dézipper — vous obtenez `BlackBoxAnalyzer.app`,
   `fix_mac.sh` et `LISEZ-MOI.txt`.
2. **Première fois seulement** — dans Terminal, copiez-collez :
   ```bash
   xattr -cr ~/Downloads/BlackBoxAnalyzer.app
   ```
3. Double-cliquez sur `BlackBoxAnalyzer.app`. ✅

### 🐧 Linux

```bash
tar -xzf BlackBoxAnalyzer-Linux.tar.gz
chmod +x BlackBoxAnalyzer
./BlackBoxAnalyzer
```

---

## 🔧 Ce qui change

### 🆕 Deux builds macOS au lieu d'un

Avant (v1.7.2), le zip Mac était compilé **uniquement pour Apple Silicon** — sur les
Mac Intel (MacBook d'avant fin 2020), l'app se lançait avec fix_mac.sh OK, mais
**crashait silencieusement** au double-clic car le binaire était arm64.

Désormais, le workflow GitHub Actions utilise une **matrice de build** :
- `macos-13` (runner Intel)       → `BlackBoxAnalyzer-macOS-Intel.zip`
- `macos-14` (runner Apple Silicon) → `BlackBoxAnalyzer-macOS-AppleSilicon.zip`

Chaque zip est vérifié à la volée : `file` sur le binaire confirme l'archi avant
de zipper. Le `LISEZ-MOI.txt` inclus dans chaque zip rappelle quelle version
télécharger selon `uname -m`.

### 🛠️ Fix permissions + sanity check archi

- Le workflow force maintenant `chmod +x` sur le binaire principal **avant** le zip
  (avant, le `.app` arrivait avec `-rw-r--r--` sur certains environnements).
- Un `file` + `grep` vérifie que l'archi du binaire correspond bien au runner.

## Contenu fonctionnel (inchangé depuis v1.7.0)

Matrice diagnostique Jello / Jitter officielle. Voir release v1.7.0 pour le détail.
