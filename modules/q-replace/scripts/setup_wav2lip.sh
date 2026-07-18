#!/usr/bin/env bash
# Install local Wav2Lip inference env at ~/Wav2Lip for q-replace.
set -euo pipefail

WAV2LIP_HOME="${WAV2LIP_HOME:-$HOME/Wav2Lip}"
REPO_URL="${WAV2LIP_REPO_URL:-https://github.com/Rudrabha/Wav2Lip.git}"
S3FD_URL="${S3FD_URL:-https://www.adrianbulat.com/downloads/python-fan/s3fd-619a316812.pth}"
GAN_GDRIVE_ID="${GAN_GDRIVE_ID:-15G3U08c8xsCkOqQxE38Z2XXDnPcOptNk}"
GAN_HF_URL="${GAN_HF_URL:-https://huggingface.co/Nekochu/Wav2Lip/resolve/main/wav2lip_gan.pth}"

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required command: $1" >&2
    exit 1
  }
}

need_cmd git
need_cmd python3
need_cmd ffmpeg
need_cmd curl

echo "==> Wav2Lip home: $WAV2LIP_HOME"

if [[ ! -d "$WAV2LIP_HOME/.git" ]]; then
  echo "==> Cloning Wav2Lip..."
  git clone --depth 1 "$REPO_URL" "$WAV2LIP_HOME"
else
  echo "==> Repo already present"
fi

cd "$WAV2LIP_HOME"
mkdir -p checkpoints face_detection/detection/sfd temp results

if [[ ! -x .venv/bin/python ]]; then
  echo "==> Creating .venv..."
  python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate
python -m pip install -U pip wheel setuptools
echo "==> Installing inference deps (modern pins for Apple Silicon / Py3.12)..."
python -m pip install torch torchaudio opencv-python-headless numpy librosa scipy tqdm pillow soundfile gdown

# Patch LandmarksType for Python 3.11+ (leading underscore = private)
python - <<'PY'
from pathlib import Path
p = Path("face_detection/api.py")
text = p.read_text(encoding="utf-8")
if "TWO_D" not in text:
    text = text.replace(
        "    _2D = 1\n    _2halfD = 2\n    _3D = 3\n",
        "    _2D = 1\n    _2halfD = 2\n    _3D = 3\n\n"
        "    # Public aliases for Python 3.11+\n"
        "    TWO_D = 1\n    TWO_HALF_D = 2\n    THREE_D = 3\n",
    )
    p.write_text(text, encoding="utf-8")
    print("patched face_detection/api.py")
PY

python - <<'PY'
from pathlib import Path
p = Path("inference.py")
text = p.read_text(encoding="utf-8")
orig = text
text = text.replace(
    "face_detection.FaceAlignment(face_detection.LandmarksType._2D,",
    'face_detection.FaceAlignment(getattr(face_detection.LandmarksType, "TWO_D", face_detection.LandmarksType._2D),',
)
if "weights_only" not in text:
    text = text.replace(
        "\t\tcheckpoint = torch.load(checkpoint_path)\n",
        "\t\tcheckpoint = torch.load(checkpoint_path, weights_only=False)\n",
    )
    text = text.replace(
        "\t\tcheckpoint = torch.load(checkpoint_path,\n\t\t\t\t\t\t\t\tmap_location=lambda storage, loc: storage)\n",
        "\t\tcheckpoint = torch.load(checkpoint_path,\n"
        "\t\t\t\t\t\t\t\tmap_location=lambda storage, loc: storage,\n"
        "\t\t\t\t\t\t\t\tweights_only=False)\n",
    )
if text != orig:
    p.write_text(text, encoding="utf-8")
    print("patched inference.py")
PY

# Modern librosa: mel() is keyword-only
python - <<'PY'
from pathlib import Path
p = Path("audio.py")
text = p.read_text(encoding="utf-8")
old = (
    "return librosa.filters.mel(hp.sample_rate, hp.n_fft, n_mels=hp.num_mels,\n"
    "                               fmin=hp.fmin, fmax=hp.fmax)"
)
new = (
    "return librosa.filters.mel(sr=hp.sample_rate, n_fft=hp.n_fft, n_mels=hp.num_mels,\n"
    "                               fmin=hp.fmin, fmax=hp.fmax)"
)
if old in text:
    p.write_text(text.replace(old, new), encoding="utf-8")
    print("patched audio.py for modern librosa")
PY

download_if_needed() {
  local dest="$1"
  local min_bytes="$2"
  shift 2
  if [[ -f "$dest" ]]; then
    local size
    size=$(wc -c <"$dest" | tr -d ' ')
    if (( size >= min_bytes )); then
      echo "==> OK: $dest ($size bytes)"
      return 0
    fi
    echo "==> Incomplete $dest ($size bytes), re-downloading..."
    rm -f "$dest"
  fi
  local url
  for url in "$@"; do
    echo "==> Trying $url"
    if [[ "$url" == gdrive:* ]]; then
      local file_id="${url#gdrive:}"
      if gdown --id "$file_id" -O "$dest"; then
        break
      fi
    else
      if curl -L --fail --retry 5 --retry-all-errors -o "$dest" "$url"; then
        break
      fi
    fi
    rm -f "$dest"
  done
  local size
  size=$(wc -c <"$dest" | tr -d ' ')
  if (( size < min_bytes )); then
    echo "Failed to download $dest (got $size bytes, need >= $min_bytes)" >&2
    exit 1
  fi
  echo "==> Downloaded $dest ($size bytes)"
}

download_if_needed \
  "face_detection/detection/sfd/s3fd.pth" \
  80000000 \
  "$S3FD_URL"

download_if_needed \
  "checkpoints/wav2lip_gan.pth" \
  300000000 \
  "gdrive:$GAN_GDRIVE_ID" \
  "$GAN_HF_URL" \
  "https://hf-mirror.com/Nekochu/Wav2Lip/resolve/main/wav2lip_gan.pth"

echo
echo "==> Verification"
"$WAV2LIP_HOME/.venv/bin/python" - <<PY
import torch
from pathlib import Path
home = Path("$WAV2LIP_HOME")
gan = home / "checkpoints" / "wav2lip_gan.pth"
s3fd = home / "face_detection" / "detection" / "sfd" / "s3fd.pth"
assert gan.exists() and gan.stat().st_size > 300_000_000, gan
assert s3fd.exists() and s3fd.stat().st_size > 80_000_000, s3fd
print("torch:", torch.__version__)
print("mps:", torch.backends.mps.is_available())
print("checkpoint:", gan)
print("s3fd:", s3fd)
print("READY")
PY

echo
echo "Setup complete. Smoke test example:"
echo "  $WAV2LIP_HOME/.venv/bin/python $WAV2LIP_HOME/inference.py \\"
echo "    --checkpoint_path $WAV2LIP_HOME/checkpoints/wav2lip_gan.pth \\"
echo "    --face <face.png|video.mp4> --audio <audio.wav> \\"
echo "    --outfile /tmp/wav2lip_smoke.mp4"
