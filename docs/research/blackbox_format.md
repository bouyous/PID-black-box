# Format Blackbox Betaflight — Notes de recherche

## Sources consultées
- Firmware Betaflight : `src/main/blackbox/` (blackbox_encode.c, blackbox.c)
- blackbox-tools (décodeur officiel C) : https://github.com/betaflight/blackbox-tools
- Plasmatree PID-Analyzer (Python, même approche) : https://github.com/Plasmatree/PID-Analyzer

---

## Structure d'un fichier .bbl / .bfl

### En-tête texte
Lignes commençant par `H ` (Header). Exemples :
```
H Product:Blackbox flight data recorder by Nicholas Sherlock
H Data version:2
H I interval:1
H Field I name:loopIteration,time,axisP[0],axisP[1],axisP[2],...
H Field I signed:0,0,1,1,1,...
```

L'en-tête définit tous les champs et leurs types. Il y a un en-tête par session dans le fichier.

### Types de frames (après l'en-tête)
- `I` — Intra frame : toutes les valeurs, non compressé (frame de référence)
- `P` — Inter frame : delta compressé par rapport au frame précédent
- `E` — Event frame : events spéciaux (arming, disarming...)
- `S` — Slow data : données qui changent lentement (vbat, amperage...)
- `G` — GPS (si activé)
- `H` — En-tête (début de nouvelle session dans le fichier)

---

## Approche retenue : blackbox_decode.exe (subprocess)

### Pourquoi
- Outil officiel Betaflight, maintenu par l'équipe firmware
- Gère tous les cas edge (multiple sessions, corruptions partielles, toutes versions BF)
- Plasmatree et PIDtoolbox utilisent la même approche
- Pas de maintenance de parser à assurer

### Invocation
```python
subprocess.run([path_to_decoder, bbl_file], cwd=output_dir)
```
Génère des fichiers CSV : `LOG00001.01.csv`, `LOG00001.02.csv`, etc.

---

## Champs CSV utiles

| Champ | Description | Unité |
|-------|-------------|-------|
| `time (us)` | Timestamp | microsecondes |
| `gyroADC[0/1/2]` | Gyro roll/pitch/yaw (filtré) | deg/s |
| `gyroData[0/1/2]` | Gyro brut (selon config debug) | deg/s |
| `rcCommand[0-3]` | Commandes stick (roll/pitch/yaw/throttle) | us |
| `axisP[0/1/2]` | Terme P du PID (roll/pitch/yaw) | — |
| `axisI[0/1/2]` | Terme I | — |
| `axisD[0/1/2]` | Terme D | — |
| `motor[0-3]` | Sorties moteur | us |
| `debug[0-3]` | Champs debug (dépend du debug_mode) | — |

---

## Environnement de test disponible

Deux dumps CLI Betaflight 4.5.2 sur MAMBA F722 2022B sont présents dans `C:\Users\bouyou\Documents\` :
- `BTFL_cli_backup_20260221_193227_MAMBAF722_2022B.txt`
- `BTFL_cli_backup_20260221_194730_MAMBAF722_2022B.txt`

Ces fichiers contiennent la configuration PID actuelle du drone — utile pour valider les recommandations futures.

---

## Décision bibliothèque plotting

**pyqtgraph** retenu pour v1 :
- Intégration native PyQt6 (même event loop)
- Performances supérieures pour données denses (50–8000 Hz selon looptime)
- matplotlib envisageable en v3 pour rapports statiques exportables
