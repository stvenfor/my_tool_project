#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
COSYVOICE_DIR="$ROOT/vendor/CosyVoice"
MATCHA_DIR="$COSYVOICE_DIR/third_party/Matcha-TTS"
MODEL_DIR="$ROOT/pretrained_models/CosyVoice2-0.5B"

clone_or_update() {
  local url="$1"
  local dest="$2"
  if [[ -d "$dest/.git" ]]; then
    return 0
  fi
  mkdir -p "$(dirname "$dest")"
  if ! git clone --depth 1 "$url" "$dest"; then
    echo "Primary clone failed, trying gitclone mirror..."
    rm -rf "$dest"
    git clone --depth 1 "https://gitclone.com/github.com/${url#https://github.com/}" "$dest"
  fi
}

if [[ ! -d "$COSYVOICE_DIR/.git" ]]; then
  echo "Cloning CosyVoice..."
  clone_or_update "https://github.com/FunAudioLLM/CosyVoice.git" "$COSYVOICE_DIR"
fi

if [[ ! -d "$MATCHA_DIR/.git" ]]; then
  echo "Cloning Matcha-TTS submodule..."
  clone_or_update "https://github.com/shivammehta25/Matcha-TTS.git" "$MATCHA_DIR"
fi

echo "Installing CosyVoice Python dependencies..."
python3 -m pip install \
  "numpy<2" \
  "ruamel.yaml<0.18" \
  conformer==0.3.2 \
  diffusers==0.29.0 \
  gdown \
  hydra-core==1.3.2 \
  HyperPyYAML==1.2.2 \
  inflect==7.3.1 \
  librosa==0.10.2 \
  lightning==2.2.4 \
  matplotlib==3.7.5 \
  modelscope==1.20.0 \
  networkx==3.1 \
  omegaconf==2.3.0 \
  onnx==1.16.0 \
  "onnxruntime>=1.19" \
  protobuf==4.25 \
  pyarrow==18.1.0 \
  pyworld==0.3.4 \
  soundfile==0.12.1 \
  torchaudio \
  transformers==4.51.3 \
  wetext==0.0.4 \
  wget==3.2 \
  x-transformers==2.11.24 \
  tqdm \
  -q

if [[ ! -f "$MODEL_DIR/cosyvoice2.yaml" ]]; then
  echo "Downloading CosyVoice2-0.5B model (first run may take several minutes)..."
  export HF_ENDPOINT="${HF_ENDPOINT:-https://hf-mirror.com}"
  python3 - <<PY
from huggingface_hub import snapshot_download
from pathlib import Path

model_dir = Path("${MODEL_DIR}")
model_dir.parent.mkdir(parents=True, exist_ok=True)
snapshot_download("FunAudioLLM/CosyVoice2-0.5B", local_dir=str(model_dir))
print("Model ready:", model_dir)
PY
fi

echo "CosyVoice ready at $COSYVOICE_DIR"
echo "Matcha-TTS ready at $MATCHA_DIR"
echo "Model at $MODEL_DIR"
