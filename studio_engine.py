"""Build independent API graphs from the user's current H3 pipeline."""
import copy
import hashlib
import json
from pathlib import Path

HERE=Path(__file__).parent
PROFILES=('ref_base','ref_upscale','other_base','other_upscale')
MODES=('T2VA','I2VA','FL2VA','L2VA','REF2VA')

def template(): return json.loads((HERE/'workflows/current.json').read_text(encoding='utf-8'))
def link(v): return isinstance(v,list) and len(v)==2 and isinstance(v[0],str) and isinstance(v[1],int)
def aligned(n): return max(5,int(n))+(5-max(5,int(n)))%17
def upscale_size(width,height,inputs):
    mode=inputs.get('mode')
    if mode=='megapixels':
        target=float(inputs.get('mode.megapixels',1))*1024*1024
        h=(target/(width/height))**.5;w=h*width/height
    elif mode=='scale by multiplier':
        scale=float(inputs.get('mode.scale',2));w=width*scale;h=height*scale
    elif mode=='target dimensions':
        w=float(inputs.get('mode.width',1280));h=float(inputs.get('mode.height',704))
    else:raise ValueError('알 수 없는 3D 업스케일 크기 설정입니다.')
    a=max(1,int(inputs.get('align',32)))
    w=round(w/a)*a
    h=w/(width/height) if inputs.get('keep_proportion') else round(h/a)*a
    return (max(16,round(w/16)*16),max(16,round(h/16)*16))
def num(value, default=0.0):
    """Empty widgets arrive as '' or None; treat them as the default."""
    try:
        if value is None or value == "": return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)

# The preview node counts latent tokens, and H3 packs 17 pixel frames into 5 of them,
# so a token is 3.4 frames and 7 fps plays the preview at the clip's real speed. taeh3
# chains its temporal state forward, so asking for fewer tokens decodes the opening of
# the clip rather than sampling across it: fewer seconds means the first few seconds.
PREVIEW_FPS=7
def preview(frames,b):
    tokens=5*((frames-5)//17)+2
    seconds=num(b.get('preview_seconds'))
    shown=int(round(seconds*PREVIEW_FPS)) if seconds>0 else tokens
    return {'preview_frames':max(1,min(tokens,shown)),'preview_fps':PREVIEW_FPS}

def defaults(info,cls):
    out={}
    for key,spec in info[cls]['input'].get('required',{}).items():
        cfg=spec[1] if len(spec)>1 else {}
        if 'default' in cfg: out[key]=cfg['default']
        elif isinstance(spec[0],list) and spec[0]: out[key]=spec[0][0]
        elif spec[0]=='COMBO' and cfg.get('options'):out[key]=cfg['options'][0]
    return out

def create(g,info,nid,cls,**kw):
    if cls not in info: raise ValueError('설치되지 않은 노드: '+cls)
    g[nid]={'class_type':cls,'inputs':{**defaults(info,cls),**kw}}
    return [nid,0]

def prune(g,outputs):
    used=set(); active=set()
    def visit(nid):
        if nid in active: raise ValueError('워크플로우 순환 연결: '+nid)
        if nid in used: return
        if nid not in g: raise ValueError('누락된 연결: '+nid)
        active.add(nid)
        for v in g[nid]['inputs'].values():
            if link(v): visit(v[0])
        active.remove(nid);used.add(nid)
    for nid in outputs: visit(nid)
    return {k:v for k,v in g.items() if k in used}

def build(b,info):
    g=template();mode=b.get('mode','REF2VA')
    if mode not in MODES: raise ValueError('지원 모드: '+', '.join(MODES))
    def ins(n): return g[n]['inputs']
    duration=int(b.get('duration',5));frames=aligned(duration*24)
    if duration<1: raise ValueError('길이는 1초 이상이어야 합니다.')
    if b.get('frames') and int(b['frames'])!=frames:
        raise ValueError(f'H3 프레임 격자와 Director 길이가 다릅니다. {duration}초는 {frames}프레임입니다.')
    width,height=int(b.get('width',768)),int(b.get('height',512))
    if min(width,height)<32 or width%32 or height%32: raise ValueError('가로·세로는 32의 배수여야 합니다.')
    prompt=str(b.get('prompt','')).strip()
    if not prompt: raise ValueError('프롬프트를 먼저 작성하세요.')
    # Advanced scalar parameters preserve all settings in the captured pipeline.
    for nid,overrides in b.get('advanced',{}).items():
        if nid not in g: raise ValueError('알 수 없는 고급 설정 노드: '+nid)
        for key,value in overrides.items():
            if key not in ins(nid) or link(ins(nid)[key]) or isinstance(value,(list,dict)):
                raise ValueError('고급 설정은 기존 값만 바꿀 수 있습니다: '+key)
            ins(nid)[key]=value
    refs=[r for r in b.get('refs',[]) if r.get('enabled',True)]
    image_refs=[r for r in refs if r.get('type','image')=='image']
    if mode=='REF2VA':
        videos=[r for r in refs if r.get('type')=='video' and r.get('media_mode','video')!='audio']
        audios=[r for r in refs if r.get('type')=='audio' or r.get('type')=='video' and r.get('media_mode') in ('audio','video_audio')]
        if len(image_refs)>9 or len(videos)>3 or len(audios)>3 or len(refs)>12:raise ValueError('REF2VA 참조 한도: 이미지 9개 · 영상 3개 · 오디오 3개 · 전체 12개')
        if audios and not image_refs and not videos:raise ValueError('오디오 참조와 함께 이미지 또는 영상이 필요합니다.')
        for kind,items in [('영상',videos),('오디오',audios)]:
            durations=[num(r.get('trim_end') or r.get('duration',0))-num(r.get('trim_start')) for r in items]
            if any(d<2 or d>15 for d in durations) or sum(durations)>15:raise ValueError(kind+' 참조는 각각 2~15초, 합계 15초 이하여야 합니다. 자르기 구간을 확인하세요.')
    known_loras=set(info.get('LoraLoaderModelOnly',{}).get('input',{}).get('required',{}).get('lora_name',[[]])[0])
    for lora in b.get('loras',[]):
        if lora.get('on') and lora.get('lora') not in known_loras:raise ValueError('설치된 추가 LoRA를 선택하세요: '+str(lora.get('lora','')))
    if mode in ('I2VA','L2VA') and not image_refs: raise ValueError('프레임 이미지가 필요합니다.')
    if mode=='FL2VA' and len(image_refs)<2: raise ValueError('FL2VA는 첫·마지막 프레임 이미지가 필요합니다.')
    if mode=='REF2VA' and not refs: raise ValueError('REF2VA 레퍼런스를 추가하세요.')
    # Protected prefix: the carried frames are given content, so a keyframe
    # pinned inside them fights the hold. Continuum drops exactly these.
    mask_prefix=bool(b.get('mask_prefix',True)) and bool(b.get('chain',False))
    protected_seconds=(int(b.get('context_length',22))/24.0) if mask_prefix else 0.0
    dropped=[]
    items=[];counts={}
    for r in refs:
        typ=r.get('type','image');slot=counts.get(typ,0);counts[typ]=slot+1
        if not r.get('file'): raise ValueError('업로드되지 않은 레퍼런스가 있습니다.')
        if (protected_seconds and typ=='image' and r.get('role') in ('first_frame','last_frame')
                and num(r.get('start'))<protected_seconds):
            dropped.append(r.get('name') or r['file']);continue
        items.append({'id':f'{typ}-{slot}','type':typ,'value':r['file'],'enabled':True,'slot':slot,'order':len(items),
                      'start':num(r.get('start'),slot if mode=='REF2VA' else 0),
                      'duration':num(r.get('duration'),1), 'trim_start':num(r.get('trim_start')),
                      'trim_end':r.get('trim_end') or None,'media_mode':r.get('media_mode','video')})
    if '2722' in g:
        ins('2722').update(**preview(frames,b))
    ins('2693').update(mode=mode,width=width,height=height,duration=duration,frame_rate=24.0,
                       prompt=prompt,external_prompt_overwrite=prompt,builder_state='{}',
                       external_width_overwrite=width,external_height_overwrite=height,
                       timeline_data=json.dumps({'version':1,'items':items},ensure_ascii=False))
    for nid in ('1512:2700','1512:2701'):
        ins(nid)['guide']=['2693',0]
        # Studio node pack: same guide, but calls Core's H3 nodes by keyword.
        if 'MMH3S_DirectorGuide' in info: g[nid]['class_type']='MMH3S_DirectorGuide'
    # Break UI-only prompt and size dependencies; graph now owns these values.
    ins('2906')['prompt_text']=prompt
    ins('1512:2963')['prompt']=prompt
    ref=mode=='REF2VA'; base='1512:2668' if ref else '1512:2591'; guide='1512:2700' if ref else '1512:2701'
    loader='1512:2588' if ref else '1512:2586'
    if b.get('model'): ins(loader)['unet_name']=b['model']
    for nid,key,option in [('1512:2587','clip_name','clip'),('1512:2584','vae_name','video_vae'),('1512:2585','vae_name','audio_vae')]:
        if b.get(option): ins(nid)[key]=b[option]
    profiles=b.get('turbo',{})
    base_profile=profiles.get('ref_base' if ref else 'other_base',{})
    up_profile=profiles.get('ref_upscale' if ref else 'other_upscale',{})
    def turbo(nid,source,profile):
        if not profile.get('enabled'): return source
        if not profile.get('lora'): raise ValueError('켜진 터보 프로필의 LoRA를 선택하세요.')
        return create(g,info,nid,'LoraLoaderModelOnly',model=source,lora_name=profile['lora'],strength_model=float(profile.get('strength',1)))
    # Each pass starts from a clean checkpoint, not the already patched base model.
    base_model=turbo('studio_base_turbo',[loader,0],base_profile)
    up_model=turbo('studio_up_turbo',[loader,0],up_profile)
    if b.get('kitchen',True):
        base_model=create(g,info,'studio_base_kitchen','PathchComfyKitchenAttentionDaSiWa',model=base_model)
        up_model=create(g,info,'studio_up_kitchen','PathchComfyKitchenAttentionDaSiWa',model=up_model)
    create(g,info,'studio_base_patch','ModelPatchTorchSettings',model=base_model,enable_fp16_accumulation=False)
    create(g,info,'studio_up_patch','ModelPatchTorchSettings',model=up_model,enable_fp16_accumulation=False)
    ins('2693')['ref2va_model']=['studio_base_patch',0];ins('2693')['fl2va_model']=['studio_base_patch',0]
    ins('2678').update(model=['studio_base_patch',0],model_upscale=['studio_up_patch',0],stack_data=json.dumps(b.get('loras',[])),use_cache=False)
    # Named upscale input is checked against installed schema below.
    if 'model_upscale' not in {**info['DaSiWa_LTX2LoraLoader']['input'].get('required',{}),**info['DaSiWa_LTX2LoraLoader']['input'].get('optional',{})}:
        ins('2678').pop('model_upscale',None)
        create(g,info,'studio_up_loras','DaSiWa_LTX2LoraLoader',model=['studio_up_patch',0],clip=['1512:2587',0],stack_data=json.dumps([{**x,'tgt':'both'} for x in b.get('loras',[]) if x.get('tgt','both') in ('both','up')]),use_cache=False)
        ins('1512:2825')['model']=['studio_up_loras',0]
    else: ins('1512:2825')['model']=['2678',2]
    ins('1512:2590').update(steps=int(b.get('steps',12)),model=['2722',0])
    ins('1512:2600')['noise_seed']=int(b.get('seed',0))
    ins(base)['guider']=['1512:2667' if ref else '1512:2592',0]
    # Use the installed base sampler, without an extra latent save output.
    # Normal engine makes one clip. Chaining, projects and their Project Suite
    # nodes moved to the Continuum engine, so nothing here touches them.
    project='';chain=False;outputs=[];trim=0
    if chain and not project:raise ValueError('이어 만들기를 사용하려면 저장 프로젝트를 선택하세요.')
    if project:
        hub=create(g,info,'studio_project','H3ProjectHub',project_name=project,create_if_missing=True)
    has_tail=bool(b.get('_chain_active',False))
    if chain and not has_tail:
        raise ValueError('이어받을 승인 클립의 latent가 없습니다. 영상 파일만 보관한 항목은 이어받을 수 없습니다. 이어받기 데이터가 있는 클립을 저장·승인하거나, 이어 만들기를 끄고 첫 클립을 생성하세요.')
    tail_size=tuple(b.get('_tail_size',[]))
    base_tail_size=tuple(b.get('_base_tail_size',b.get('_tail_size',[])))
    if project and chain and has_tail and base_tail_size != (width,height):
        raise ValueError('이전 클립의 저해상도 이어받기 데이터가 없거나 크기가 다릅니다. 같은 베이스 해상도의 새 프로젝트로 시작하세요.')
    if project and chain and int(b.get('context_length',22)) not in (5,22,39,56):
        raise ValueError('정확한 latent 이어받기는 5·22·39·56프레임 중에서 선택하세요.')
    if project and chain:
        context=create(g,info,'studio_context','H3Context',conditioning=[guide,0],latent=[guide,1],
                       context_latent=['studio_project',4],enabled=['studio_project',2],vae=['1512:2584',0],
                       context_length=int(b.get('context_length',22)),video_source='latent',anchor_mode='head',seed_head=mask_prefix,head_hold=1.0)
        # Taper converts Context's plain video-only mask into the nested (video,
        # audio) mask LTXVSeparateAVLatent requires. With no mask it passes through.
        taper=create(g,info,'studio_taper_a','MMH3_HeadMaskTaper',latent=['studio_context',2],trim_frames=0,enabled=False)
        ins('1512:2667' if ref else '1512:2592')['conditioning']=context
        ins(base)['latent_image']=taper;trim=['studio_context',1]
    latent=[base,1]
    # Bypass upscale by changing only decoder sources, leaving the base pass intact.
    finish=str(b.get('finish') or ('now' if b.get('upscale',True) else 'none'))
    if finish not in ('now','later','none'): raise ValueError("고화질 마감은 'now' · 'later' · 'none' 중 하나입니다.")
    upscale=finish=='now'
    seam='꺼짐'
    final_latent=['1512:2753' if ref else '1512:2794',1] if upscale else latent
    if upscale:
        sampler='1512:2753' if ref else '1512:2794'
        upscaler='1512:2762' if ref else '1512:2860'
        ins(sampler)['guider']=['1512:2756' if ref else '1512:2798',0]
        if b.get('upscale_mp'): ins(upscaler)['mode.megapixels']=float(b['upscale_mp'])
        # Upscaler-Plus added this input; the captured template predates it.
        ins(upscaler)['offload_after_upscale']=bool(b.get('offload_upscaler',True))
        # Carry the previous clip's COMPLETED refine tail, never this clip's raw
        # upscaler output: holding the upscaler's own prefix left its residue in
        # place and the refine pass spread it as speckle.
        if project and chain and mask_prefix:
            target=upscale_size(width,height,ins(upscaler));tail=tuple(b.get('_tail_size') or ())
            if not tail: raise ValueError('앞 클립의 고화질 latent가 없습니다. 이음매 이어받기를 끄거나, 앞 클립부터 고화질로 마감하세요.')
            if tuple(target)!=tail:
                raise ValueError('앞 클립의 고화질 크기 {}×{} 와 이번 설정 {}×{} 가 다릅니다. 업스케일 목표 MP를 앞 클립과 같게 맞추세요.'.format(tail[0],tail[1],target[0],target[1]))
            ins(sampler)['latent_image']=create(g,info,'studio_seam','H3RefinedPrefix',
                latent=['1512:2763' if ref else '1512:2797',0],previous=['studio_project',1],
                trim_frames=int(b.get('context_length',22)),sigmas=['1512:2758' if ref else '1512:2792',0])
            seam='잠금 {}프레임 · 베이스에서 고정 · refine은 앞 클립 완성본으로 교체'.format(int(b.get('context_length',22)))
    project_latent=final_latent
    images=create(g,info,'studio_decode','VAEDecode',samples=final_latent,vae=['1512:2584',0])
    # Audio comes from the base pass, as the captured workflow did: the refine
    # pass exists to sharpen video and would re-roll the voice for nothing.
    audio=create(g,info,'studio_audio','VAEDecodeAudio',samples=latent,vae=['1512:2585',0])
    if b.get('motion'):
        ins('1512:2933')['images']=images;ins('1512:2934')['audio']=audio;ins('1512:2944')['reference']=audio
        ins('1512:2940')['guider']=['1512:2939',0]
        images=['1512:2943',0];audio=['1512:2944',0]
    if b.get('face'):
        ins('1512:2962')['images']=images;ins('1512:2973')['base_images']=images
        ins('1512:2963')['ref_audios.ref_audio_0']=audio;ins('1512:2965')['audio']=audio
        ins('1512:2971')['guider']=['1512:2970',0]
        images=['1512:2973',0]
    if project and chain:
        create(g,info,'studio_trim','H3ContextTrim',images=images,audio=audio,trim_frames=trim,fps=24.0)
        images=['studio_trim',0];audio=['studio_trim',1]
    post=b.get('post',{})
    for key,cls,input_name in [('resize','DaSiWa_TorchResize','image'),('rtx','DaSiWa_RTX_UpscalerRefiner','images'),('watermark','DaSiWa_Watermark','images')]:
        options=post.get(key,{})
        if options.get('enabled'):
            images=create(g,info,'studio_'+key,cls,**{**options.get('values',{}),input_name:images})
    if post.get('model_upscale',{}).get('enabled'):
        options=post['model_upscale'];model=create(g,info,'studio_upscale_model','UpscaleModelLoader',**options.get('values',{}))
        images=create(g,info,'studio_image_upscale','ImageUpscaleWithModel',image=images,upscale_model=model)
    final_fps=24
    if post.get('interpolate',{}).get('enabled'):
        options=post['interpolate'];model=create(g,info,'studio_interpolation_model','FrameInterpolationModelLoader',model_name=options.get('model','rife_v4.26.safetensors'))
        multiplier=int(options.get('multiplier',2))
        images=create(g,info,'studio_interpolate','FrameInterpolate',interp_model=model,images=images,multiplier=multiplier)
        final_fps*=multiplier
    if b.get('color',{}).get('enabled'):
        if not project: raise ValueError('자동 색 보정은 기준 클립을 저장할 프로젝트를 선택하세요. 첫 클립은 기준으로 기록됩니다.')
        c=b['color'];images=create(g,info,'studio_color','MMH3_ColorCarry',images=images,latent=project_latent,vae=['1512:2584',0],project=['studio_project',0],chain_active=['studio_project',2],trim_frames=0,enabled=True,strength=float(c.get('strength',1)),max_luma_shift=float(c.get('max_luma_shift',0.04)),max_saturation_change=float(c.get('max_saturation_change',0.15)),reset_anchor=bool(c.get('reset_anchor',False)))
        project_latent=['studio_color',1]
    ins('2568').update(images=images,audio=audio,codec='H.264',audio_codec='AAC',frame_rate=float(final_fps),filename_prefix='studio/%date:yyyy-MM-dd%/%date:hhmmss%',save_output=True)
    outputs.append('2568')
    if project:
        create(g,info,'studio_project_save','H3ProjectSave',project=['studio_project',0],latent=project_latent,images=images,audio=audio,fps=final_fps,**({'base_latent':latent} if upscale else {}));outputs.append('studio_project_save')
    g=prune(g,outputs)
    return g,{'frames':frames,'duration':frames/24,'profile':'ref' if ref else 'other','nodes':len(g),'finish':finish,'seam':seam,'dropped_keyframes':dropped,'color_scope':'최종 프레임 전체 + 다음 클립 latent' if b.get('color',{}).get('enabled') else '꺼짐'}

def validate(g,info):
    errors=[]
    for nid,n in g.items():
        cls=n['class_type'];schema=info.get(cls)
        if not schema: errors.append(f'{cls}: 설치되지 않은 노드');continue
        fields={**schema['input'].get('required',{}),**schema['input'].get('optional',{})}
        for key,spec in schema['input'].get('required',{}).items():
            if key not in n['inputs'] and not any(k.startswith(key+'.') for k in n['inputs']): errors.append(f'{cls}.{key}: 필수 입력 누락')
        for key,v in n['inputs'].items():
            spec=fields.get(key)
            if link(v):
                source=g.get(v[0]);types=info.get(source['class_type'],{}).get('output',[]) if source else []
                if v[1]<0 or v[1]>=len(types): errors.append(f'{cls}.{key}: 출력 연결이 유효하지 않습니다')
                continue
            if not spec: continue # expandable inputs are validated by ComfyUI
            typ=spec[0];cfg=spec[1] if len(spec)>1 else {}
            if typ=='COMBO':typ=cfg.get('options',[])
            if isinstance(typ,list) and v not in typ: errors.append(f'{cls}.{key}: 설치된 선택지에 없음 ({v})')
            if typ in ('INT','FLOAT') and (not isinstance(v,(int,float)) or isinstance(v,bool)): errors.append(f'{cls}.{key}: 숫자가 필요합니다')
            if isinstance(v,(int,float)) and not isinstance(v,bool):
                if 'min' in cfg and v<cfg['min'] or 'max' in cfg and v>cfg['max']: errors.append(f'{cls}.{key}: 허용 범위를 벗어났습니다')
    return errors

def fingerprint(g): return hashlib.sha256(json.dumps(g,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def changes(before,after):
    return [f'{nid} · {after.get(nid,before.get(nid))["class_type"]}' for nid in sorted(set(before)|set(after)) if before.get(nid)!=after.get(nid)]

