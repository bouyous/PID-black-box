# BlackBox Analyzer v1.9.7 - Lecture PID, latence et rebonds bas gaz

**Date :** 2 mai 2026

Cette version ajoute des outils de lecture plus proches du terrain FPV :
rebonds apres flips/rolls gaz coupes, balance P/I/D/FF, latence selon le type
de drone, et marche a suivre blackbox.

## Nouveautes

### Onglet P/I/D

- Lecture des traces `axisP`, `axisI`, `axisD` et `axisF` depuis la blackbox.
- Affichage RMS par axe.
- Ratio D/P pour visualiser le compromis amortissement / rebond.
- Verdict lisible : D trop bas, D haut, OK, donnees indisponibles.

### Onglet Latence

- Cibles differentes selon le profil :
  - 5 pouces freestyle/race : reponse vive et latence faible.
  - 7/10 pouces long range : plus de douceur, meilleure stabilite vent/autonomie.
- Affichage du lag gyro/setpoint, rise time et overshoot par axe roll/pitch.
- Aide a lire le compromis filtres ouverts vs filtres conservateurs.

### Onglet Plan de vol

Procedure conseillee en trois logs :

1. Structure et filtres : 2 a 3 minutes calmes, peu de grosses commandes.
2. Rampes de gaz : bas gaz vers plein gaz puis redescente, 1 a 3 fois.
3. Ressenti pilote : flips, rolls, yaw, reprises bas gaz, mouvements axes separes.

## Corrections terrain

### Rebond gaz coupes apres figure

Les flips/rolls a bas gaz ne sont plus ignores par le masque de vol. Le logiciel
peut maintenant detecter les rebonds apres une figure gaz coupes et recommander
D, D_min ou `iterm_relax_cutoff` quand c'est coherent.

### Resistance au vent

Le mode "stabilite au vent" pousse mieux l'autorite I et D_min au lieu de rester
trop neutre sur certains profils.

### Detection batterie Li-ion

La detection du nombre de cellules utilise maintenant la tension moyenne et la
tension max, pour eviter de classer un 6S Li-ion bas comme un 4S.

### eRPM et filtre RPM

La frequence moteur est convertie avec les poles moteur. Les pics couverts par
RPM filter sont donc analyses avec une frequence mecanique plus realiste.

### CLI PID brut

Le dump CLI brut dedoublonne les recommandations par parametre, comme le mode
sliders, pour eviter les doublons contradictoires.

### Temp Windows

Le decodeur blackbox choisit un dossier temporaire reellement writable avec
fallback si `%TEMP%` est bloque par Windows ou un antivirus.

## Verification

- Compilation Python : OK
- Tests unitaires : OK, 7 tests
- Smoke test Qt local : OK

## Installation

### Windows

1. Telecharger `BlackBoxAnalyzer_v1.9.7.exe` depuis les assets de la release.
2. Double-clic.

### macOS

- Apple Silicon : `BlackBoxAnalyzer-macOS-AppleSilicon.zip`
- Intel : `BlackBoxAnalyzer-macOS-Intel.zip`
- Si Gatekeeper bloque : `xattr -cr ~/Downloads/BlackBoxAnalyzer.app`

### Linux

```bash
tar -xzf BlackBoxAnalyzer-Linux.tar.gz
chmod +x BlackBoxAnalyzer
./BlackBoxAnalyzer
```
