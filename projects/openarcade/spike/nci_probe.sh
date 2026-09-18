#!/usr/bin/env bash
# NCI go/no-go spike: prove RetroArch cold-launch -> GET_STATUS -> PLAYING over UDP.
#
# RUN THIS IN A NORMAL TERMINAL (foreground GUI session), NOT from a background
# agent/daemon shell. A GUI app launched from a background process cannot create
# a window on macOS and segfaults at window creation (proven during the spike).
# On the Linux arcade cabinet this caveat does not apply -- plain exec works.
#
# Usage: ./nci_probe.sh <core_path> <rom_path>
#   e.g. ./nci_probe.sh \
#     "$HOME/Library/Application Support/RetroArch/cores/snes9x_libretro.dylib" \
#     "/tmp/oa_spike_rom/Killer Instinct (USA).zip"
set -uo pipefail

RA="/Applications/RetroArch.app/Contents/MacOS/RetroArch"
CORES="$HOME/Library/Application Support/RetroArch/cores"
CORE="${1:-$CORES/snes9x_libretro.dylib}"
ROM="${2:-}"
PORT=55355

# Network-command + safe-video override (appended; doesn't touch the user's main cfg).
NCICFG="$(mktemp /tmp/nci.XXXX.cfg)"
{
  echo 'network_cmd_enable = "true"'
  echo "network_cmd_port = \"$PORT\""
  echo 'video_driver = "metal"'   # metal init succeeds where vulkan/MoltenVK segfaulted
} > "$NCICFG"

probe() { echo -n "GET_STATUS" | nc -u -w1 127.0.0.1 "$PORT" 2>/dev/null; }

echo "==> Launching RetroArch (core=$(basename "$CORE")${ROM:+, rom=$(basename "$ROM")})"
# Direct exec from a foreground Terminal: args honored AND window can be created.
"$RA" -L "$CORE" ${ROM:+"$ROM"} --appendconfig "$NCICFG" >/tmp/ra_spike.log 2>&1 &
RA_PID=$!
echo "    pid=$RA_PID"

START=$(date +%s.%N)
STATUS=""
for i in $(seq 1 60); do
  sleep 0.5
  OUT="$(probe)"
  if [ -n "$OUT" ]; then
    echo "    [$(printf '%.1f' "$(echo "$(date +%s.%N) - $START" | bc)")s] $OUT"
    case "$OUT" in
      *PLAYING*) STATUS="PLAYING"; break;;
    esac
  fi
done
END=$(date +%s.%N)
ELAPSED=$(printf '%.1f' "$(echo "$END - $START" | bc)")

echo "==> Result: ${STATUS:-NO_PLAYING} after ${ELAPSED}s"
kill "$RA_PID" 2>/dev/null
rm -f "$NCICFG"
[ "$STATUS" = "PLAYING" ] && { echo "GO ✅ — cold-launch readiness detection works"; exit 0; } || { echo "NO-GO ❌ — never reached PLAYING (see /tmp/ra_spike.log)"; exit 1; }
