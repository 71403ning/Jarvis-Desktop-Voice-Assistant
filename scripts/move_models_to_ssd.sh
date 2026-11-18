#!/bin/bash
# 把內建硬碟上的 AI 模型資料夾搬到外接硬碟，並在原位置留下捷徑（symlink），
# 讓各個工具不用改設定就能繼續找到模型。
#
#   bash scripts/move_models_to_ssd.sh                      # 預覽：只列出清單
#   bash scripts/move_models_to_ssd.sh --apply              # 實際搬移
#   SSD=/Volumes/MyDrive bash scripts/move_models_to_ssd.sh --apply
#
# 處理的資料夾（不存在或已經在外接硬碟上就跳過）：
#   ~/.ollama/models            Ollama（Breeze、TAIDE、百龍…）
#   ~/.cache/huggingface        Hugging Face 下載快取
#   ~/.cache/whisper            OpenAI Whisper
#   ~/.lmstudio/models          LM Studio
#   ~/.cache/lm-studio/models   LM Studio（舊版）
set -uo pipefail

SSD="${SSD:-/Volumes/SSD}"
DEST="$SSD/ai-models"
APPLY=0
[ "${1:-}" = "--apply" ] && APPLY=1

# 名稱|來源資料夾
ITEMS="ollama|$HOME/.ollama/models
huggingface|$HOME/.cache/huggingface
whisper|$HOME/.cache/whisper
lmstudio|$HOME/.lmstudio/models
lmstudio-old|$HOME/.cache/lm-studio/models"

bytes() {  # 計算資料夾內一般檔案的總大小，macOS/Linux 皆適用
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
  echo "外接硬碟 $SSD 沒有掛載或無法寫入。請用 SSD=/Volumes/<磁碟名稱> 指定。" >&2
  exit 1
fi

echo "目的地：$DEST   （剩餘空間：$(human "$(free_bytes "$SSD")")）"
[ $APPLY -eq 0 ] && echo "預覽模式：不會做任何變更。確認後加上 --apply 再執行一次才會搬移。"
echo

todo=""
need=0
while IFS='|' read -r name src; do
  if [ -L "$src" ]; then
    echo "[已完成] $src -> $(readlink "$src")（已經是捷徑）"
    continue
  fi
  if [ ! -d "$src" ]; then
    echo "[跳過]   $src（不存在）"
    continue
  fi
  size=$(bytes "$src")
  echo "[搬移]   $src  $(human "$size")  ->  $DEST/$name"
  todo="$todo$name|$src
"
  need=$((need + size))
done <<EOF
$ITEMS
EOF

echo
if [ -z "$todo" ]; then
  echo "沒有需要搬移的資料夾：模型都已經在外接硬碟上，或根本不存在。"
  exit 0
fi
echo "共需搬移：$(human "$need")"
if [ "$need" -ge "$(free_bytes "$SSD")" ]; then
  echo "$SSD 的剩餘空間不足。" >&2
  exit 1
fi
[ $APPLY -eq 0 ] && exit 0

echo "==> 先關閉 Ollama，避免模型檔案正在使用中"
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
    echo "!! 複製失敗；$src 保持原狀未刪除" >&2
    failed=1
    continue
  fi
  a=$(bytes "$src"); b=$(bytes "$dst")
  if [ "$b" -lt "$a" ]; then
    echo "!! 複製不完整（$(human "$b") / $(human "$a")）；$src 保持原狀未刪除" >&2
    failed=1
    continue
  fi
  # 確認複製完整後才刪除原檔，再建立捷徑。
  rm -rf "$src" && ln -s "$dst" "$src"
  echo "   完成；$src 已改為捷徑"
done <<EOF
$todo
EOF

echo
echo "內建硬碟目前剩餘：$(human "$(free_bytes "$HOME")")"
echo "請重新啟動 Ollama（open -a Ollama 或 brew services start ollama），再執行 ollama list 確認"
exit $failed
