#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
ZIPVOICE_DIR="$ROOT/vendor/ZipVoice"

if [[ ! -d "$ZIPVOICE_DIR/.git" ]]; then
  echo "Cloning ZipVoice..."
  git clone --depth 1 https://github.com/k2-fsa/ZipVoice.git "$ZIPVOICE_DIR"
fi

echo "Installing ZipVoice Python dependencies (piper_phonemize optional for Chinese-only)..."
python3 -m pip install \
  torch torchaudio torchcodec \
  numpy lhotse huggingface_hub safetensors vocos \
  cn2an inflect jieba pypinyin pydub \
  -q

echo "ZipVoice ready at $ZIPVOICE_DIR"
