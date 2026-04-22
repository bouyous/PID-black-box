#!/bin/bash
# fix_mac_standalone.sh — version autonome livrée DANS le .zip macOS à côté du .app
#
# USAGE (après avoir dézippé BlackBoxAnalyzer-macOS.zip) :
#   1. Double-cliquez sur le .zip téléchargé pour l'extraire.
#   2. Ouvrez Terminal, glissez-déposez ce script dedans, appuyez sur Entrée.
#      OU : cd vers le dossier du .app, puis : bash fix_mac_standalone.sh
#
# Ce script supprime l'attribut de quarantaine macOS (Gatekeeper) qui bloque
# le lancement du .app au double-clic. À exécuter UNE SEULE FOIS.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_PATH="$SCRIPT_DIR/BlackBoxAnalyzer.app"

echo "=== BlackBox Analyzer — Déblocage Mac Gatekeeper ==="
echo ""

if [ ! -d "$APP_PATH" ]; then
    echo "❌ BlackBoxAnalyzer.app introuvable à côté de ce script."
    echo "   Ce script doit être dans le même dossier que BlackBoxAnalyzer.app"
    echo "   (c'est le cas quand vous dézippez BlackBoxAnalyzer-macOS.zip)."
    exit 1
fi

echo "► Suppression de la quarantaine sur $APP_PATH ..."
xattr -cr "$APP_PATH" && echo "  ✅ Quarantaine supprimée." || {
    echo "  ⚠️  xattr -cr a échoué, tentative alternative..."
    xattr -d com.apple.quarantine "$APP_PATH" 2>/dev/null || true
}

echo "► Autorisation d'exécution..."
chmod -R +x "$APP_PATH/Contents/MacOS/" 2>/dev/null || true

echo ""
echo "=== Terminé ! ==="
echo ""
echo "Vous pouvez maintenant double-cliquer sur BlackBoxAnalyzer.app pour lancer l'app."
echo ""
