from modelscope import DiffusionPipeline
import torch

# Lazy-loaded pipeline to avoid repeated initialization
_PIPE = None
_DEVICE = None


def _get_pipe(model_name: str) -> DiffusionPipeline:
    global _PIPE, _DEVICE
    if _PIPE is not None:
        return _PIPE

    if torch.cuda.is_available():
        torch_dtype = torch.bfloat16
        _DEVICE = "cuda"
    else:
        torch_dtype = torch.float32
        _DEVICE = "cpu"

    _PIPE = DiffusionPipeline.from_pretrained(model_name, torch_dtype=torch_dtype).to(_DEVICE)
    return _PIPE


def generate_image(
    model_name: str,
    prompt: str,
    negative_prompt: str,
    width: int,
    height: int,
    num_inference_steps: int,
    guidance_scale: float,
    seed: int | None,
):
    """Generate a single image and return a PIL.Image."""

    pipe = _get_pipe(model_name)
    device = _DEVICE or ("cuda" if torch.cuda.is_available() else "cpu")
    generator = torch.Generator(device=device).manual_seed(seed) if seed is not None else None

    image = pipe(
        prompt=prompt,
        negative_prompt=negative_prompt,
        width=width,
        height=height,
        num_inference_steps=num_inference_steps,
        true_cfg_scale=guidance_scale,
        generator=generator,
    ).images[0]

    return image
