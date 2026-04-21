#!/bin/bash
# fix_mac.sh — À exécuter UNE SEULE FOIS après téléchargement sur Mac
# Supprime l'attribut de quarantaine macOS (Gatekeeper) qui bloque l'app.
#
# USAGE :
#   1. Ouvrez Terminal
#   2. Naviguez vers le dossier de l'app :
#         cd /chemin/vers/PID-black-box
#   3. Exécutez :
#         bash fix_mac.sh
#
# Après ça, l'app s'ouvre en double-cliquant normalement.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "=== BlackBox Analyzer — Fix Mac Gatekeeper ==="
echo ""

# 1. Supprimer la quarantaine sur le dossier complet
echo "► Suppression de la quarantaine sur le dossier..."
xattr -cr "$SCRIPT_DIR" && echo "  ✅ Quarantaine supprimée." || echo "  ⚠️  xattr a échoué (ignoré)."

# 2. Rendre les binaires dans tools/ exécutables
TOOLS_DIR="$SCRIPT_DIR/tools"
if [ -d "$TOOLS_DIR" ]; then
    echo "► Autorisation d'exécution sur les binaires dans tools/..."
    for f in "$TOOLS_DIR"/blackbox_decode*; do
        if [ -f "$f" ]; then
            chmod +x "$f"
            # Supprimer aussi la quarantaine sur le binaire spécifiquement
            xattr -d com.apple.quarantine "$f" 2>/dev/null || true
            echo "  ✅ $f → exécutable"
        fi
    done
fi

# 3. Vérifier Python
echo ""
echo "► Vérification de Python..."
if command -v python3 &>/dev/null; then
    PY=$(python3 --version 2>&1)
    echo "  ✅ $PY trouvé."
else
    echo "  ❌ Python 3 non trouvé."
    echo "     Installez Python 3.11+ depuis https://www.python.org/downloads/macos/"
    exit 1
fi

# 4. Vérifier les dépendances
echo ""
echo "► Vérification des dépendances Python..."
MISSING=()
for pkg in PyQt6 pyqtgraph numpy pandas scipy; do
    if ! python3 -c "import ${pkg//-/_}" 2>/dev/null; then
        MISSING+=("$pkg")
    fi
done

if [ ${#MISSING[@]} -gt 0 ]; then
    echo "  ⚠️  Dépendances manquantes : ${MISSING[*]}"
    echo "     Installation en cours..."
    pip3 install "${MISSING[@]}" || pip3 install --user "${MISSING[@]}"
    echo "  ✅ Dépendances installées."
else
    echo "  ✅ Toutes les dépendances sont présentes."
fi

# 5. Vérifier le décodeur blackbox
echo ""
echo "► Vérification du décodeur blackbox..."
DECODER_FOUND=false
for name in blackbox_decode_mac blackbox_decode_osx blackbox_decode; do
    if [ -f "$TOOLS_DIR/$name" ]; then
        echo "  ✅ Décodeur trouvé : tools/$name"
        DECODER_FOUND=true
        break
    fi
done

if ! $DECODER_FOUND; then
    if command -v blackbox_decode &>/dev/null; then
        echo "  ✅ blackbox_decode trouvé dans le PATH système."
        DECODER_FOUND=true
    fi
fi

if ! $DECODER_FOUND; then
    echo "  ⚠️  Décodeur blackbox introuvable !"
    echo ""
    echo "     Option 1 — Homebrew (recommandé) :"
    echo "       brew install blackbox-tools"
    echo ""
    echo "     Option 2 — Manuel :"
    echo "       Téléchargez le binaire Mac depuis :"
    echo "       https://github.com/betaflight/blackbox-tools/releases"
    echo "       Renommez-le 'blackbox_decode_mac' et placez-le dans tools/"
    echo "       Puis relancez ce script."
fi

echo ""
echo "=== Terminé ! ==="
echo ""
echo "Lancez l'application avec :"
echo "  python3 src/main.py"
echo ""
