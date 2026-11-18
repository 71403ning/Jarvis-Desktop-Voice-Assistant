#!/bin/bash
# One-shot installer for Jarvis on an Apple Silicon Mac (e.g. Mac mini M4).
# Usage:  bash scripts/setup_mac.sh                      (downloads Breeze only)
#         JARVIS_MODELS="breeze taide bailong" bash scripts/setup_mac.sh
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "$(uname -s)" != "Darwin" ]; then
  echo "This script is for macOS. On Windows/Linux follow README.md." >&2
  exit 1
fi
if ! command -v brew >/dev/null 2>&1; then
  echo "Homebrew is required. Install it from https://brew.sh and run this again." >&2
  exit 1
fi

MODELS="${JARVIS_MODELS:-breeze}"

echo "==> Installing Python 3.12 and PortAudio"
brew install python@3.12 portaudio

# Use one Ollama only: two installs (Ollama.app + Homebrew) run different
# versions and fight over port 11434.
if [ -d /Applications/Ollama.app ]; then
  echo "==> Ollama.app found; using it (keep it in Login Items so it starts after reboot)"
  if brew list ollama >/dev/null 2>&1; then
    echo "    Homebrew also has ollama. Remove the duplicate with:"
    echo "      brew services stop ollama && brew uninstall ollama"
  fi
  curl -fs http://localhost:11434/api/tags >/dev/null 2>&1 || open -a Ollama
elif command -v ollama >/dev/null 2>&1; then
  echo "==> Using existing ollama at $(command -v ollama)"
else
  echo "==> Installing Ollama with Homebrew and starting it as a background service"
  brew install ollama
  brew services start ollama
fi

echo "==> Creating virtual environment in .venv"
PY="$(brew --prefix python@3.12)/bin/python3.12"
"$PY" -m venv .venv
.venv/bin/pip install --upgrade pip
CFLAGS="-I$(brew --prefix portaudio)/include" \
LDFLAGS="-L$(brew --prefix portaudio)/lib" \
  .venv/bin/pip install -r requirements.txt

echo "==> Waiting for Ollama"
for _ in $(seq 1 30); do
  curl -fs http://localhost:11434/api/tags >/dev/null && break
  sleep 1
done

echo "==> Downloading Taiwanese models: $MODELS (several GB each, first time only)"
# shellcheck disable=SC2086
bash scripts/pull_tw_models.sh $MODELS || echo "!! Some models failed; Jarvis still runs with the rest."

echo "==> Running self-tests"
.venv/bin/python -m unittest discover -s tests

cat <<EOF

Done. Start Jarvis with:
  JARVIS_LANG=zh-TW .venv/bin/python Jarvis/jarvis.py           # voice
  JARVIS_LANG=zh-TW .venv/bin/python Jarvis/jarvis.py --text    # keyboard / SSH

Notes:
  * If ~/.ollama/models points to an external drive, macOS must allow Ollama
    to use it (System Settings > Privacy & Security > Files and Folders /
    Removable Volumes), or downloads fail with "operation not permitted".
  * Mac mini has no built-in microphone: plug in a USB mic, webcam or headset.
  * macOS will ask Terminal for Microphone (and Screen Recording for screenshots)
    permission the first time. Allow it in System Settings > Privacy & Security.
EOF
