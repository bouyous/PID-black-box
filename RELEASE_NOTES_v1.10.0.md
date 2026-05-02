# BlackBox Analyzer v1.10.0 - Navigation claire et mode Expert

**Date :** 2 mai 2026

Cette version reorganise le diagnostic pour garder une lecture simple au
premier niveau, tout en conservant les outils techniques avances.

## Nouveautes

### Navigation laterale

- Les onglets principaux passent sur le cote gauche.
- Le premier niveau garde les vues utiles pour decider vite :
  - Contexte
  - Diagnostic
  - Latence
  - Symptomes
  - Check OK
  - Plan de vol
  - Expert

### Onglet Expert

Les vues les plus techniques sont regroupees dans `Expert` :

- Courbes Step Response
- Balance P/I/D
- CLI Dump

Le but est de ne pas noyer un pilote debutant dans les courbes, tout en laissant
les outils avances disponibles immediatement pour ceux qui veulent lire plus
finement la blackbox.

## Verification

- Compilation Python : OK
- Tests unitaires : OK, 8 tests
- Smoke test Qt local : OK

## Installation

### Windows

Telecharger `BlackBoxAnalyzer_v1.10.0.exe` depuis les assets de la release.

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
