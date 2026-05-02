# BlackBox Analyzer v1.9.8 - Courbes Step Response

**Date :** 2 mai 2026

Cette version ajoute une vue graphique de type step response pour lire la
reponse du drone comme dans les outils de tuning avances, sans copier leur
interface ni leur code.

## Nouveautes

### Onglet Step response

- Courbe moyenne normalisee par axe Roll, Pitch et Yaw.
- Axe horizontal en millisecondes, de 0 a 500 ms.
- Ligne de reference a 1.0 :
  - 1.0 = consigne atteinte.
  - au-dessus de 1.0 = overshoot / rebond.
  - sous 1.0 longtemps = reponse lente ou molle.
- Mini-graphes Peak et Latency a droite.
- Message `insufficient data` quand le log ne contient pas assez de vrais
  changements de setpoint, par exemple sur un vol stationnaire.

### Analyse conservee dans SessionAnalysis

Chaque axe stocke maintenant une courbe moyenne `StepResponseCurve` :

- `time_ms`
- `response`
- `sample_count`
- `peak`
- `latency_ms`

Cela permet a l'interface d'afficher les courbes sans recalculer depuis le CSV.

## Verification

- Compilation Python : OK
- Tests unitaires : OK, 8 tests
- Smoke test Qt local : OK

## Installation

### Windows

Telecharger `BlackBoxAnalyzer_v1.9.8.exe` depuis les assets de la release.

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
