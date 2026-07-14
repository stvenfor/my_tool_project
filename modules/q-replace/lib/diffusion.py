from __future__ import annotations

from functools import lru_cache
from typing import Any

import cv2
import numpy as np
import torch
from PIL import Image


@lru_cache(maxsize=1)
def _load_ipadapter_controlnet_pipeline(model_id: str, controlnet_id: str, ip_adapter_repo: str, device: str):
    from diffusers import ControlNetModel, StableDiffusionXLControlNetPipeline

    dtype = torch.float16 if device in {"mps", "cuda"} else torch.float32
    controlnet = ControlNetModel.from_pretrained(controlnet_id, torch_dtype=dtype)
    pipe = StableDiffusionXLControlNetPipeline.from_pretrained(
        model_id,
        controlnet=controlnet,
        torch_dtype=dtype,
    )
    pipe.load_ip_adapter(
        ip_adapter_repo,
        subfolder="sdxl_models",
        weight_name="ip-adapter_sdxl.bin",
    )
    # IP-Adapter requires dedicated attention processors; slicing/xformers break them.
    return pipe.to(device)


def _load_controlnet_img2img_pipeline(model_id: str, controlnet_id: str, device: str):
    from diffusers import ControlNetModel, StableDiffusionXLControlNetImg2ImgPipeline

    dtype = torch.float16 if device in {"mps", "cuda"} else torch.float32
    controlnet = ControlNetModel.from_pretrained(controlnet_id, torch_dtype=dtype)
    pipe = StableDiffusionXLControlNetImg2ImgPipeline.from_pretrained(
        model_id,
        controlnet=controlnet,
        torch_dtype=dtype,
    )
    if device == "mps":
        pipe.enable_attention_slicing()
    return pipe.to(device)


def _pil_from_bgr(image_bgr: np.ndarray) -> Image.Image:
    if image_bgr.ndim == 3 and image_bgr.shape[2] == 4:
        rgba = cv2.cvtColor(image_bgr, cv2.COLOR_BGRA2RGBA)
        return Image.fromarray(rgba).convert("RGB")
    rgb = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2RGB)
    return Image.fromarray(rgb)


def generate_pose_character_frame(
    character_bgr: np.ndarray,
    openpose_bgr: np.ndarray,
    prompt: str,
    negative_prompt: str,
    config: dict[str, Any],
    device: str,
    *,
    seed: int,
    width: int = 768,
    height: int = 1024,
) -> np.ndarray:
    """Generate character in target pose using IP-Adapter + ControlNet OpenPose."""
    models_cfg = config["models"]
    synth_cfg = config["synthesis"]

    pipe = _load_ipadapter_controlnet_pipeline(
        models_cfg["sdxl_base"],
        models_cfg["controlnet_openpose"],
        models_cfg["ip_adapter"],
        device,
    )
    pipe.set_ip_adapter_scale(float(synth_cfg.get("ip_adapter_scale", 0.65)))

    character_pil = _pil_from_bgr(character_bgr)
    openpose_rgb = cv2.cvtColor(openpose_bgr, cv2.COLOR_BGR2RGB)
    control_pil = Image.fromarray(openpose_rgb).resize((width, height), Image.Resampling.LANCZOS)

    generator = torch.Generator(device=device).manual_seed(seed)
    result = pipe(
        prompt=prompt,
        negative_prompt=negative_prompt,
        image=control_pil,
        ip_adapter_image=character_pil,
        num_inference_steps=int(synth_cfg.get("num_inference_steps", 24)),
        guidance_scale=float(synth_cfg.get("guidance_scale", 7.0)),
        controlnet_conditioning_scale=float(synth_cfg.get("controlnet_conditioning_scale", 0.85)),
        width=width,
        height=height,
        generator=generator,
    ).images[0]
    return cv2.cvtColor(np.array(result), cv2.COLOR_RGB2BGR)


def generate_img2img_controlnet(
    init_bgr: np.ndarray,
    control_bgr: np.ndarray,
    prompt: str,
    negative_prompt: str,
    config: dict[str, Any],
    device: str,
    *,
    strength: float,
    num_inference_steps: int,
    guidance_scale: float,
    controlnet_conditioning_scale: float,
    seed: int,
) -> np.ndarray:
    models_cfg = config["models"]
    pipe = _load_controlnet_img2img_pipeline(
        models_cfg["sdxl_base"],
        models_cfg["controlnet_openpose"],
        device,
    )

    init_image = _pil_from_bgr(init_bgr)
    control_image = _pil_from_bgr(control_bgr)
    if control_image.size != init_image.size:
        control_image = control_image.resize(init_image.size)

    generator = torch.Generator(device=device).manual_seed(seed)
    result = pipe(
        prompt=prompt,
        negative_prompt=negative_prompt,
        image=init_image,
        control_image=control_image,
        strength=strength,
        num_inference_steps=num_inference_steps,
        guidance_scale=guidance_scale,
        controlnet_conditioning_scale=controlnet_conditioning_scale,
        generator=generator,
    ).images[0]
    return cv2.cvtColor(np.array(result), cv2.COLOR_RGB2BGR)
