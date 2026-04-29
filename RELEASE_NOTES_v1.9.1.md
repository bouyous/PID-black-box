# BlackBox Analyzer v1.9.1 — Polish UI + convergence en 3 BBL

**Date :** 29 avril 2026

> 🛠️ **Patch v1.9.0** : 6 corrections issues du retour terrain de Liam.
> Pas de refonte — juste des ajustements ciblés.

## 📥 Installation

### 🪟 Windows — le plus simple

1. Téléchargez **`BlackBoxAnalyzer_v1.9.1.exe`** depuis *Assets* ci-dessous.
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

## 🔧 Les 6 corrections

### 1. Fix : `_divider` qui s'affichait dans la sidebar étendue

Quand on cliquait sur le bouton burger pour étendre la sidebar, deux entrées
intitulées « _divider » apparaissaient au-dessus de Diagnostic et au-dessus
de Profil & Ressenti. C'était un bug d'indexation dans le tuple `NAV_ITEMS` —
la condition de filtrage des séparateurs visuels portait sur le mauvais champ.

✅ Les séparateurs sont maintenant de fines lignes horizontales, sans texte.

### 2. Icône moteurs : ⚙ → ❋

Le pictogramme « engrenage » donnait l'impression d'un menu de paramètres.
Remplacé par **❋** (HEAVY EIGHT TEARDROP-SPOKED PROPELLER ASTERISK — c'est
littéralement son nom Unicode) qui ressemble à une hélice 8 pales et
correspond mieux à l'onglet "Moteurs".

### 3. Radio buttons CLI dump (Brut / Sliders) — refait

L'ancien rendu Qt par défaut affichait un rond gris qui s'effaçait quand on
cliquait, on ne voyait pas lequel était sélectionné.

Désormais :
- Le bouton **sélectionné** a un **fond bleu**, une bordure bleue épaisse,
  et un **point bleu rempli** dans son indicateur.
- Le bouton **non sélectionné** a un fond gris, bordure fine.
- Au survol : bordure bleue.

Plus aucun doute possible sur ce qui est coché.

### 4. Gate "J'accepte les risques" remis en place — par session

Le gate avait disparu en pratique parce qu'il utilisait `QSettings`
(persistence sur disque, jamais réinitialisée) : après 3 acceptations dans
toute la vie du logiciel, le bypass était permanent.

Désormais : **compteur en mémoire, réinitialisé à chaque ouverture du
logiciel**. Le gate apparaît jusqu'à 3 fois par session (les 3 premiers
diagnostics affichés), puis se cache pour ne plus encombrer. À la prochaine
ouverture de l'app, il revient à zéro — c'est volontaire pour qu'un pilote
ne s'habitue jamais à cliquer sans lire.

### 5. Bouton « 🎯 Profil & Ressenti » dans la barre du haut

À gauche de la température moteurs, un nouveau bouton **« 🎯 Profil & Ressenti »**
mis en évidence avec une bordure et un fond bleus :

```
[fichier .bbl ·  N sessions]  …  [🎯 Profil & Ressenti]  │  [❄][🌡][🔥]
```

- Persistant (jamais scrollé), comme la température
- Cliquable même avant qu'un fichier soit chargé (pré-configuration possible)
- Un clic ouvre la vue Profil & Ressenti (sliders, températures, 5 questions)
  en plein écran à droite

### 6. Recommender plus agressif → convergence en ~3 BBL

Retour terrain : il fallait 7 ou 8 BBL pour atteindre un tune correct.
**Cible : 3 BBL.**

**Ce qui change :**

| Paramètre | Avant | Après |
|-----------|-------|-------|
| Plafond réduction P (oscillation HF) | -15 % | **-22 %** |
| Plafond réduction P (osc. PID 8–40 Hz) | -18 % | **-25 %** |
| Plafond bump D (osc. PID) | +12 % | **+18 %** |
| Plafond bump I (drift ligne droite) | +15 % | **+22 %** |
| Plafond réduction D (bruit chauffe) | -8 % / -12 % | **-12 % / -18 %** |
| Plafond bump FF (réponse lente) | +12 % / +18 % | **+18 % / +25 %** |
| Plafond bump P (réponse lente) | +10 % / +15 % | **+16 % / +22 %** |
| Pilote « pas locké » → FF | +10 % | **+18 %** |
| Pilote « pas locké » → D | +7 % | **+12 %** |
| Pilote « pas réactif » → P | +6 % | **+12 %** |

**Changement majeur :** quand le pilote répond *« amélioration : OUI »* aux
5 questions, les deltas existants sont maintenant **amplifiés ×1.35** au lieu
d'être laissés tels quels. Logique : si le pilote nous dit qu'on va dans le
bon sens, autant pousser sans tergiverser.

**Inversement** quand *« amélioration : NON »* : les deltas sont atténués
×0.6 (au lieu de ÷2 = ×0.5) — on continue d'avancer, mais doucement.

**Garde-fous conservés :** le détecteur d'oscillation PID 8–40 Hz et le
verrou anti-augmentation-du-I restent strictement en place. Le mode 🔥
moteurs chauds bloque toujours les recos qui aggraveraient la chauffe.

## 📦 Fichiers modifiés

- `src/ui/sidebar.py` — fix `_divider`, icône moteurs, profil toujours actif
- `src/ui/motor_temp_bar.py` — ajout bouton Profil & Ressenti
- `src/ui/main_window.py` — câblage du bouton profil
- `src/ui/recommendation_panel.py` — radio buttons restylés, gate par session
- `src/analysis/recommender.py` — deltas plus agressifs (×1.35 sur amélioration)

Aucun changement de format BBL ni de fichier de config.
