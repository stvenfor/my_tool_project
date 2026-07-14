#!/usr/bin/env python3
"""Generate realistic character reference image for q-replace."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

import torch
from PIL import Image

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")

PROMPT = (
    "photorealistic young East Asian woman, slim dancer body, long dark wavy hair, "
    "delicate face, large eyes, fair smooth skin, soft beauty lighting, "
    "white strapless tube top, purple ruffled mini shorts with pink bow at waist, "
    "full body, standing straight, arms at sides, clean white background, "
    "douyin aesthetic, high detail, professional photo"
)
NEGATIVE = (
    "deformed, extra limbs, bad hands, extra fingers, blurry, low quality, watermark, "
    "text, cartoon, chibi, 3d render, oversaturated, ugly face, nsfw, nude"
)


def resolve_device() -> str:
    if torch.backends.mps.is_available():
        return "mps"
    if torch.cuda.is_available():
        return "cuda"
    return "cpu"


def generate(output: Path, seed: int, width: int, height: int) -> Path:
    from diffusers import StableDiffusionXLPipeline

    device = resolve_device()
    dtype = torch.float16 if device in {"mps", "cuda"} else torch.float32
    print(f"Loading SDXL on {device}...")
    pipe = StableDiffusionXLPipeline.from_pretrained(
        "stabilityai/stable-diffusion-xl-base-1.0",
        torch_dtype=dtype,
        use_safetensors=True,
    )
    if device == "mps":
        pipe.enable_attention_slicing()
    pipe = pipe.to(device)

    generator = torch.Generator(device=device).manual_seed(seed)
    print(f"Generating character ref (seed={seed})...")
    result = pipe(
        prompt=PROMPT,
        negative_prompt=NEGATIVE,
        width=width,
        height=height,
        num_inference_steps=30,
        guidance_scale=7.0,
        generator=generator,
    ).images[0]

    output.parent.mkdir(parents=True, exist_ok=True)
    result.save(output)
    print(f"Saved: {output}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate realistic dancer character reference.")
    parser.add_argument(
        "--output",
        default=str(ROOT / "assets" / "realistic-dancer" / "ref_front.png"),
        help="Output PNG path",
    )
    parser.add_argument("--seed", type=int, default=20260712)
    parser.add_argument("--width", type=int, default=768)
    parser.add_argument("--height", type=int, default=1152)
    args = parser.parse_args()
    generate(Path(args.output), args.seed, args.width, args.height)


if __name__ == "__main__":
    main()
