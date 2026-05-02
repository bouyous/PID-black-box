# BlackBox Analyzer v1.10.1 - Ergonomie Expert et securite moteurs chauds

**Date :** 2 mai 2026

Cette version corrige l'ergonomie de la navigation et renforce le garde-fou
thermique.

## Ergonomie

- `Mode Expert` est maintenant une vraie entree de la barre gauche, placee sous
  `Diagnostic`.
- `Ressenti pilote` est place juste sous `Mode Expert`.
- Les vues techniques ne sont plus dans des onglets verticaux illisibles.
- Les navigations internes utilisent des boutons lisibles, encadres et arrondis.
- `CLI Dump` est visible dans `Mode Expert` avec un libelle complet.
- Le style general est plus proche Windows 10/11 : police Segoe UI, contours,
  coins arrondis et boutons plus doux.

## Securite moteurs chauds

- Quand le pilote signale des moteurs chauds, les hausses de `I` sont maintenant
  bloquees comme les hausses de P, D et FF.
- Ajout d'un test de regression pour verifier qu'un signalement `Moteurs chauds`
  ne peut pas produire une recommandation `i_*` a la hausse.

## Verification

- Compilation Python : OK
- Tests unitaires : OK, 9 tests
- Smoke test Qt local : OK

## Installation

### Windows

Telecharger `BlackBoxAnalyzer_v1.10.1.exe` depuis les assets de la release.

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
