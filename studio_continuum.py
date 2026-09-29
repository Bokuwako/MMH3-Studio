"""Continuum engine: the node authors' own path, wired from Studio.

Generation, chaining and the high-resolution pass all run inside one ComfyUI
execution, exactly as H3 Continuum and the Latent Upscaler + Refine packs are
meant to be used:

    H3 Continuum Sampler V3.4  ── video_latents ─┐
                               ── audio_latents ─┼─> Upscaler + Refine (3D)
                               ── refine_state  ─┘        (optional)
                               ── assembly_plan ──> Assemble + Seam ──> save

The carried prefix is protected by Core's per-token denoise mask and is never
also fed back as an ordinary reference, which is what made the Project Suite
hybrid flicker. `refine_state` hands the second pass the exact conditioning,
model state and mask of the chunk it refines.
"""
import json
from pathlib import Path

import pack_bridge as pack
import studio_engine as engine

HERE = Path(__file__).parent

# Same models the captured pipeline uses, so an empty field means "as before".
TEMPLATE_MODELS = {'model': ('1512:2588', 'unet_name'), 'clip': ('1512:2587', 'clip_name'),
                   'video_vae': ('1512:2584', 'vae_name'), 'audio_vae': ('1512:2585', 'vae_name')}


def template_models():
    try: graph = engine.template()
    except Exception: return {}
    out = {}
    for key, (nid, field) in TEMPLATE_MODELS.items():
        value = (graph.get(nid) or {}).get('inputs', {}).get(field)
        if isinstance(value, str) and value: out[key] = value
    return out

CONTINUITY = {5: 'Fast — 5 frames', 22: 'Balanced — 22 frames', 39: 'Strong — 39 frames',
              0: 'Auto — conservative'}
PROMPT_MODES = ('Auto', 'Fixed', 'List', 'Timeline')
REFINE_SIGMAS = '0.9035, 0.8000, 0.6316, 0.3158, 0.0000'


def defaults(info, cls):
    out = {}
    for key, spec in info[cls]['input'].get('required', {}).items():
        cfg = spec[1] if len(spec) > 1 else {}
        if 'default' in cfg: out[key] = cfg['default']
        elif isinstance(spec[0], list) and spec[0]: out[key] = spec[0][0]
    return out


def comfy_path(name):
    """Absolute path into ComfyUI's input folder: LoadImage's combo lists only its root."""
    path = Path(str(name))
    return str(path if path.is_absolute() else (pack.COMFY / 'input' / path).resolve())


def build(b, info):
    """Return an API graph plus meta, from the same render body the UI sends."""
    g = {}

    def create(nid, cls, **kw):
        if cls not in info: raise ValueError('설치되지 않은 노드: ' + cls + ' (Continuum 또는 Upscaler-Plus 설치를 확인하세요)')
        g[nid] = {'class_type': cls, 'inputs': {**defaults(info, cls), **kw}}
        return [nid, 0]

    prompt = str(b.get('prompt', '')).strip()
    if not prompt: raise ValueError('프롬프트를 먼저 작성하세요.')
    width, height = int(b.get('width', 768)), int(b.get('height', 512))
    if min(width, height) < 32 or width % 32 or height % 32: raise ValueError('가로·세로는 32의 배수여야 합니다.')
    chunks = int(b.get('chunks', 1))
    if chunks < 1: raise ValueError('클립 개수는 1 이상이어야 합니다.')
    chunk_seconds = engine.num(b.get('chunk_seconds'), engine.num(b.get('duration'), 5))
    if not 4 <= chunk_seconds <= 15: raise ValueError('Continuum은 클립 하나를 4~15초로 만듭니다. 5초가 제작자 권장값입니다.')
    if chunks > 16: raise ValueError('Continuum의 클립 개수는 16개까지입니다.')
    mode = str(b.get('prompt_mode', 'Auto'))
    if mode not in PROMPT_MODES: raise ValueError('프롬프트 모드가 올바르지 않습니다.')
    parts = [p for p in prompt.split('\n---\n')]
    if mode == 'List' and len(parts) != chunks:
        raise ValueError('List 모드는 클립 개수만큼 프롬프트가 필요합니다. 현재 {}개 / 클립 {}개. 프롬프트 사이를 --- 한 줄로 나누세요.'.format(len(parts), chunks))

    fallback = template_models()
    unet = b.get('model') or fallback.get('model')
    clip_name = b.get('clip') or fallback.get('clip')
    video_vae = b.get('video_vae') or fallback.get('video_vae')
    audio_vae = b.get('audio_vae') or fallback.get('audio_vae')
    for label, value in (('모델', unet), ('텍스트 인코더', clip_name), ('영상 VAE', video_vae), ('오디오 VAE', audio_vae)):
        if not value: raise ValueError(label + '을(를) 선택하세요. 현재 워크플로우 템플릿에서도 값을 찾지 못했습니다.')

    model = create('cont_unet', 'UNETLoader', unet_name=unet, weight_dtype='default')
    # One model serves both passes here: the refine node takes its model from the
    # chunk's refine_state, so a separate upscale-pass LoRA cannot apply.
    turbo = (b.get('turbo') or {}).get('ref_base' if str(b.get('mode')) == 'REF2VA' else 'other_base') or {}
    if turbo.get('enabled'):
        if not turbo.get('lora'): raise ValueError('켜진 터보 프로필의 LoRA를 선택하세요.')
        model = create('cont_turbo', 'LoraLoaderModelOnly', model=model, lora_name=turbo['lora'],
                       strength_model=engine.num(turbo.get('strength'), 1))
    for index, lora in enumerate(b.get('loras') or []):
        if not lora.get('on'): continue
        if not lora.get('lora'): raise ValueError('켜진 추가 LoRA를 선택하세요.')
        model = create('cont_lora_%d' % index, 'LoraLoaderModelOnly', model=model, lora_name=lora['lora'],
                       strength_model=engine.num(lora.get('str'), 1))
    # Same model patches the captured workflow applies, so switching engines does
    # not silently change the sampling curve or the attention path.
    if b.get('kitchen', True) and 'PathchComfyKitchenAttentionDaSiWa' in info:
        model = create('cont_kitchen', 'PathchComfyKitchenAttentionDaSiWa', model=model)
    if b.get('sigma_shift', True) and 'MiniMaxH3SigmaShift' in info:
        model = create('cont_shift', 'MiniMaxH3SigmaShift', model=model,
                       shift_video=engine.num(b.get('shift_video'), 12.0),
                       shift_audio=engine.num(b.get('shift_audio'), 3.0))
    # Live preview: ComfyUI ships with previews off, so the model carries its own
    # previewer (taeh3 gives true colour instead of a latent colour guess).
    if b.get('preview', True) and 'ModelPreviewOverrideKJ' in info:
        chunk_frames = engine.aligned(int(round(chunk_seconds * 24)))
        model = create('cont_preview', 'ModelPreviewOverrideKJ', model=model, max_resolution=512,
                       jpeg_quality=80, suppress_default_preview=True,
                       tiny_vae='taeh3.safetensors', **engine.preview(chunk_frames, b))
    clip = create('cont_clip', 'CLIPLoader', clip_name=clip_name, type='minimax')
    vvae = create('cont_video_vae', 'VAELoader', vae_name=video_vae)
    avae = create('cont_audio_vae', 'VAELoader', vae_name=audio_vae)
    sampler = create('cont_sampler_select', 'KSamplerSelect', sampler_name=b.get('sampler_name', 'euler'))
    sigmas = create('cont_sigmas', 'BasicScheduler', model=model, scheduler=b.get('scheduler', 'beta'),
                    steps=int(b.get('steps', 12)), denoise=1.0)

    refs = [r for r in (b.get('refs') or []) if r.get('enabled', True)]
    images = [r for r in refs if r.get('type', 'image') == 'image']
    videos = [r for r in refs if r.get('type') == 'video']
    audios = [r for r in refs if r.get('type') == 'audio']
    if len(images) > 8: raise ValueError('Continuum 엔진의 이미지 레퍼런스는 8개까지입니다.')
    if len(videos) > 1: raise ValueError('Continuum 엔진의 영상 레퍼런스는 1개까지입니다.')
    # Driving Audio replaces the soundtrack; the voice-reference input only lends its
    # timbre. V3.4 hides the latter upstream; the Studio sampler re-exposes it.
    driving = bool(b.get('driving_audio', False))
    # The Studio node pack adds voice reference and text-encoder release by
    # subclassing the V3.4 sampler; fall back to the plain sampler without it.
    sampler_cls = 'MMH3S_ContinuumSampler' if 'MMH3S_ContinuumSampler' in info else 'H3ContinuumSamplerV34'
    voice_ref = 'reference_audio_1' in {**(info[sampler_cls]['input'].get('required') or {}),
                                        **(info[sampler_cls]['input'].get('optional') or {})}
    if len(audios) > (1 if driving else 2):
        raise ValueError('Continuum 엔진의 오디오는 Driving Audio 1개, 또는 목소리 참조 2개까지입니다.')
    if len(audios) > 1 and 'reference_audio_2' not in (info[sampler_cls]['input'].get('optional') or {}):
        raise ValueError('두 번째 목소리 참조는 MMH3 Studio 노드팩이 필요합니다. ComfyUI를 재시작해 노드를 다시 불러오세요.')
    if audios and not driving and not voice_ref:
        raise ValueError('이 Continuum 버전에는 목소리 참조 입력이 없습니다. "이 오디오를 최종 소리로 사용"을 켜거나 Normal 엔진을 쓰세요.')

    inputs = {}
    slot = 0
    for index, r in enumerate(images):
        if not r.get('file'): raise ValueError('업로드되지 않은 레퍼런스가 있습니다.')
        node = create('cont_image_%d' % index, 'VHS_LoadImagePath', image=comfy_path(r['file']),
                      custom_width=0, custom_height=0)
        role = r.get('role') or ''
        if role == 'first_frame' and 'first_frame' not in inputs: inputs['first_frame'] = node
        elif role == 'last_frame' and 'last_frame' not in inputs: inputs['last_frame'] = node
        else:
            slot += 1
            inputs['reference_image_%d' % slot] = node
    def trim(r):
        start = engine.num(r.get('trim_start'))
        end = engine.num(r.get('trim_end'))
        return start, (end - start if end > start else 0.0)
    for r in videos:
        # The loader counts skipped and capped frames at force_rate, so a trim needs a fixed rate.
        start, length = trim(r)
        rate = 24 if start or length else 0
        clip_frames = create('cont_video', 'VHS_LoadVideoPath', video=comfy_path(r['file']), force_rate=rate,
                             custom_width=0, custom_height=0, frame_load_cap=int(round(length * 24)),
                             skip_first_frames=int(round(start * 24)), select_every_nth=1)
        inputs['reference_video_1'] = clip_frames
    for index, r in enumerate(audios, 1):
        start, length = trim(r)
        node = create('cont_audio' if index == 1 else 'cont_audio_%d' % index, 'VHS_LoadAudio',
                      audio_file=comfy_path(r['file']), seek_seconds=start, duration=length)
        if driving:
            inputs['driving_audio'] = node
        else:
            # <Audio 1> and <Audio 2> follow the order of the audio references.
            inputs['reference_audio_%d' % index] = node
            inputs['reference_audio_vae'] = avae

    carry = int(b.get('context_length', 39))
    audio_carry = bool(b.get('audio_continuity', True))
    # Audio latents run at 40 Hz: only a carry length divisible by 3 lands on an
    # exact audio step at 24 fps (39 frames = 65 steps). The pack refuses to round.
    if audio_carry and carry % 3:
        raise ValueError('이어받을 프레임 {}개는 오디오 격자(40Hz)에 딱 떨어지지 않습니다. 39로 바꾸거나, 오디오 이어받기를 끄세요.'.format(carry))
    continuity = CONTINUITY.get(carry, CONTINUITY[39])
    store = 'Save + Auto Resume' if b.get('run_storage', True) else 'Off'
    refine = bool(b.get('finish', 'now') == 'now')
    if refine and store != 'Off':
        # The pack fails closed rather than pairing reused chunks with new state.
        store = 'Off'
    node = create('cont_run', sampler_cls, model=model, clip=clip, video_vae=vvae, audio_vae=avae,
                  sampler=sampler, sigmas=sigmas, sequence_prompt=prompt, prompt_mode=mode, chunks=chunks,
                  chunk_seconds=chunk_seconds, width=width, height=height, continuity=continuity,
                  base_seed=int(b.get('seed', 0)), audio_continuity=audio_carry, diagnostics='Basic',
                  reroll_from_chunk='Auto', reroll_nonce=int(b.get('reroll', 0)), strict_compatibility=True,
                  debug=False, show_preview=True, run_storage=store, run_name=str(b.get('project') or ''),
                  reference_size='Match Output', project_id=str(b.get('project') or ''),
                  video_reference_size='Balanced - 0.6 MP',
                  continuation_method='Native Masked — exact continuation (Recommended)',
                  emit_refine_conditioning=refine, **inputs)

    video_latents, audio_latents = ['cont_run', 0], ['cont_run', 1]
    if refine:
        latent = create('cont_refine', 'MinimaxH3LatentUpscaler3DRefineHandoff',
                        latent=video_latents, audio_latent=audio_latents, refine_state=['cont_run', 5],
                        noise=create('cont_refine_noise', 'RandomNoise', noise_seed=int(b.get('seed', 0))),
                        sampler=sampler,
                        sigmas=create('cont_refine_sigmas', 'ManualSigmas', sigmas=str(b.get('refine_sigmas') or REFINE_SIGMAS)),
                        model_name=str(b.get('upscale_model') or 'minimax_h3_latent_upscaler_3d_fp16.safetensors'),
                        mode='megapixels', megapixels=engine.num(b.get('upscale_mp'), 1), align=32,
                        keep_proportion=False, lock_audio=True, cfg=1.0, device='cuda', precision='fp16',
                        # The learned upscaler is finished once the refine pass starts:
                        # give its VRAM back, the same reason the text encoder is released.
                        offload_after_upscale=bool(b.get('offload_upscaler', True)))
        decoded = create('cont_decode', 'VAEDecode', samples=latent, vae=vvae)
        audio = create('cont_decode_audio', 'VAEDecodeAudio', samples=latent, vae=avae)
    else:
        decoded = create('cont_decode', 'VAEDecode', samples=video_latents, vae=vvae)
        audio = create('cont_decode_audio', 'VAEDecodeAudio', samples=audio_latents, vae=avae)

    seam = create('cont_assemble', 'H3ContinuumAssembleSeamV34', images=decoded, audio=audio,
                  assembly_plan=['cont_run', 2], driving_audio=['cont_run', 4], exact_total_duration=True,
                  audio_seam='Auto', video_seam='Auto', diagnostics='Basic', image_output_device='Auto',
                  timeline_mode='Exact requested duration (Recommended)')
    frames, sound = seam, ['cont_assemble', 1]

    post = b.get('post') or {}
    for key, cls, name in [('resize', 'DaSiWa_TorchResize', 'image'), ('rtx', 'DaSiWa_RTX_UpscalerRefiner', 'images'),
                           ('watermark', 'DaSiWa_Watermark', 'images')]:
        options = post.get(key) or {}
        if options.get('enabled'):
            frames = create('cont_post_' + key, cls, **{**(options.get('values') or {}), name: frames})
    if (post.get('model_upscale') or {}).get('enabled'):
        options = post['model_upscale']
        frames = create('cont_post_model_upscale', 'ImageUpscaleWithModel', image=frames,
                        upscale_model=create('cont_post_upscale_model', 'UpscaleModelLoader', **(options.get('values') or {})))
    fps = 24
    if (post.get('interpolate') or {}).get('enabled'):
        options = post['interpolate']
        multiplier = int(options.get('multiplier', 2))
        frames = create('cont_post_interpolate', 'FrameInterpolate', images=frames, multiplier=multiplier,
                        interp_model=create('cont_post_interp_model', 'FrameInterpolationModelLoader',
                                            model_name=options.get('model', 'rife_v4.26.safetensors')))
        fps *= multiplier

    create('cont_save', 'DaSiWa_EnhancedVideoCombine', images=frames, audio=sound, codec='H.264',
           audio_codec='AAC', frame_rate=float(fps), save_output=True,
           filename_prefix='studio_continuum/%date:yyyy-MM-dd%/%date:hhmmss%')
    create('cont_status', 'PreviewAny', source=['cont_run', 3])
    total = chunks * chunk_seconds
    return g, {'frames': int(round(total * 24)), 'duration': total, 'profile': 'continuum', 'nodes': len(g),
               'finish': 'now' if refine else 'none', 'engine': 'continuum',
               'seam': 'Native Masked · {} · 오디오 이어받기 {} · 클립 {}개'.format(continuity, '켬' if audio_carry else '끔', chunks),
               'turbo': (turbo.get('lora') if turbo.get('enabled') else '') or '없음',
               'audio_source': ('첨부한 오디오를 그대로 사용 (Driving Audio)' if (audios and driving)
                                else '목소리 참조 %d개 (%s)' % (len(audios), ', '.join('<Audio %d>' % (i + 1) for i in range(len(audios))))
                                if audios else '모델이 생성'),
               'patches': ('Kitchen ' if b.get('kitchen',True) else '') + ('SigmaShift %g/%g' % (float(b.get('shift_video',12)), float(b.get('shift_audio',3))) if b.get('sigma_shift',True) else ''),
               'dropped_keyframes': [], 'color_scope': '꺼짐 (Continuum 조립기가 이음매를 처리)'}
