# BlackBox Analyzer v1.10.2 - Protocole terrain et Vibrations

**Date :** 2 mai 2026

Cette version transforme la methode Blackbox terrain en diagnostic lisible :
une seule blackbox peut contenir une reference calme courte, des rampes de gaz
et du freestyle exploitable.

## Protocole Blackbox

- Detection automatique des phases utiles : reference calme, rampes de gaz et
  vol tune.
- Les rampes sont detectees sur une commande gaz lissee pour mieux coller aux
  vols reels, pas seulement aux rampes parfaites.
- Les impulsions freestyle courtes sont additionnees pour ne plus sous-estimer
  les flips, rolls, yaw et reprises bas gaz.
- L'onglet Diagnostic affiche la confiance du protocole et les moments detectes.
- La page d'accueil affiche la marche a suivre recommandee avant chargement.

## Expert et diagnostic

- `FFT` est renomme `Vibrations`, avec un vocabulaire plus lisible.
- Les harmoniques moteur utilisent maintenant les poles moteur pour convertir
  eRPM en frequence mecanique.
- Le mode Expert regroupe les courbes step response, vibrations, PID Roll,
  PID Pitch, PID Yaw, gyroscope, moteurs, balance P/I/D et CLI dump.
- Le CLI pret a copier-coller est aussi disponible directement dans Diagnostic.

## Verification terrain

- 17 blackbox terrain du dossier `bb` decodees avec succes.
- 18 sessions analysees sans erreur.
- Detection protocole : 7 sessions fortes, 10 moyennes, 1 limitee.
- Rampes gaz detectees sur toutes les sessions testees.

## Verification technique

- Compilation Python : OK
- Tests unitaires : OK, 10 tests
- Smoke test Qt local : OK
- Batch terrain : OK

## Installation

### Windows

Telecharger `BlackBoxAnalyzer_v1.10.2.exe` depuis les assets de la release.

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
