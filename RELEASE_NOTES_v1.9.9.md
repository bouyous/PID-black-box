# BlackBox Analyzer v1.9.9 - Step Response multi-sessions

**Date :** 2 mai 2026

Cette version rapproche encore la vue Step Response d'un outil de lecture
terrain exploitable.

## Nouveautes

### Superposition des sessions

- La vue Step Response affiche maintenant les sessions du fichier courant sous
  forme de tests 1, 2, 3, etc.
- Une session sans donnees reste marquee `insufficient data`.
- Une session exploitable affiche sa courbe avec une couleur dediee.
- Les graphes Peak et Latency placent un point par test.

### Valeurs PID visibles

Pour chaque axe, la vue affiche les valeurs :

`P, I, D, Dm, F`

avec le nombre de steps utilises pour construire la courbe.

### Avertissement FeedForward

Quand le FeedForward est actif, l'onglet affiche un avertissement non bloquant :
la step response peut etre influencee par le terme F et doit etre lue avec
prudence pour regler P, I et D.

## Verification

- Compilation Python : OK
- Tests unitaires : OK, 8 tests
- Smoke test Qt local : OK

## Installation

### Windows

Telecharger `BlackBoxAnalyzer_v1.9.9.exe` depuis les assets de la release.

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
