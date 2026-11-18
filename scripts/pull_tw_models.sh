#!/bin/bash
# 把台灣的繁體中文大型語言模型下載到 Ollama，並取 Jarvis 認得的短名稱：
# breeze、taide、bailong。
#
#   bash scripts/pull_tw_models.sh                 # 三個都下載（約 17 GB）
#   bash scripts/pull_tw_models.sh breeze taide    # 只下載指定的
#
# 來源是 Hugging Face 上社群轉換的 GGUF 檔（Q4_K_M 量化）。
# 若來源倉庫搬移，修改下方對應那一行即可。
#   breeze  聯發科 Llama-Breeze2-8B-Instruct（純文字版）         約 4.9 GB
#   taide   國科會 TAIDE Gemma-3-TAIDE-12b-Chat-2602              約 8.2 GB
#   bailong 群創 Bailong-instruct-7B（以 Llama 2 為基底，2024）   約 4.2 GB
set -uo pipefail

command -v ollama >/dev/null 2>&1 || { echo "請先安裝 Ollama（Ollama.app 或 brew install ollama）。" >&2; exit 1; }

models="${*:-breeze taide bailong}"
failed=""
for name in $models; do
  case "$name" in
    breeze)  src="hf.co/mradermacher/Llama-Breeze2-8B-Instruct-text-only-i1-GGUF:Q4_K_M" ;;
    taide)   src="hf.co/Vowel-Posh/Gemma-3-TAIDE-12b-Chat-2602-Q4_K_M-GGUF" ;;
    bailong) src="hf.co/NapYang/Bailong-instruct-7B.GGUF:Q4_K_M" ;;
    *) echo "不認得的模型「$name」（可用 breeze、taide、bailong）" >&2; failed="$failed $name"; continue ;;
  esac
  echo "==> $name  <-  $src"
  if ollama pull "$src" && ollama cp "$src" "$name"; then
    echo "==> $name 已就緒，快速測試："
    ollama run "$name" "用一句繁體中文自我介紹。" || failed="$failed $name"
    ollama stop "$name" >/dev/null 2>&1 || true   # 下載下一個之前先釋放記憶體
  else
    failed="$failed $name"
  fi
done

if [ -n "$failed" ]; then
  echo "失敗：$failed" >&2
  exit 1
fi
echo "全部完成。可用語音切換：「切換模型 TAIDE」/「切換模型 百龍」/「切換模型 Breeze」"
