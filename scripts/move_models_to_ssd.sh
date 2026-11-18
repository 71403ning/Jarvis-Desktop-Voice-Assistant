#!/bin/bash
# Move local AI model folders from the internal disk to an external drive and
# leave a symlink behind, so every tool keeps finding its models.
#
#   bash scripts/move_models_to_ssd.sh                      # dry run: only report
#   bash scripts/move_models_to_ssd.sh --apply              # really move
#   SSD=/Volumes/MyDrive bash scripts/move_models_to_ssd.sh --apply
#
# Folders handled (skipped when missing or already on the drive):
#   ~/.ollama/models            Ollama (Breeze, TAIDE, Bailong, ...)
#   ~/.cache/huggingface        Hugging Face downloads
#   ~/.cache/whisper            OpenAI Whisper
#   ~/.lmstudio/models          LM Studio
#   ~/.cache/lm-studio/models   LM Studio (older versions)
set -uo pipefail

SSD="${SSD:-/Volumes/SSD}"
DEST="$SSD/ai-models"
APPLY=0
[ "${1:-}" = "--apply" ] && APPLY=1

# name|source folder
ITEMS="ollama|$HOME/.ollama/models
huggingface|$HOME/.cache/huggingface
whisper|$HOME/.cache/whisper
lmstudio|$HOME/.lmstudio/models
lmstudio-old|$HOME/.cache/lm-studio/models"

bytes() {  # total size of regular files in a folder, portable across macOS/Linux
  python3 - "$1" <<'PY'
import os, sys
total = 0
for root, _dirs, files in os.walk(sys.argv[1]):
    for f in files:
        p = os.path.join(root, f)
        if not os.path.islink(p):
            total += os.path.getsize(p)
print(total)
PY
}
human() { python3 -c "import sys;n=float(sys.argv[1]);u='B KB MB GB TB'.split();i=0
while n>=1024 and i<4: n/=1024;i+=1
print(f'{n:.1f} {u[i]}')" "$1"; }
free_bytes() { df -Pk "$1" | awk 'NR==2 {print $4 * 1024}'; }

if [ ! -d "$SSD" ] || [ ! -w "$SSD" ]; then
  echo "External drive $SSD is not mounted or not writable. Set SSD=/Volumes/<name>." >&2
  exit 1
fi

echo "Target: $DEST   (free: $(human "$(free_bytes "$SSD")"))"
[ $APPLY -eq 0 ] && echo "DRY RUN - nothing will be changed. Re-run with --apply to move."
echo

todo=""
need=0
while IFS='|' read -r name src; do
  if [ -L "$src" ]; then
    echo "[ok]   $src -> $(readlink "$src")  (already a link)"
    continue
  fi
  if [ ! -d "$src" ]; then
    echo "[skip] $src (not present)"
    continue
  fi
  size=$(bytes "$src")
  echo "[move] $src  $(human "$size")  ->  $DEST/$name"
  todo="$todo$name|$src
"
  need=$((need + size))
done <<EOF
$ITEMS
EOF

echo
if [ -z "$todo" ]; then
  echo "Nothing to move: all model folders are already on the external drive or absent."
  exit 0
fi
echo "Total to move: $(human "$need")"
if [ "$need" -ge "$(free_bytes "$SSD")" ]; then
  echo "Not enough free space on $SSD." >&2
  exit 1
fi
[ $APPLY -eq 0 ] && exit 0

echo "==> Stopping Ollama so no model file is in use"
if command -v osascript >/dev/null 2>&1; then
  osascript -e 'quit app "Ollama"' >/dev/null 2>&1 || true
fi
if command -v brew >/dev/null 2>&1 && brew list ollama >/dev/null 2>&1; then
  brew services stop ollama >/dev/null 2>&1 || true
fi
pkill -f "ollama serve" >/dev/null 2>&1 || true
sleep 2

failed=0
while IFS='|' read -r name src; do
  [ -z "$name" ] && continue
  dst="$DEST/$name"
  echo "==> $src -> $dst"
  mkdir -p "$dst"
  if command -v rsync >/dev/null 2>&1; then copy=(rsync -a "$src/" "$dst/"); else copy=(cp -Rp "$src/." "$dst/"); fi
  if ! "${copy[@]}"; then
    echo "!! copy failed; $src left untouched" >&2
    failed=1
    continue
  fi
  a=$(bytes "$src"); b=$(bytes "$dst")
  if [ "$b" -lt "$a" ]; then
    echo "!! copy incomplete ($(human "$b") of $(human "$a")); $src left untouched" >&2
    failed=1
    continue
  fi
  # Only delete the original after a verified copy, then link it.
  rm -rf "$src" && ln -s "$dst" "$src"
  echo "   done; $src is now a link"
done <<EOF
$todo
EOF

echo
echo "Internal disk free now: $(human "$(free_bytes "$HOME")")"
echo "Start Ollama again (open -a Ollama, or brew services start ollama), then: ollama list"
exit $failed
