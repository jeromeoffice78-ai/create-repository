#!/data/data/com.termux/files/usr/bin/bash
# One-time setup. Preserves existing dashboard and browser data.
set -eu
if [ "${PREFIX:-}" != "/data/data/com.termux/files/usr" ]; then
 echo "Use this script inside your existing Termux app." >&2
 exit 1
fi
ROOT="$HOME/supertab"
mkdir -p "$ROOT/bin" "$HOME/.termux"
TARGET="$ROOT/bin/REVVL-services.sh"
if [ -f "$TARGET" ]; then
 cp -p "$TARGET" "$TARGET.backup.$(date +%Y%m%d-%H%M%S)"
fi
# Copy the included services script from the same folder as this setup script.
HERE="$(cd "$(dirname "$0")" && pwd)"
if [ ! -f "$HERE/REVVL-services.sh" ]; then
 echo "Put REVVL-services.sh beside this installer in Downloads." >&2
 exit 1
fi
cp "$HERE/REVVL-services.sh" "$TARGET"
chmod 700 "$TARGET"
P="$HOME/.termux/termux.properties"
if ! grep -Eq '^[[:space:]]*allow-external-apps[[:space:]]*=[[:space:]]*true' "$P" 2>/dev/null; then
  printf 'Allow your new REVVL app to send commands to Termux? This allows trusted apps with the RUN_COMMAND permission to execute scripts. [y/N] '
  read -r answer || answer=N
  case "$answer" in
    y|Y|yes|YES)
      if [ -f "$P" ]; then cp -p "$P" "$P.backup.$(date +%Y%m%d-%H%M%S)"; fi
      printf '\nallow-external-apps=true\n' >> "$P"
      command -v termux-reload-settings >/dev/null 2>&1 && termux-reload-settings || true
      ;;
    *) echo "External app access remains off. You can enable it later." ;;
  esac
fi
echo "REVVL service script installed at $TARGET"
echo "Existing REVVL dashboard, Termux files, and Chrome data preserved."
