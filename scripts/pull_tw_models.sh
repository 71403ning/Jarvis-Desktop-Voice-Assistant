#!/bin/bash
# Download Taiwanese Traditional-Chinese LLMs into Ollama and give them short
# names that Jarvis understands: breeze, taide, bailong.
#
#   bash scripts/pull_tw_models.sh                 # all three (~16.5 GB disk)
#   bash scripts/pull_tw_models.sh breeze taide    # only some
#
# Sources are community GGUF conversions on Hugging Face (Q4_K_M quantization).
# Change a line below if a repository moves.
#   breeze  MediaTek Research Llama-Breeze2-8B-Instruct, text only   ~4.9 GB
#   taide   TAIDE Gemma-3-TAIDE-12b-Chat-2602                         ~7.3 GB
#   bailong INX-TEXT Bailong-instruct-7B (Llama 2 based, 2024)         ~4.2 GB
set -uo pipefail

command -v ollama >/dev/null 2>&1 || { echo "Install Ollama first (brew install ollama)." >&2; exit 1; }

models="${*:-breeze taide bailong}"
failed=""
for name in $models; do
  case "$name" in
    breeze)  src="hf.co/mradermacher/Llama-Breeze2-8B-Instruct-text-only-i1-GGUF:Q4_K_M" ;;
    taide)   src="hf.co/Vowel-Posh/Gemma-3-TAIDE-12b-Chat-2602-Q4_K_M-GGUF" ;;
    bailong) src="hf.co/NapYang/Bailong-instruct-7B.GGUF:Q4_K_M" ;;
    *) echo "Unknown model '$name' (use breeze, taide or bailong)" >&2; failed="$failed $name"; continue ;;
  esac
  echo "==> $name  <-  $src"
  if ollama pull "$src" && ollama cp "$src" "$name"; then
    echo "==> $name ready. Quick check:"
    ollama run "$name" "用一句繁體中文自我介紹。" || failed="$failed $name"
    ollama stop "$name" >/dev/null 2>&1 || true   # free memory before the next model
  else
    failed="$failed $name"
  fi
done

if [ -n "$failed" ]; then
  echo "Failed:$failed" >&2
  exit 1
fi
echo "All done. Switch by voice: 「切換模型 TAIDE」 / 「切換模型 百龍」 / 「切換模型 Breeze」"
