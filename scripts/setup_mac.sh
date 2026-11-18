#!/bin/bash
# Jarvis 一鍵安裝腳本，適用 Apple Silicon Mac（例如 Mac mini M4）。
# 用法：bash scripts/setup_mac.sh                      （只下載 Breeze）
#       JARVIS_MODELS="breeze taide bailong" bash scripts/setup_mac.sh
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "$(uname -s)" != "Darwin" ]; then
  echo "這支腳本只適用 macOS。Windows/Linux 請依照 README.md 安裝。" >&2
  exit 1
fi
if ! command -v brew >/dev/null 2>&1; then
  echo "需要先安裝 Homebrew：請到 https://brew.sh 安裝後再執行一次。" >&2
  exit 1
fi

MODELS="${JARVIS_MODELS:-breeze}"

echo "==> 安裝 Python 3.12 與 PortAudio"
brew install python@3.12 portaudio

# 只使用一套 Ollama：同時裝 Ollama.app 和 Homebrew 版會跑兩個不同版本，
# 而且會搶同一個連接埠 11434。
if [ -d /Applications/Ollama.app ]; then
  echo "==> 偵測到 Ollama.app，直接使用（請把它加入「登入項目」，重開機後才會自動啟動）"
  if brew list ollama >/dev/null 2>&1; then
    echo "    Homebrew 也裝了一份 ollama，可用以下指令移除重複的版本："
    echo "      brew services stop ollama && brew uninstall ollama"
  fi
  curl -fs http://localhost:11434/api/tags >/dev/null 2>&1 || open -a Ollama
elif command -v ollama >/dev/null 2>&1; then
  echo "==> 使用已安裝的 ollama：$(command -v ollama)"
else
  echo "==> 用 Homebrew 安裝 Ollama，並設為背景服務"
  brew install ollama
  brew services start ollama
fi

echo "==> 在 .venv 建立 Python 虛擬環境"
PY="$(brew --prefix python@3.12)/bin/python3.12"
"$PY" -m venv .venv
.venv/bin/pip install --upgrade pip
CFLAGS="-I$(brew --prefix portaudio)/include" \
LDFLAGS="-L$(brew --prefix portaudio)/lib" \
  .venv/bin/pip install -r requirements.txt

echo "==> 等待 Ollama 啟動"
for _ in $(seq 1 30); do
  curl -fs http://localhost:11434/api/tags >/dev/null && break
  sleep 1
done

echo "==> 下載台灣模型：$MODELS（每個數 GB，只有第一次需要下載）"
# shellcheck disable=SC2086
bash scripts/pull_tw_models.sh $MODELS || echo "!! 部分模型下載失敗；Jarvis 仍可使用其他已下載的模型。"

echo "==> 執行自我測試"
.venv/bin/python -m unittest discover -s tests

cat <<EOF

安裝完成。啟動 Jarvis：
  JARVIS_LANG=zh-TW .venv/bin/python Jarvis/jarvis.py           # 語音模式
  JARVIS_LANG=zh-TW .venv/bin/python Jarvis/jarvis.py --text    # 鍵盤 / SSH 模式

注意事項：
  * 如果 ~/.ollama/models 指向外接硬碟，必須在「系統設定 > 隱私權與安全性 >
    檔案與資料夾 / 卸除式卷宗」允許 Ollama 存取，否則下載會出現
    "operation not permitted"。
  * Mac mini 沒有內建麥克風：請外接 USB 麥克風、webcam 或耳機。
  * 第一次執行時 macOS 會詢問「終端機」能否使用麥克風（截圖功能還需要「螢幕錄影」），
    請在「系統設定 > 隱私權與安全性」允許。
EOF
