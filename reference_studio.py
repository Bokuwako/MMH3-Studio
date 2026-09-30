"""Reference image desk: Anima sheets -> Qwen 2.1 edit -> project assets."""
import asyncio
import copy
import csv
import json
import math
import re
import shutil
import time
import uuid
from pathlib import Path
from types import SimpleNamespace
from aiohttp import web


def choices(info, node, field):
    schema=info.get(node,{}).get('input',{})
    spec={**schema.get('required',{}),**schema.get('optional',{})}.get(field,[[]])
    return spec[0] if isinstance(spec[0],list) else (spec[1].get('options',[]) if len(spec)>1 else [])


def workflow_defaults(comfy):
    root=Path(comfy)/'user/default/workflows'
    def read(name):
        p=root/name
        # Without the source workflow every setting below falls back to its default.
        if not p.is_file():return {}
        return {str(n['id']):n for n in json.loads(p.read_text(encoding='utf-8'))['nodes']}
    a=read('Anima_Ref_Sheet.json');q=read('Qwen_Image_edit_2.1.json')
    def w(nodes,n,index,fallback):
        values=nodes.get(n,{}).get('widgets_values') or []
        return values[index] if len(values)>index else fallback
    def lora_stack(nodes,n):
        # easy loraStack in simple mode: toggle, mode, count, then (name, strength, model, clip) per slot.
        # The source workflow feeds this stack to the refine loader only.
        values=nodes.get(n,{}).get('widgets_values') or []
        if len(values)<3 or not values[0]:return []
        out=[]
        for i in range(int(values[2])):
            name,strength=(values[3+i*4:5+i*4]+[None,0])[:2]
            if name and name!='None':out.append({'enabled':bool(strength),'model':name,'strength':strength})
        return out
    def pixaroma(nodes,n):
        # Resolution Pixaroma keeps its choice as a JSON object in the widget; the switch
        # beside it picks that fixed size (True) or the first input image's size (False).
        state=w(nodes,n,0,{})
        state=state if isinstance(state,dict) else {}
        return {'size_mode':'fixed' if w(nodes,'489',0,True) else 'input','ratio':state.get('ratio','3:2'),
                'width':int(state.get('w',1344)),'height':int(state.get('h',896))}
    return {'anima':{'model':w(a,'491',0,'Anima 1.1.safetensors'),'vae':w(a,'698',0,''),'profile':'anima',
        'width':w(a,'491',10,1152),'height':w(a,'491',11,896),'steps':w(a,'496',3,30),'cfg':w(a,'496',4,5),
        'sampler':w(a,'496',5,'res_multistep'),'scheduler':w(a,'496',6,'beta'),'seed':1,'random_seed':True,
        'shift':w(a,'393',0,4),'dcw':True,'sage':True,'upscale':True,'upscaler':w(a,'687',0,''),
        'refine_steps':w(a,'682',3,14),'refine_cfg':w(a,'682',4,6),'refine_denoise':w(a,'682',7,.5),
        'refine_sampler':w(a,'682',5,'er_sde'),'refine_scheduler':w(a,'682',6,'simple'),
        'face':False,'detector':w(a,'694',0,''),'face_steps':w(a,'693',5,4),
        'negative':w(a,'756',0,''),'loras':[],'refine_loras':lora_stack(a,'753')},
        'qwen':{'model':w(q,'496',0,''),'loader':'UNETLoader','clip':w(q,'493',0,''),'vae':w(q,'486',0,''),
        'steps':w(q,'509',2,25),'cfg':w(q,'509',3,1),'sampler':w(q,'509',4,'euler'),'scheduler':w(q,'509',5,'simple'),
        'seed':1,'random_seed':True,'resolution':1024,'cache_device':'auto','cache_dtype':'default','negative':'','loras':[],
        **pixaroma(q,'478')}}


_characters=None


def characters(comfy):
    """Danbooru character tags, most-posted first. Read once from the list EasyUseAnima ships."""
    global _characters
    if _characters is not None:return _characters
    root=Path(comfy)/'custom_nodes/ComfyUI-EasyUseAnima/__easyuse_anima__'
    source=root/'danbooru_2025-09-01.csv'
    if not source.is_file():raise ValueError('단부루 태그 목록이 없습니다: '+str(source))
    rows=[r for r in csv.reader(source.open(encoding='utf-8')) if len(r)>=3 and r[2].isdigit()]
    # A character is qualified by its series, e.g. shiroko_(blue_archive); keep that series
    # when it is itself a copyright tag or one of its aliases.
    series={}
    for name,category,_count,*rest in rows:
        if category=='3':
            series[name]=name
            for alias in (rest[0] if rest else '').split(','):
                if alias:series.setdefault(alias,name)
    korean={}
    described=root/'danbooru_tags_classified.csv'
    if described.is_file():
        korean={r['name']:r['description'] for r in csv.DictReader(described.open(encoding='utf-8')) if r.get('category')=='4'}
    out=[]
    for name,category,count,*rest in rows:
        if category!='4':continue
        qualifier=re.search(r'_\(([^()]+)\)$',name)
        out.append({'tag':name,'count':int(count),'aliases':rest[0] if rest else '',
                    'series':series.get(qualifier.group(1)) if qualifier else None,'ko':korean.get(name,'')})
    out.sort(key=lambda c:-c['count'])
    _characters=out
    return out


def search_characters(comfy,query,limit=12):
    query=query.strip().lower()
    if not query:return []
    key=query.replace(' ','_')
    hangul=any('가'<=ch<='힣' for ch in query)
    hits=[]
    for c in characters(comfy):
        name=c['tag']
        if hangul:rank=0 if query in c['ko'] else None
        elif name==key:rank=0
        elif name.startswith(key):rank=1
        elif key in name:rank=2
        elif key in c['aliases']:rank=3
        else:rank=None
        if rank is not None:hits.append((rank,c))
    hits.sort(key=lambda h:(h[0],-h[1]['count']))
    return [{'tag':c['tag'],'count':c['count'],'series':c['series'],
             'note':c['ko'].split('.')[0][:90] if c['ko'] else ''} for _,c in hits[:limit]]


def build(stage, body, info, input_files=()):
    """Build only this request, never execute the prompts saved in the source UI JSON."""
    g={};p=body['settings'];text=str(body.get('prompt','')).strip()
    if not text:raise ValueError('프롬프트를 입력하세요.')
    def add(key,cls,**inputs):
        if cls not in info:raise ValueError('설치되지 않은 노드: '+cls)
        g[key]={'class_type':cls,'inputs':inputs};return [key,0]
    def integer(key,default,low,high):
        v=int(p.get(key,default))
        if not low<=v<=high:raise ValueError(key+' 설정 범위를 확인하세요.')
        return v
    seed=integer('seed',1,0,2**53-1)
    def loras(model,clip,key='loras',prefix='lora_'):
        for i,l in enumerate(p.get(key,[])):
            if not l.get('enabled',True) or not l.get('model'):continue
            strength=float(l.get('strength',1))
            if not math.isfinite(strength):raise ValueError('LoRA 강도가 올바르지 않습니다.')
            model=add(prefix+str(i),'LoraLoader',model=model,clip=clip,lora_name=l['model'],strength_model=strength,strength_clip=strength)
            clip=[model[0],1]
        return model,clip
    if stage=='anima':
        add('checkpoint','CheckpointLoaderSimple',ckpt_name=p['model'])
        vae=add('vae','VAELoader',vae_name=p['vae']) if p.get('vae') else ['checkpoint',2]
        def prepare(key,prefix):
            # Each pass gets its own LoRA stack from the same checkpoint, as the source
            # workflow's second Efficient Loader does for the refine.
            model,clip=loras(['checkpoint',0],['checkpoint',1],key,prefix+'lora_')
            if p.get('profile','anima')=='anima':
                if p.get('dcw',True):model=add(prefix+'dcw','DCWModelPatch',model=model,lambda_l=.08,lambda_h=.018,enabled=True)
                model=add(prefix+'flow','ModelSamplingAuraFlow',model=model,shift=float(p.get('shift',4)),sampling='flow')
            if p.get('sage',True):model=add(prefix+'attention','PathchSageAttentionKJ',model=model,sage_attention='auto',allow_compile=False)
            positive=add(prefix+'positive','CLIPTextEncode',clip=clip,text=text)
            negative=add(prefix+'negative','CLIPTextEncode',clip=clip,text=str(p.get('negative','')))
            return model,clip,positive,negative
        model,clip,positive,negative=prepare('loras','')
        width=integer('width',1152,64,4096);height=integer('height',896,64,4096)
        if body.get('slot')=='detail' and body.get('target')=='character':
            # The face sheet is narrower than the full-body sheet: half its width unless set.
            width=int(p.get('face_width') or width//2//32*32)
            if not 64<=width<=4096:raise ValueError('얼굴 시트 가로 설정 범위를 확인하세요.')
        if width%32 or height%32:raise ValueError('가로·세로는 32의 배수로 입력하세요.')
        latent=add('latent','EmptySD3LatentImage' if p.get('profile','anima')=='anima' else 'EmptyLatentImage',width=width,height=height,batch_size=1)
        latent=add('sample','KSampler',model=model,positive=positive,negative=negative,latent_image=latent,
                   seed=seed,steps=integer('steps',30,1,150),cfg=float(p.get('cfg',5)),sampler_name=p.get('sampler','res_multistep'),scheduler=p.get('scheduler','beta'),denoise=1.)
        images=add('decode','VAEDecode',samples=latent,vae=vae)
        if p.get('upscale',True):
            model,clip,positive,negative=prepare('refine_loras','refine_')
            images=add('upscale','ImageUpscaleWithModel',image=images,upscale_model=add('upscale_model','UpscaleModelLoader',model_name=p['upscaler']))
            latent=add('encode_upscale','VAEEncode',pixels=images,vae=vae)
            latent=add('refine','KSampler',model=model,positive=positive,negative=negative,latent_image=latent,seed=seed,
                       steps=integer('refine_steps',14,1,150),cfg=float(p.get('refine_cfg',6)),sampler_name=p.get('refine_sampler','er_sde'),scheduler=p.get('refine_scheduler','simple'),denoise=float(p.get('refine_denoise',.5)))
            images=add('decode_upscale','VAEDecode',samples=latent,vae=vae)
        if p.get('face'):
            provider=add('detector','UltralyticsDetectorProvider',model_name=p['detector'])
            values={}
            for key,spec in info.get('FaceDetailer',{}).get('input',{}).get('required',{}).items():
                config=spec[1] if len(spec)>1 else {}
                if 'default' in config:values[key]=config['default']
                elif isinstance(spec[0],list):values[key]=spec[0][0]
            values.update(image=images,model=model,clip=clip,vae=vae,positive=positive,negative=negative,bbox_detector=provider,
                          segm_detector_opt=['detector',1],seed=seed,steps=integer('face_steps',4,1,100),denoise=.25,guide_size=1024,max_size=1536,wildcard='')
            images=add('face','FaceDetailer',**values)
    elif stage=='qwen':
        if not 1<=len(input_files)<=16:raise ValueError('편집할 이미지 1~16장을 선택하세요.')
        loader=p.get('loader','UNETLoader')
        if loader not in ('UNETLoader','UnetLoaderGGUF'):raise ValueError('지원하지 않는 모델 로더')
        model=add('model',loader,unet_name=p['model'],**({'weight_dtype':'default'} if loader=='UNETLoader' else {}))
        clip=add('clip','CLIPLoader',clip_name=p['clip'],type='qwen_image',device='default')
        vae=add('vae','VAELoader',vae_name=p['vae']);model,clip=loras(model,clip)
        model=add('cache','QwenImage21Cache',model=model,device=p.get('cache_device','auto'),dtype=p.get('cache_dtype','default'))
        refs={f'images.image_{i+1}':add('image_'+str(i),'LoadImage',image=file) for i,file in enumerate(input_files)}
        encoded=add('edit_prompt','TextEncodeQwenImage21',clip=clip,vae=vae,prompt=text,negative_prompt=str(p.get('negative','')),resolution=integer('resolution',1024,0,4096),**refs)
        latent=['edit_prompt',2]
        if p.get('size_mode','fixed')=='fixed':
            latent=add('latent','EmptyLatentImage',width=integer('width',1344,64,4096),height=integer('height',896,64,4096),batch_size=1)
        latent=add('sample','KSampler',model=model,positive=encoded,negative=['edit_prompt',1],latent_image=latent,seed=seed,
                   steps=integer('steps',25,1,150),cfg=float(p.get('cfg',1)),sampler_name=p.get('sampler','euler'),scheduler=p.get('scheduler','simple'),denoise=1.)
        images=add('decode','VAEDecode',samples=latent,vae=vae)
    else:raise ValueError('지원하지 않는 생성 단계')
    add('save','SaveImage',images=images,filename_prefix='studio_references/'+stage)
    return g


def install(routes, *, comfy, assets, load, save, remote, info, jobs, job, lock, safe_media, validate, kill):
    async def result(body):
        pid=body.get('job_id');index=int(body.get('index',0))
        if pid not in jobs or jobs[pid].get('deleted') or jobs[pid].get('settings',{}).get('task_type')!='reference_image':raise ValueError('레퍼런스 생성 결과가 없습니다.')
        if jobs[pid]['state']!='completed':raise ValueError('완료된 결과만 선택할 수 있습니다.')
        images=[o for o in jobs[pid].get('outputs',[]) if o.get('node')=='save' and Path(o.get('filename','')).suffix.lower() in ('.png','.jpg','.webp')]
        if index<0 or index>=len(images):raise ValueError('이미지 번호가 올바르지 않습니다.')
        o=images[index];return safe_media(str(Path(o.get('subfolder',''))/o['filename']),o.get('type','output'))
    @routes.get('/api/ref-studio/characters')
    async def character_search(r):
        return web.json_response(await asyncio.to_thread(search_characters,comfy,r.query.get('q','')))
    @routes.get('/api/ref-studio/catalog')
    async def catalog(r):
        schemas=await info()
        return web.json_response({'defaults':workflow_defaults(comfy),'models':{key:choices(schemas,cls,field) for key,cls,field in [
            ('checkpoints','CheckpointLoaderSimple','ckpt_name'),('diffusion','UNETLoader','unet_name'),('gguf','UnetLoaderGGUF','unet_name'),
            ('clips','CLIPLoader','clip_name'),('vaes','VAELoader','vae_name'),('loras','LoraLoader','lora_name'),('upscalers','UpscaleModelLoader','model_name'),
            ('detectors','UltralyticsDetectorProvider','model_name'),('samplers','KSampler','sampler_name'),('schedulers','KSampler','scheduler')]}})
    @routes.get('/api/ref-studio/state')
    async def state(r):return web.json_response(load('reference_workspace.json',{}))
    @routes.post('/api/ref-studio/state')
    async def state_save(r):save('reference_workspace.json',await r.json());return web.json_response({'ok':True})
    @routes.get('/api/ref-studio/jobs')
    async def job_list(r):return web.json_response([j for j in reversed(list(jobs.values())) if j.get('settings',{}).get('task_type')=='reference_image' and not j.get('deleted')])
    @routes.post('/api/ref-studio/generate')
    async def generate(r):
        b=await r.json();stage=b.get('stage');b['settings']=dict(b.get('settings',{}))
        if b['settings'].get('random_seed',True):b['settings']['seed']=uuid.uuid4().int%(2**32)
        async with lock:
            schemas=await info();files=[]
            for source in b.get('sources',[]) if stage=='qwen' else []:
                if source.get('job_id'):
                    path=await result(source);target=Path(comfy)/'input/mmh3_studio'/('ref_'+uuid.uuid4().hex+path.suffix)
                    target.parent.mkdir(parents=True,exist_ok=True);await asyncio.to_thread(shutil.copy2,path,target)
                    files.append('mmh3_studio/'+target.name)
                else:
                    path=safe_media(source['file']);
                    if path.suffix.lower() not in ('.png','.jpg','.jpeg','.webp'):raise ValueError('이미지만 편집에 사용할 수 있습니다.')
                    files.append(str(path.relative_to(Path(comfy)/'input')).replace('\\','/'))
            graph=build(stage,b,schemas,files);graph.update(kill(schemas))
            # LoadImage's menu omits uploaded subfolders. Paths were checked above;
            # ComfyUI performs its own file validation when accepting the graph.
            checks=copy.deepcopy(schemas)
            if files:checks['LoadImage']['input']['required']['image'][0]=files
            errors=validate(graph,checks)
            if errors:raise ValueError('\n'.join(errors))
            q=await remote('/queue')
            if not q.get('queue_running') and not q.get('queue_pending'):
                try:
                    residents=await remote('/api/ps',service='ollama')
                    for model in residents.get('models',[]):await remote('/api/generate',{'model':model['name'],'keep_alive':0},service='ollama')
                except Exception:pass  # Image generation does not require Ollama to be running.
            # ComfyUI's own page asks for sampler previews per prompt; without this the
            # server default (none) applies and KSampler sends no live frames.
            answer=await remote('/prompt',{'prompt':graph,'client_id':'mmh3-studio','extra_data':{'preview_method':'auto'}});pid=answer['prompt_id']
            entry={'id':pid,'created':time.time(),'state':'queued','settings':{**b,'task_type':'reference_image'},'outputs':[]}
            jobs[pid]=entry;save('jobs.json',jobs)
        return web.json_response(entry)
    @routes.post('/api/ref-studio/asset')
    async def to_asset(r):
        b=await r.json()
        async with lock:
            source=await result(b)
            return web.json_response(assets.store(b['project'],source,{'name':b.get('name') or '레퍼런스 이미지','type':'image','role':b.get('role','character_full'),'purpose':b.get('purpose','')}))
