#!/data/data/com.termux/files/usr/bin/bash
# REVVL Tab 2 Super Tablet app bridge: single-file installer.
# Installs only the startup service script, keeps existing dashboards and browser data.
set -eu
if [ "${PREFIX:-}" != "/data/data/com.termux/files/usr" ]; then
  printf 'ERROR: Open your existing Termux app before running this script.\n' >&2
  exit 1
fi
ROOT="$HOME/supertab"
TARGET="$ROOT/bin/REVVL-services.sh"
mkdir -p "$ROOT/bin" "$HOME/.termux"
if [ -e "$TARGET" ]; then
  cp -p "$TARGET" "$TARGET.backup.$(date '+%Y%m%d-%H%M%S')"
fi
cat > "$TARGET" <<'REVVL_EMBEDDED_SCRIPT'
#!/data/data/com.termux/files/usr/bin/bash
# REVVL Super Tablet local servers. No root, no deletions, no network exposure.
set -u
export PATH="/data/data/com.termux/files/usr/bin:/system/bin:/system/xbin:$PATH"
HOME="/data/data/com.termux/files/home"
ROOT="$HOME/supertab"
V2="$ROOT/creator-v2"
mkdir -p "$ROOT" "$V2"
LOG="$ROOT/revvl-services.log"
echo "[$(date)] REVVL services starting" >> "$LOG"
port_ready() {
  python -c 'import socket,sys; s=socket.socket(); s.settimeout(0.7); r=s.connect_ex(("127.0.0.1",int(sys.argv[1]))); s.close(); sys.exit(0 if r==0 else 1)' "$1"
}
if ! command -v python >/dev/null 2>&1; then
  echo "Python missing; install via: pkg install python" >> "$LOG"
  exit 1
fi
# Leave any existing listener unchanged.
if ! port_ready 8765; then
  # The original dashboard may be under one of these known names.
  for file in "$ROOT/index.html" "$ROOT/dashboard/index.html" "$ROOT/SUPER_TABLET_DASHBOARD.html" "$HOME/index.html" "$ROOT/legacy-quicklaunch/index.html"; do
    if [ -f "$file" ]; then
      mkdir -p "$ROOT/legacy-mount"
      ln -sfn "$file" "$ROOT/legacy-mount/index.html"
      nohup python -m http.server 8765 --bind 127.0.0.1 --directory "$ROOT/legacy-mount" >> "$ROOT/legacy-8765.log" 2>&1 </dev/null &
      break
    fi
  done
  # If no known HTML file exists, preserve user files and log the missing source.
  if ! port_ready 8765; then
    echo "Original 8765 service not found. Leave unchanged; user may need original launcher." >> "$LOG"
  fi
fi
if ! port_ready 8766; then
  if [ -s "$V2/REVVL_Super_Tablet_v2.html" ]; then
    nohup python -m http.server 8766 --bind 127.0.0.1 --directory "$V2" >> "$V2/server.log" 2>&1 </dev/null &
  else
    echo "Cannot start 8766: REVVL_Super_Tablet_v2.html missing." >> "$LOG"
  fi
fi
if ! port_ready 8767 && [ -s "$V2/revvl_chatgpt_api.py" ]; then
  nohup python -u "$V2/revvl_chatgpt_api.py" >> "$V2/chatgpt_api.log" 2>&1 </dev/null &
fi
echo "[$(date)] Startup requests complete" >> "$LOG"
REVVL_EMBEDDED_SCRIPT
chmod 700 "$TARGET"
P="$HOME/.termux/termux.properties"
if ! grep -Eq '^[[:space:]]*allow-external-apps[[:space:]]*=[[:space:]]*true([[:space:]]*(#.*)?)?$' "$P" 2>/dev/null; then
  printf '\nThe Android REVVL launcher needs permission to ask Termux to run startup scripts.\n'
  printf 'Enable allow-external-apps? This lets Android apps granted the Termux RUN_COMMAND permission execute commands. [y/N] '
  read -r approval || approval=N
  case "$approval" in
    y|Y|yes|YES)
      if [ -f "$P" ]; then cp -p "$P" "$P.backup.$(date '+%Y%m%d-%H%M%S')"; fi
      if [ -f "$P" ]; then
        sed -i '/^[[:space:]]*allow-external-apps[[:space:]]*=/d' "$P"
      fi
      printf '\nallow-external-apps=true\n' >> "$P"
      if command -v termux-reload-settings >/dev/null 2>&1; then termux-reload-settings; fi
      printf 'Enabled external app support.\n'
      ;;
    *) printf 'External app support remains disabled. You can enable it later.\n' ;;
  esac
fi
printf '\nREVVL app bridge installed: %s\n' "$TARGET"
printf 'Your existing dashboards, shortcuts, Termux installation, and Chrome projects are preserved.\n'
printf 'Now open the REVVL Super Tablet Android app and grant RUN_COMMAND permission if requested.\n'
