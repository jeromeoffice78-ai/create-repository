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
  for file in "$ROOT/index.html" "$ROOT/dashboard/index.html" "$ROOT/SUPER_TABLET_DASHBOARD.html" "$HOME/index.html"; do
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
