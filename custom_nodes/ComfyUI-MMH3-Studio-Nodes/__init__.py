"""MMH3 Studio nodes: every Studio-specific change to other packs, done by inheritance.

Nothing here edits another pack's files. Each node subclasses the original and
changes behaviour only for the duration of its own call, so updating the parent
pack keeps working and removing this pack restores the originals exactly.

    MMH3S_ContinuumSampler   H3 Continuum Sampler V3.4 plus
                             - the Reference Audio inputs V3.4 hides upstream, and a
                               second voice reference for <Audio 2>
                             - release of the text encoder after each chunk's encode
    MMH3S_DirectorGuide      DaSiWa MiniMax H3 Director Guide, calling Core's H3
                             nodes by keyword so an argument reorder cannot break it

Parents are looked up in ComfyUI's node registry. Packs load alphabetically and
this folder sorts after both parents; if a parent is missing its node is skipped.
"""
import importlib
import logging
import sys

log = logging.getLogger("mmh3_studio_nodes")

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}


def _parent(name):
    try:
        import nodes
        return nodes.NODE_CLASS_MAPPINGS.get(name)
    except Exception:
        return None


# ── text encoder release ────────────────────────────────────────────────────────

def _vram_used_gb():
    try:
        import torch
        free, total = torch.cuda.mem_get_info()
        return (total - free) / 2 ** 30
    except Exception:
        return float("nan")


class _ReleasingClip:
    """Wrap a CLIP so each encode hands its VRAM back to the diffusion model.

    On a 16 GB card the H3 text encoder (~15 GB) and the diffusion model (~20 GB)
    fight for the same memory every chunk. The encoder is idle until the next
    chunk, so after encoding it is unloaded and the freed amount is logged.
    """

    def __init__(self, clip):
        self._clip = clip

    def __getattr__(self, name):
        return getattr(self._clip, name)

    def encode_from_tokens_scheduled(self, *args, **kwargs):
        result = self._clip.encode_from_tokens_scheduled(*args, **kwargs)
        before = _vram_used_gb()
        try:
            import comfy.model_management as mm
            patcher = getattr(self._clip, "patcher", None)
            if patcher is not None and hasattr(mm, "unload_model_clones"):
                mm.unload_model_clones(patcher)
            if hasattr(mm, "soft_empty_cache"):
                mm.soft_empty_cache()
        except Exception as exc:
            log.info("mmh3 studio: text encoder release skipped: %s", exc)
            return result
        after = _vram_used_gb()
        log.info("mmh3 studio: text encoder released: %.2f GB -> %.2f GB used (%.2f GB freed)",
                 before, after, before - after)
        return result


# ── second voice reference ───────────────────────────────────────────────────

class _SecondAudioClip:
    """Tokenize with one more audio slot right after the first, so <Audio 2> has a place."""

    def __init__(self, clip):
        self._clip = clip

    def __getattr__(self, name):
        return getattr(self._clip, name)

    def tokenize(self, text, **kwargs):
        items = list(kwargs.get("minimax_ref_items") or [])
        audio = [i for i, item in enumerate(items) if isinstance(item, dict) and item.get("type") == "audio"]
        if audio:
            items.insert(audio[-1] + 1, {"type": "audio"})
            kwargs["minimax_ref_items"] = items
        return self._clip.tokenize(text, **kwargs)


def _install_second_audio(parent_module, audio, vae):
    """Make Continuum's two conditioning builders carry a second reference audio.

    Continuum adds its one voice as a tokenize item plus an audio block in minimax_refs,
    and Core reads any number of those. Each builder is wrapped for this run only to add
    the second pair right after the first. Returns (owner, name, original) to restore.
    """
    root = parent_module.rsplit(".v3.", 1)[0]
    names = {"reference": root + ".reference", "reference_audio": root + ".reference_audio",
             "h3_builder": root + ".v2.h3_builder", "sequence": root + ".v2.sequence",
             "physical_runtime": root + ".v2.physical_runtime"}
    # Continuum imports some of these lazily inside its run, so load them here.
    modules, missing = {}, []
    for key, name in names.items():
        try:
            modules[key] = importlib.import_module(name)
        except ImportError:
            missing.append(name)
    if missing:
        raise RuntimeError("MMH3 Studio: this Continuum version cannot take a second reference audio "
                           "(missing %s). Disconnect Reference Audio 2." % ", ".join(missing))
    ra = modules["reference_audio"]
    block = ra.reference_audio_block(ra.encode_reference_audio(vae, ra.prepare_reference_audio_source(audio, vae)))

    def wrap(build):
        def with_second(clip, *args, **kwargs):
            if kwargs.get("reference_audio_assets") is None:
                return build(clip, *args, **kwargs)
            conditioning = build(_SecondAudioClip(clip), *args, **kwargs)
            for pair in conditioning:
                refs = list(pair[1].get("minimax_refs") or [])
                first = next((i for i, ref in enumerate(refs) if ref.get("kind") == "audio"), None)
                if first is not None:
                    refs.insert(first + 1, dict(block))
                    pair[1] = {**pair[1], "minimax_refs": refs}
            return conditioning
        return with_second

    restore = []
    for key, name in (("reference", "encode_reference_prompt"), ("h3_builder", "encode_prompt_conditioning"),
                      ("sequence", "encode_prompt_conditioning"), ("physical_runtime", "encode_prompt_conditioning")):
        owner = modules[key]
        original = getattr(owner, name)
        restore.append((owner, name, original))
        setattr(owner, name, wrap(original))
    log.info("mmh3 studio: second reference audio attached as <Audio 2>")
    return restore


# ── Continuum sampler ─────────────────────────────────────────────────────────

def _make_continuum_sampler(Parent):
    grand = next((c for c in Parent.__mro__[1:] if "run" in c.__dict__), None)

    class MMH3S_ContinuumSampler(Parent):
        DESCRIPTION = ("H3 Continuum Sampler V3.4 for MMH3 Studio: adds a voice Reference Audio "
                       "and releases the text encoder after each chunk's encode.")

        @classmethod
        def INPUT_TYPES(cls):
            schema = Parent.INPUT_TYPES()
            optional = dict(schema.get("optional", {}))
            # V3.4 hides these; the V3.2 runtime underneath still implements them.
            optional["reference_audio_1"] = ("AUDIO", {"tooltip": "Voice reference: lends its timbre, "
                                                                  "unlike Driving Audio which replaces the soundtrack."})
            optional["reference_audio_2"] = ("AUDIO", {"tooltip": "Second voice reference, for <Audio 2>."})
            optional["reference_audio_vae"] = ("VAE",)
            optional["release_text_encoder"] = ("BOOLEAN", {"default": True, "tooltip":
                                                "Unload the text encoder after each chunk's encode so the "
                                                "diffusion model gets the VRAM back."})
            return {**schema, "optional": optional}

        def run(self, reference_audio_1=None, reference_audio_2=None, reference_audio_vae=None,
                release_text_encoder=True, **kwargs):
            if release_text_encoder and kwargs.get("clip") is not None:
                kwargs["clip"] = _ReleasingClip(kwargs["clip"])
            if kwargs.get("driving_audio") is not None:
                return super().run(**kwargs)
            voice, second = reference_audio_1, reference_audio_2
            if voice is None:
                voice, second = second, None
            if voice is None or grand is None:
                return super().run(**kwargs)
            voice_vae = reference_audio_vae or kwargs.get("audio_vae")
            original = grand.__dict__["run"]

            def with_voice(self_, *args, **inner):
                # V3.4 passes None here unconditionally; supply the voice instead.
                inner["reference_audio_1"] = voice
                inner["reference_audio_vae"] = voice_vae
                return original(self_, *args, **inner)

            restore = []
            if second is not None:
                if kwargs.get("run_storage", "Off") != "Off":
                    # Stored chunks are keyed without the second voice and would be reused as if
                    # it were absent.
                    log.info("mmh3 studio: second reference audio connected, Run Storage turned off")
                    kwargs["run_storage"] = "Off"
                restore = _install_second_audio(Parent.__module__, second, voice_vae)
            grand.run = with_voice
            try:
                return super().run(**kwargs)
            finally:
                grand.run = original
                for owner, name, value in restore:
                    setattr(owner, name, value)

    return MMH3S_ContinuumSampler


# ── DaSiWa Director Guide ─────────────────────────────────────────────────────

class _KeywordRef2VA:
    """Core's MiniMaxH3ReferenceToVideo, called by keyword instead of position."""

    def __init__(self, native):
        self._native = native

    def __getattr__(self, name):
        return getattr(self._native, name)

    def execute(self, clip, vae, audio_vae, prompt, width, height, length,
                ref_image_size, ref_images, ref_videos, ref_video_audios, ref_audios):
        return self._native.execute(clip=clip, vae=vae, audio_vae=audio_vae, prompt=prompt,
                                    width=width, height=height, length=length,
                                    ref_image_size=ref_image_size, ref_images=ref_images,
                                    ref_videos=ref_videos, ref_video_audios=ref_video_audios,
                                    ref_audios=ref_audios)


def _make_director_guide(Parent):
    module = sys.modules.get(Parent.__module__)

    class MMH3S_DirectorGuide(Parent):
        DESCRIPTION = ("DaSiWa MiniMax H3 Director Guide for MMH3 Studio: safe against Core argument "
                       "reorders, and releases the text encoder once the prompt is encoded.")

        @classmethod
        def INPUT_TYPES(cls):
            schema = Parent.INPUT_TYPES()
            optional = dict(schema.get("optional", {}))
            optional["release_text_encoder"] = ("BOOLEAN", {"default": True, "tooltip":
                                                "Unload the text encoder once the prompt is encoded so the "
                                                "diffusion model gets the VRAM back."})
            return {**schema, "optional": optional}

        def apply(self, *args, release_text_encoder=True, **kwargs):
            if release_text_encoder and kwargs.get("clip") is not None:
                kwargs["clip"] = _ReleasingClip(kwargs["clip"])
            lookup = getattr(module, "_native_node", None)
            if lookup is None:
                return super().apply(*args, **kwargs)

            def keyword_native(name):
                native = lookup(name)
                return _KeywordRef2VA(native) if name == "MiniMaxH3ReferenceToVideo" else native

            module._native_node = keyword_native
            try:
                return super().apply(*args, **kwargs)
            finally:
                module._native_node = lookup

    return MMH3S_DirectorGuide


# ── registration ──────────────────────────────────────────────────────────────

for key, parent_name, factory, title in [
    ("MMH3S_ContinuumSampler", "H3ContinuumSamplerV34", _make_continuum_sampler,
     "MMH3 Studio · Continuum Sampler"),
    ("MMH3S_DirectorGuide", "MiniMaxH3DirectorGuide", _make_director_guide,
     "MMH3 Studio · Director Guide"),
]:
    parent = _parent(parent_name)
    if parent is None:
        log.warning("mmh3 studio: %s not found; %s is unavailable", parent_name, key)
        continue
    NODE_CLASS_MAPPINGS[key] = factory(parent)
    NODE_DISPLAY_NAME_MAPPINGS[key] = title

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
