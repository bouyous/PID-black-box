# BlackBox Analyzer v1.7.4 — Hotfix critique : NameError au lancement

**Date :** 22 avril 2026

> ⚠️ Les binaires **v1.6.0 → v1.7.3 étaient TOUS cassés** (Windows, Mac, Linux).
> L'app crashait au chargement avec `NameError: name 'CauseVector' is not defined`.
> **La v1.7.4 corrige ça** — c'est la première version réellement fonctionnelle
> depuis la refonte symptom_db. Mettez à jour.

## 📥 Installation

### 🪟 Windows — le plus simple

1. Téléchargez **`BlackBoxAnalyzer_v1.7.4.exe`** depuis *Assets* ci-dessous.
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

## 🐛 Le bug

Traceback capturé sur macOS Intel :
```
File "ui/recommendation_panel.py", line 748, in <module>
NameError: name 'CauseVector' is not defined
[PYI-552:ERROR] Failed to execute script 'main' due to unhandled exception
```

**Cause :** lors du merge avec la v1.4.0 du PC de développement, l'import
`from analysis.symptom_db import CauseVector, RiskLevel, SymptomRule` a été
perdu dans `ui/recommendation_panel.py`. Ces trois symboles sont utilisés dans
les dictionnaires `_VECTOR_COLOR` / `_RISK_COLOR` et dans le typage de
`SymptomCard` — leur absence faisait crasher l'app à l'initialisation de
`main_window`.

**Fix :** 1 ligne ajoutée, import rétabli.

## 📚 Leçon — pourquoi les versions précédentes ne le détectaient pas

- Les workflows CI buildaient l'exécutable mais ne le lançaient pas.
- Aucune exécution de l'app en test → la NameError à l'import passait inaperçue.
- À ajouter dans une prochaine version : une étape `python -c "import ui.main_window"`
  dans les workflows pour attraper ce genre de bug avant publication.

## Contenu fonctionnel (inchangé depuis v1.7.0)

Matrice diagnostique Jello / Jitter officielle (voir release v1.7.0).
