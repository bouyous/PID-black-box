# BlackBox Analyzer v1.9.0 — Refonte UI complète

**Date :** 29 avril 2026

> 🎨 **Nouvelle interface inspirée Betaflight Configurator + Task Manager Windows.**
> Sidebar à icônes repliable, drag & drop sur toute la fenêtre, bandeau
> température moteurs persistant qui ne se cache jamais, démarrage en plein
> écran adaptatif (720p → 4K). Aucun changement de logique d'analyse — c'est
> de la pure refonte visuelle.

## 📥 Installation

### 🪟 Windows — le plus simple

1. Téléchargez **`BlackBoxAnalyzer_v1.9.0.exe`** depuis *Assets* ci-dessous.
2. **Double-cliquez**. C'est tout.

### 🍎 macOS

**Étape 0 — vérifier l'architecture :** dans Terminal : `uname -m`

| `uname -m` | À télécharger |
|------------|---------------|
| `arm64`    | `BlackBoxAnalyzer-macOS-AppleSilicon.zip` |
| `x86_64`   | `BlackBoxAnalyzer-macOS-Intel.zip` |

Puis :
1. Double-clic sur le `.zip` pour dézipper.
2. Dans Terminal (une seule fois) :
   ```bash
   xattr -cr ~/Downloads/BlackBoxAnalyzer.app
   ```
3. Double-clic sur `BlackBoxAnalyzer.app`. ✅

### 🐧 Linux

```bash
tar -xzf BlackBoxAnalyzer-Linux.tar.gz
chmod +x BlackBoxAnalyzer
./BlackBoxAnalyzer
```

---

## ✨ Ce qui change visuellement

### 1. Rail sidebar à gauche (style Task Manager Windows / VS Code)

Une bande verticale de 64 px à gauche avec les icônes principales toujours
visibles. Cliquer sur le bouton **☰ burger** en haut l'élargit à 260 px avec
les labels complets. La sélection active est mise en évidence par un trait
vertical bleu à gauche du bouton, comme dans les configurateurs FPV.

**Sections de navigation :**
- 📂 Ouvrir un fichier
- 🩺 Diagnostic
- 📈 Gyroscope
- 🎚 PID Roll / Pitch / Yaw
- 🌀 FFT
- ⚙ Moteurs
- 📊 Comparaison *(visible une fois une référence définie)*
- 🎯 Profil & Ressenti

### 2. Drag & drop n'importe où sur la fenêtre

L'ancien rectangle pointillé en haut a disparu. Glissez un `.bbl` ou `.bfl`
sur n'importe quelle partie de la fenêtre — un overlay bleu semi-transparent
"📂 Déposez votre fichier blackbox" apparaît pour confirmer la cible.

### 3. 🔧 Bandeau Température Moteurs **persistant et non scrollable**

C'est l'élément le plus important pour le pilote terrain : le bandeau du haut
**reste toujours visible**, quel que soit l'onglet sélectionné. Le pilote peut
toucher les cloches moteur juste après l'atterrissage et cliquer sur :

- **❄  Froids** — marge thermique disponible
- **🌡  Tièdes** — état nominal
- **🔥  Chauds** — limite avant destruction

→ **Cliquer = recalcul immédiat des recommandations.** Plus besoin d'appuyer
sur "Appliquer" : la sélection régénère automatiquement le diagnostic en
intégrant les garde-fous thermiques (les recos qui aggraveraient la chauffe
sont automatiquement bloquées en mode 🔥).

Le fond du bandeau change aussi de couleur selon l'état (rouge sur 🔥, vert
sur 🌡, bleu sur ❄) — repérable d'un coup d'œil sans avoir à lire les boutons.

Le bandeau affiche également :
- Le nom du fichier blackbox courant
- Un sélecteur de session (si la BBL contient plusieurs vols)

### 4. Vue principale en plein écran

Plus d'onglets internes empilés. Le `QStackedWidget` central donne **100% de
l'espace disponible** au graphique sélectionné. Sur un écran 1366×768, le FFT
est enfin lisible sans avoir à scroller.

### 5. Adaptive sizing — fonctionne de 720p à 4K

- Démarrage en `showMaximized()` (utilise tout l'écran disponible sans bloquer
  la barre de titre)
- `minimumSize 1024×600` (compatible netbook)
- Sidebar dans un `QScrollArea` — si l'écran est trop petit, la nav scrolle
- Splitter implicite redimensionnable entre la sidebar et le contenu
- Plus de tailles en pixels en dur dans les widgets de saisie pilote

### 6. Vue d'accueil propre

Au lancement (avant chargement d'un fichier) : un grand logo ✈, le titre, un
bouton "📂 Ouvrir un fichier blackbox…" et le rappel **« Glissez un fichier
n'importe où sur la fenêtre »**. Plus de zone de drop disgracieuse en haut.

### 7. Vue Profil & Ressenti unifiée

Tous les paramètres pilote regroupés dans une seule vue scrollable :
- Sélecteurs Taille / Style / Batterie
- 4 sliders de ressenti (Locké / Stabilité vent / Réactivité / Propreté)
- 5 questions Oui/Non post-vol

Chaque modification déclenche une régénération automatique du diagnostic.

## 🛠️ Nouveaux fichiers

| Fichier | Rôle |
|---------|------|
| `src/ui/sidebar.py` | `RailSidebar` repliable + boutons de navigation |
| `src/ui/motor_temp_bar.py` | Bandeau persistant Température Moteurs |
| `src/ui/drop_overlay.py` | Overlay semi-transparent pendant le drag |
| `src/ui/main_window.py` | Réécrit de zéro autour du `QStackedWidget` |

## 🔬 Aucun changement métier

La logique d'analyse (`analyzer.py`, `recommender.py`, `symptom_db.py`) est
**strictement inchangée**. Les détecteurs PID 8–40 Hz, le punch wobble, le
garde-fou anti-augmentation de I, la matrice diagnostique Jello/Jitter — tout
fonctionne exactement comme en v1.8.4.

C'est volontaire : refonte UI uniquement, pour réduire le risque de
régressions.

## 🐛 Limites connues

- Le bouton burger replie/déplie instantanément. Une animation fluide pourrait
  être ajoutée plus tard (cosmétique, non bloquant).
- La vue "Comparaison" reste cachée tant qu'aucune référence n'a été définie.
  Ce n'est pas un bug, c'est intentionnel.
