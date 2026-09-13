#!/usr/bin/env bash
# Registers the app in the desktop menu for the current user.
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
TARGET="$HOME/.local/share/applications/marine-doc-intelligence.desktop"
mkdir -p "$(dirname "$TARGET")"
sed "s|__INSTALL_DIR__|$HERE|g" "$HERE/marine-doc-intelligence.desktop" > "$TARGET"
chmod +x "$TARGET" "$HERE/MarineDocIntelligence"
update-desktop-database "$HOME/.local/share/applications" 2>/dev/null || true
echo "Installed menu entry: $TARGET"
