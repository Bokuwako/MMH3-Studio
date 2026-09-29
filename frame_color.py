"""Colour-correct a still frame toward an anchor frame with MAINodes' ColorCarry transform.

The same brightness offset and saturation multiplier, with the same clamps, that the
ColorCarry node applies between chunks, so a frame carried into the next clip by hand
gets the correction a chained render would have given it.
"""
import importlib.util
from pathlib import Path

import numpy as np
import torch
from PIL import Image

import pack_bridge as pack

_carry = None


def carry():
    global _carry
    if _carry is None:
        path = pack.COMFY / 'custom_nodes/ComfyUI-MAINodes/h3_color_carry.py'
        if not path.is_file():
            raise ValueError('색 보정에 필요한 MAINodes(h3_color_carry.py)가 없습니다: ' + str(path))
        spec = importlib.util.spec_from_file_location('mmh3_studio_color_carry', path)
        _carry = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_carry)
    return _carry


def load(path):
    rgb = np.asarray(Image.open(path).convert('RGB'), dtype=np.float32) / 255.0
    return torch.from_numpy(rgb)[None]


def stats(path):
    return carry().tensor_scene_color_stats(load(path))


def correct(source, target, anchor, settings):
    """Write the corrected frame to `target` as PNG; return (brightness, saturation)."""
    def number(key, default):
        value = settings.get(key)
        return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else default

    frame = load(source)
    brightness, saturation = carry().scene_color_transform(
        anchor, carry().tensor_scene_color_stats(frame),
        strength=number('strength', 1.0),
        # Studio keeps the luma limit as a fraction of full range; the node counts 8-bit code values.
        max_luma=number('max_luma_shift', 0.04) * 255.0,
        max_sat=number('max_saturation_change', 0.08))
    out = carry().apply_rgb_color_transform(frame, brightness, saturation)[0]
    Image.fromarray((out.clamp(0, 1).numpy() * 255.0 + 0.5).astype(np.uint8)).save(Path(target), 'PNG')
    return brightness, saturation
