"""Local H3 Studio. Rendering stays in ComfyUI; editing stays in the installed pack."""
import asyncio
import base64
import json
import mimetypes
import os
import shutil
import subprocess
import time
import uuid
import sys
from pathlib import Path
from urllib.parse import urlencode
sys.path.insert(0,str(Path(__file__).resolve().parent))
from aiohttp import web, ClientSession, ClientTimeout, FormData
import pack_bridge as pack
import studio_engine as engine
import studio_continuum as continuum
import frame_color
from project_assets import ProjectAssets
from project_inbox import adopt, video_output, DRAFT_PREFIX
from project_inbox import core as project_core
import project_timeline as timeline
import finish_runner
from finish_runner import record as finish_record
from studio_trash import Trash, delete_clip

HERE=Path(__file__).parent
DATA=HERE/'data';DATA.mkdir(exist_ok=True)
assets=ProjectAssets(DATA/'asset_projects')
trash=Trash(DATA/'trash',[DATA,pack.COMFY/'output'])
DEFAULT={'comfy_url':'http://127.0.0.1:8188','ollama_url':'http://127.0.0.1:11434'}

def production_jobs(records):
    """Select the latest attempt before filtering tombstones; never promote an older result."""
    candidates = [j for j in records if j.get('settings', {}).get('task_type') != 'reference_image'
                  and not j.get('settings', {}).get('maintenance')]
    candidates.sort(key=lambda j: j.get('created', 0), reverse=True)
    active = [j for j in candidates if j.get('state') in ('queued', 'running') and not j.get('deleted')]
    latest = next((j for j in candidates if j.get('state') not in ('queued', 'running')), None)
    return active + ([latest] if latest and not latest.get('deleted') else [])


def load(name,default):
    try:return json.loads((DATA/name).read_text(encoding='utf-8'))
    except (FileNotFoundError,json.JSONDecodeError):return default
def save(name,data):
    p=DATA/name;t=p.with_suffix('.tmp');t.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8');t.replace(p)
def safe_media(filename,folder='input'):
    if folder not in ('input','output','temp'):raise ValueError('허용되지 않는 미디어 경로')
    root=(pack.COMFY/folder).resolve();p=(root/filename).resolve()
    if not p.is_relative_to(root) or not p.is_file(): raise ValueError('미디어 파일을 찾을 수 없습니다: '+filename)
    return p

@web.middleware
async def errors(request,handler):
    # Local-only app: reject cross-origin write requests from unrelated sites.
    origin=request.headers.get('Origin','')
    if request.method not in ('GET','HEAD') and origin and origin!=f'{request.scheme}://{request.host}':
        raise web.HTTPForbidden(text='다른 사이트의 요청은 허용되지 않습니다.')
    try:response=await handler(request)
    except web.HTTPException:raise
    except Exception as exc:return web.json_response({'error':str(exc)},status=400)
    # The app's own files change while it runs; never let a browser hold an old copy.
    if request.path=='/' or request.path.startswith('/web/'):
        response.headers['Cache-Control']='no-store, must-revalidate'
    return response

def build_app():
    app=web.Application(middlewares=[errors],client_max_size=1024**3)
    routes=web.RouteTableDef();cfg=load('config.json',DEFAULT.copy());jobs=load('jobs.json',{});lock=asyncio.Lock()
    preview={'image':None,'type':'image/jpeg','at':0,'job':''}
    async def monitor():
        active=None
        while True:
            try:
                async with ClientSession() as session:
                    async with session.ws_connect(cfg['comfy_url'].replace('http','ws',1)+'/ws?clientId=mmh3-studio',heartbeat=20) as ws:
                        async for msg in ws:
                            if msg.type.name=='BINARY':
                                # ComfyUI preview frame: 4-byte event, 4-byte image
                                # format (1=JPEG, 2=PNG), then the encoded image.
                                raw=msg.data
                                if len(raw)>8 and int.from_bytes(raw[:4],'big')==1:
                                    kind='image/png' if int.from_bytes(raw[4:8],'big')==2 else 'image/jpeg'
                                    preview.update(image=raw[8:],type=kind,at=time.time(),job=active or '')
                                continue
                            if msg.type.name!='TEXT':continue
                            event=json.loads(msg.data);data=event.get('data',{});kind=event.get('type')
                            if kind in ('execution_start','executing'):
                                active=data.get('prompt_id',active)
                                if active in jobs:jobs[active]['node']=data.get('node');jobs[active]['state']='running'
                            if kind=='kj_preview_override' and data.get('image'):
                                # Model Preview Override sends base64 in a text event,
                                # not the core previewer's binary frame.
                                try:preview.update(image=base64.b64decode(data['image']),
                                                   type=str(data.get('mime') or 'image/jpeg'),
                                                   at=time.time(),job=active or '')
                                except Exception:pass
                            if kind=='progress' and active in jobs:
                                jobs[active]['progress']={'value':data.get('value',0),'max':data.get('max',0)}
            except asyncio.CancelledError:raise
            except Exception:await asyncio.sleep(3)
    async def lifecycle(app):
        task=asyncio.create_task(monitor())
        yield
        task.cancel()
        try:await task
        except asyncio.CancelledError:pass
    app.cleanup_ctx.append(lifecycle)
    async def remote(path,body=None,service='comfy',method=None):
        url=cfg[service+'_url'].rstrip('/')+path
        async with ClientSession(timeout=ClientTimeout(total=180)) as session:
            async with session.request(method or ('POST' if body is not None else 'GET'),url,json=body) as r:
                text=await r.text()
                try:data=json.loads(text)
                except ValueError:data={'error':text[:600]}
                if r.status>=400:raise ValueError(f'HTTP {r.status}: '+str(data)[:1200])
                return data
    async def info():return await remote('/object_info')
    async def idle():
        q=await remote('/queue')
        if q.get('queue_running') or q.get('queue_pending'):raise ValueError('ComfyUI 작업이 진행 중입니다. 완료 후 실행하세요.')
    KILL_KEYS=('comfy_models','isolated_workers','orphan_workers','ollama','node_cache','torch_cache')
    def kill_graph(schemas,ollama=True):
        """The Kill Switch as an unconnected node. ComfyUI runs ready output nodes first,
        so it clears memory before any loader in the same prompt runs."""
        opts=load('workspace.json',{}).get('kill_options') or {}
        if not opts.get('before_every_task',True) or 'MMH3_KillSwitch' not in schemas:return {}
        inputs=engine.defaults(schemas,'MMH3_KillSwitch');inputs['ollama_url']=cfg['ollama_url']
        inputs.update({k:opts[k] for k in KILL_KEYS if isinstance(opts.get(k),bool)})
        if not ollama:inputs['ollama']=False
        return {'studio_kill':{'class_type':'MMH3_KillSwitch','inputs':inputs}}
    async def kill_now():
        """Before Ollama: run the Kill Switch on its own and wait for it. Ollama stays
        loaded, since the model about to be called would only be reloaded."""
        g=kill_graph(await info(),ollama=False)
        if not g:
            await remote('/free',{'unload_models':True,'free_memory':True});return
        pid=(await remote('/prompt',{'prompt':g,'client_id':'mmh3-studio'}))['prompt_id']
        for _ in range(240):
            if (await remote('/history/'+pid)).get(pid):return
            await asyncio.sleep(.25)
        raise ValueError('Kill Switch가 60초 안에 끝나지 않았습니다.')
    @routes.get('/')
    async def home(r):return web.FileResponse(HERE/'web/index.html')
    @routes.get('/api/status')
    async def status(r):
        result={}
        for service,path in [('comfy','/system_stats'),('ollama','/api/tags')]:
            try:result[service]={'ok':True,'data':await remote(path,service=service)}
            except Exception as exc:result[service]={'ok':False,'error':str(exc)}
        return web.json_response(result)
    @routes.get('/api/catalog')
    async def catalog(r):
        out=await asyncio.to_thread(pack.catalog);schemas=await info()
        out['models']={key:schemas.get(cls,{}).get('input',{}).get('required',{}).get(field,[[]])[0] for key,cls,field in [('model','UNETLoader','unet_name'),('clip','CLIPLoader','clip_name'),('vae','VAELoader','vae_name'),('lora','LoraLoaderModelOnly','lora_name')]}
        out['advanced']={nid:{'class_type':n['class_type'],'values':{k:v for k,v in n['inputs'].items() if not engine.link(v)},'schema':schemas.get(n['class_type'],{}).get('input',{})} for nid,n in engine.template().items() if n['class_type'] not in ('MMH3_PromptFreeze','MiniMaxH3Director','DaSiWa_LTX2LoraLoader','PreviewAny','H3ContextSaveLatent','H3ContextLoadLatent','MMH3_AVLatentFromCheckpoint')}
        out['post']={key:{'schema':schemas[cls]['input'],'defaults':engine.defaults(schemas,cls)} for key,cls in [('resize','DaSiWa_TorchResize'),('rtx','DaSiWa_RTX_UpscalerRefiner'),('watermark','DaSiWa_Watermark'),('model_upscale','UpscaleModelLoader')] if cls in schemas}
        interp=schemas.get('FrameInterpolationModelLoader',{}).get('input',{}).get('required',{}).get('model_name',[[]])
        out['interpolation_models']=interp[1].get('options',[]) if interp[0]=='COMBO' else interp[0]
        return web.json_response(out)
    @routes.get('/api/state')
    async def state(r):return web.json_response(load('workspace.json',{}))
    @routes.post('/api/state')
    async def state_save(r):save('workspace.json',await r.json());return web.json_response({'ok':True})
    @routes.post('/api/upload')
    async def upload(r):
        reader=await r.multipart();part=await reader.next()
        if part is None or not part.filename:raise ValueError('파일을 선택하세요.')
        name=Path(part.filename).name;ext=Path(name).suffix.lower()
        kind='image' if ext in ('.png','.jpg','.jpeg','.webp') else 'audio' if ext in ('.wav','.mp3','.flac','.ogg','.m4a') else 'video' if ext in ('.mp4','.mov','.mkv','.webm') else ''
        if not kind:raise ValueError('지원하지 않는 미디어 형식입니다.')
        uploads=DATA/'uploads';uploads.mkdir(exist_ok=True);p=uploads/(uuid.uuid4().hex+ext)
        with p.open('wb') as f:
            while True:
                chunk=await part.read_chunk(1024*1024)
                if not chunk:break
                f.write(chunk)
        duration=1
        if kind=='image':
            from PIL import Image
            with Image.open(p) as im:im.verify()
        else:
            probe=await asyncio.to_thread(subprocess.run,['ffprobe','-v','error','-show_entries','format=duration:stream=codec_name,codec_type','-of','json',str(p)],capture_output=True,text=True,timeout=30)
            if probe.returncode:raise ValueError('읽을 수 없는 오디오/영상입니다: '+probe.stderr[:300])
            md=json.loads(probe.stdout);duration=float(md['format']['duration'])
            # Director uses its own loaders; normalize AV1 uploads before any expensive render.
            if any(s.get('codec_name')=='av1' for s in md.get('streams',[])):
                dst=p.with_suffix('.mp4')
                if dst==p:dst=p.with_name(p.stem+'_h264.mp4')
                proc=await asyncio.to_thread(subprocess.run,['ffmpeg','-v','error','-y','-i',str(p),'-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac',str(dst)],capture_output=True,timeout=600)
                if proc.returncode:raise ValueError('AV1 변환 실패');
                p=dst
        form=FormData()
        with p.open('rb') as f:
            form.add_field('image',f,filename=p.name,content_type=mimetypes.guess_type(p.name)[0] or 'application/octet-stream');form.add_field('subfolder','mmh3_studio');form.add_field('overwrite','false')
            async with ClientSession() as session:
                async with session.post(cfg['comfy_url']+'/upload/image',data=form) as resp:
                    if resp.status!=200:raise ValueError(await resp.text())
                    d=await resp.json()
        return web.json_response({'file':d.get('subfolder','')+'/'+d['name'],'name':name,'type':kind,'duration':duration,'enabled':True,'role':'character_full','start':0})
    @routes.get('/api/media')
    async def media(r):return web.FileResponse(safe_media(r.query['file'],r.query.get('folder','input')))
    @routes.post('/api/brief')
    async def brief(r):return web.json_response(await asyncio.to_thread(pack.brief,await r.json()))
    @routes.post('/api/prompt')
    async def prompt(r):
        b=await r.json()
        for ref in b.get('refs',[]):safe_media(ref['file'])
        if b.get('project') and b.get('chain',False):
            project=await remote('/h3_suite/project/state?'+urlencode({'name':b['project']}))
            b['continuation']=bool(project.get('chain_active'))
        else:b['continuation']=False
        async with lock:
            await idle();await kill_now()
            result=await asyncio.to_thread(pack.write,b,cfg['ollama_url'])
        return web.json_response(result)
    @routes.post('/api/freeze')
    async def freeze(r):
        async with lock:
            await idle();await kill_now()
            result=await asyncio.to_thread(pack.freeze,await r.json(),cfg['ollama_url'])
        return web.json_response(result)
    async def prepare(b):
        b.pop('_draft_project',None)
        if not b.get('project') and not b.get('chain'):
            b['_draft_project']=DRAFT_PREFIX+uuid.uuid4().hex
        schemas=await info()
        for ref in b.get('refs',[]):
            if not ref.get('enabled',True):continue
            path=safe_media(ref['file'])
            if ref.get('type','image')!='image':
                proc=await asyncio.to_thread(subprocess.run,['ffprobe','-v','error','-show_entries','format=duration:stream=codec_name,codec_type','-of','json',str(path)],capture_output=True,text=True,timeout=30)
                if proc.returncode:raise ValueError('참조 미디어를 읽을 수 없습니다: '+ref['file'])
                metadata=json.loads(proc.stdout);actual=float(metadata['format']['duration'])
                start=float(ref.get('trim_start') or 0);end=float(ref.get('trim_end') or actual)
                if not 0<=start<end<=actual+.05:raise ValueError('미디어 자르기 구간이 실제 길이를 벗어납니다: '+ref['file'])
                if any(x.get('codec_name')=='av1' for x in metadata.get('streams',[])):raise ValueError('AV1 영상은 Studio에서 다시 업로드해 H.264로 변환하세요.')
                ref['duration']=actual
        project_state=None
        # The Continuum engine keeps its own chunk store; Project Suite routes
        # are not part of that path and may not even be installed.
        suite=False
        if b.get('project') and suite:
            project_state=await remote('/h3_suite/project/state?'+urlencode({'name':b['project']}))
        b['_chain_active']=bool(b.get('chain') and project_state and project_state.get('chain_active'))
        approved=[c for c in (project_state or {}).get('clips',[]) if c.get('status')=='approved']
        # Clip order at submit time: a retry of the same clip overwrites its ledger entry.
        b['_clip_index']=len(approved) if b.get('project') else None
        tail_shape=approved[-1].get('meta',{}).get('latent_video',[]) if approved else []
        b['_tail_size']=[tail_shape[-1]*16,tail_shape[-2]*16] if tail_shape else []
        base_shape=approved[-1].get('meta',{}).get('base_latent_video',tail_shape) if approved else []
        b['_base_tail_size']=[base_shape[-1]*16,base_shape[-2]*16] if base_shape else []
        if str(b.get('engine','suite'))=='continuum':
            g,meta=continuum.build(b,schemas)
        else:
            g,meta=engine.build(b,schemas)
        g.update(kill_graph(schemas))
        problems=engine.validate(g,schemas)
        previous=load('last_graph.json',{})
        if b.get('project') and suite:
            try:
                project=await remote('/h3_suite/project/state?'+urlencode({'name':b['project']}))
                if project.get('pending') and not b.get('candidate_retry'):problems.append('후보 클립이 있습니다. 프로젝트에서 이 버전 사용 또는 다른 후보 만들기를 선택하세요.')
                if b.get('chain',False) and project.get('chain_active'):
                    approved=[c for c in project.get('clips',[]) if c.get('status')=='approved']
                    shape=approved[-1].get('meta',{}).get('latent_video',[]) if approved else []
                    # Previous final frames are resized/re-encoded at each target resolution.
                    if int(b.get('context_length',22))>=meta['frames']:problems.append('이어받을 프레임 수보다 생성 길이가 길어야 합니다.')
            except Exception as exc:problems.append('프로젝트를 먼저 생성하거나 선택하세요: '+str(exc))
        meta.update(errors=problems,changed=engine.changes(previous,g),fingerprint=engine.fingerprint(g))
        return g,meta
    @routes.post('/api/preflight')
    async def preflight(r):
        _,meta=await prepare(await r.json());return web.json_response(meta)
    @routes.post('/api/render')
    async def render(r):
        b=await r.json()
        async with lock:
            g,meta=await prepare(b)
            if meta['errors']:raise ValueError('\n'.join(meta['errors']))
            # Renders may queue: ComfyUI runs them one at a time and a waiting
            # prompt costs nothing. Unload Ollama only when nothing is rendering,
            # because a running job needs its VRAM left alone.
            queue=await remote('/queue')
            waiting=len(queue.get('queue_running',[]))+len(queue.get('queue_pending',[]))
            if not waiting:
                residents=await remote('/api/ps',service='ollama')
                for model in residents.get('models',[]):await remote('/api/generate',{'model':model['name'],'keep_alive':0},service='ollama')
            client='mmh3-studio'
            result=await remote('/prompt',{'prompt':g,'client_id':client})
            pid=result['prompt_id'];jobs[pid]={'id':pid,'created':time.time(),'state':'queued','settings':b,'meta':meta,'outputs':[],'waiting':waiting}
            save('jobs.json',jobs);save('last_graph.json',g)
        return web.json_response(jobs[pid])
    def job_video(pid):
        job=jobs.get(pid) or {}
        for o in job.get('outputs',[]):
            if str(o.get('filename','')).lower().endswith(('.mp4','.webm','.mov')):
                folder=o.get('type','output')
                name=(o.get('subfolder','')+'/'+o['filename']) if o.get('subfolder') else o['filename']
                try:return safe_media(name,folder)
                except Exception:continue
        return None

    def grab_frames(pid):
        """First and last frame of a finished render, cached beside the job list."""
        video=job_video(pid)
        if video is None:raise ValueError('이 작업에는 영상 결과가 없습니다.')
        out=DATA/'frames';out.mkdir(exist_ok=True);made={}
        for which,args in (('first',['-i',str(video),'-frames:v','1']),
                           ('last',['-sseof','-1','-i',str(video),'-update','1'])):
            target=out/('%s_%s.jpg'%(pid,which))
            if not target.is_file() or target.stat().st_mtime<video.stat().st_mtime:
                run=subprocess.run(['ffmpeg','-v','error','-nostdin','-y',*args,'-q:v','3',str(target)],
                                   capture_output=True,text=True,timeout=180)
                if run.returncode or not target.is_file():
                    raise ValueError('프레임 추출 실패: '+run.stderr[-300:])
            made[which]=target
        return made

    @routes.get('/api/job/frames')
    async def job_frames(r):
        pid=r.query['id']
        if pid not in jobs:raise web.HTTPNotFound()
        made=await asyncio.to_thread(grab_frames,pid)
        return web.json_response({k:'/api/job/frame?'+urlencode({'id':pid,'which':k,'t':int(v.stat().st_mtime)})
                                  for k,v in made.items()})

    @routes.get('/api/job/frame')
    async def job_frame(r):
        pid=r.query['id'];which=r.query.get('which','first')
        if pid not in jobs or which not in ('first','last'):raise web.HTTPNotFound()
        path=DATA/'frames'/('%s_%s.jpg'%(pid,which))
        if not path.is_file():await asyncio.to_thread(grab_frames,pid)
        return web.FileResponse(path)

    def frame_label(pid,which):
        return ('첫 프레임' if which=='first' else '마지막 프레임')+' · '+time.strftime('%m-%d %H:%M',time.localtime(jobs[pid].get('created',0)))
    @routes.get('/api/job/frame/anchor')
    async def color_anchor(r):return web.json_response(load('color_anchor.json',{}))
    @routes.post('/api/job/frame/anchor')
    async def color_anchor_set(r):
        """Remember one frame's scene colour, the target that later frames are corrected toward."""
        b=await r.json();pid=b.get('id');which=b.get('which','first')
        if pid not in jobs or which not in ('first','last'):raise ValueError('작업을 찾을 수 없습니다.')
        made=await asyncio.to_thread(grab_frames,pid)
        stats=await asyncio.to_thread(lambda:frame_color.stats(made[which]))
        anchor={'label':frame_label(pid,which),'job':pid,'which':which,'stats':stats}
        save('color_anchor.json',anchor);return web.json_response(anchor)
    @routes.post('/api/job/frame/adopt')
    async def job_frame_adopt(r):
        """Copy one saved frame into ComfyUI's input folder so it can be reused.

        With `correct`, the frame's brightness and saturation are first pulled toward the
        colour anchor with MAINodes' ColorCarry transform and the result is kept as PNG."""
        b=await r.json();pid=b.get('id');which=b.get('which','first')
        if pid not in jobs or which not in ('first','last'):raise ValueError('작업을 찾을 수 없습니다.')
        made=await asyncio.to_thread(grab_frames,pid)
        source=made[which];label=frame_label(pid,which);note=''
        target=pack.COMFY/'input/mmh3_studio'/(uuid.uuid4().hex+('.png' if b.get('correct') else '.jpg'))
        target.parent.mkdir(parents=True,exist_ok=True)
        if b.get('correct'):
            anchor=load('color_anchor.json',{})
            if not anchor.get('stats'):raise ValueError('먼저 색 기준이 될 프레임을 지정하세요. (프레임 메뉴 5번)')
            brightness,saturation=await asyncio.to_thread(frame_color.correct,source,target,anchor['stats'],b.get('color') or {})
            label+=' · 색 보정';note='밝기 %+.1f · 채도 ×%.3f (기준: %s)'%(brightness*255,saturation,anchor['label'])
        else:await asyncio.to_thread(shutil.copy2,source,target)
        return web.json_response({'file':'mmh3_studio/'+target.name,'name':label,'type':'image',
                                  'duration':1,'start':0,'enabled':True,'role':'','purpose':'','note':note})

    @routes.get('/api/preview')
    async def preview_frame(r):
        if not preview['image'] or time.time()-preview['at']>1800:raise web.HTTPNoContent()
        return web.Response(body=preview['image'],content_type=preview['type'],
                            headers={'Cache-Control':'no-store','X-Job':preview['job'],
                                     'X-At':repr(preview['at']),
                                     'X-Age':str(int(time.time()-preview['at']))})
    @routes.get('/api/jobs')
    async def job_list(r):
        if r.query.get('view') == 'production':
            return web.json_response(production_jobs(jobs.values()))
        return web.json_response([j for j in list(jobs.values())[::-1] if not j.get('deleted')])
    @routes.get('/api/jobs/{pid}')
    async def job(r):
        pid=r.match_info['pid']
        if pid not in jobs or jobs[pid].get('deleted'):raise web.HTTPNotFound()
        j=jobs[pid]
        if j.get('state') in ('cancelled','completed','failed'):return web.json_response(j)
        h=(await remote('/history/'+pid)).get(pid)
        if h:
            status=h.get('status',{});j['state']='failed' if status.get('status_str')=='error' else 'completed' if status.get('completed') else 'running'
            j['errors']=[p.get('exception_message',k) for k,p in status.get('messages',[]) if k in ('execution_error','execution_interrupted')]
            j['outputs']=[];seen=set()
            for nid,out in h.get('outputs',{}).items():
                for key in ('images','gifs','videos','audio'):
                    for item in out.get(key,[]):
                        if isinstance(item,dict) and item.get('filename'):
                            identity=(item.get('type','output'),item.get('subfolder',''),item['filename'])
                            if identity in seen:continue
                            seen.add(identity)
                            item={**item,'node':nid};item['url']='/api/output?'+urlencode({k:item.get(k,'') for k in ('filename','subfolder','type')});j['outputs'].append(item)
            save('jobs.json',jobs)
        else:
            q=await remote('/queue');running=[str(x[1]) for x in q.get('queue_running',[])];pending=[str(x[1]) for x in q.get('queue_pending',[])]
            j['state']='running' if pid in running else 'queued' if pid in pending else 'unknown'
        return web.json_response(j)
    @routes.post('/api/jobs/{pid}/cancel')
    async def cancel(r):
        pid=r.match_info['pid']
        if pid not in jobs:raise web.HTTPNotFound()
        q=await remote('/queue')
        if any(str(x[1])==pid for x in q.get('queue_running',[])):await remote('/interrupt',{})
        else:await remote('/queue',{'delete':[pid]})
        jobs[pid]['state']='cancelled';save('jobs.json',jobs);return web.json_response({'ok':True})
    @routes.get('/api/output')
    async def output(r):
        folder=r.query.get('type','output')
        if folder not in ('output','temp','input'):raise ValueError('허용되지 않는 경로')
        return web.FileResponse(safe_media(r.query.get('subfolder','')+'/'+r.query['filename'] if r.query.get('subfolder') else r.query['filename'],folder))
    @routes.get('/api/trash')
    async def trash_list(r):return web.json_response({'items':trash.list()})
    @routes.post('/api/trash/restore')
    async def trash_restore(r):
        body=await r.json()
        async with lock:
            data=await asyncio.to_thread(trash.restore,body['id'])
            pid=data.get('payload',{}).get('job_id')
            if pid in jobs:jobs[pid].pop('deleted',None);save('jobs.json',jobs)
        return web.json_response({'ok':True})
    @routes.post('/api/delete/asset')
    async def delete_asset(r):
        body=await r.json()
        async with lock:
            a,path=assets.get(body['project'],body['id'])
            result=trash.remove(a['name'],'asset',[path.parent])
        return web.json_response(result)
    @routes.post('/api/delete/asset-project')
    async def delete_asset_project(r):
        body=await r.json()
        async with lock:
            path=assets.project(body['project']);meta=assets.read(path/'project.json')
            result=trash.remove(meta['name'],'asset-project',[path])
        return web.json_response(result)
    @routes.post('/api/delete/project')
    async def delete_project(r):
        body=await r.json()
        async with lock:
            await idle();p=project_core(pack.COMFY).Project(str(pack.COMFY/'output'),body['name'])
            patches=[]
            for file in ('project_saved_videos.json','timeline_edits.json'):
                data=load(file,{})
                if body['name'] in data:
                    data.pop(body['name']);patches.append((DATA/file,json.dumps(data,ensure_ascii=False,indent=2)))
            result=trash.remove(body['name'],'project',[p.root],patches)
        return web.json_response(result)
    @routes.post('/api/delete/clip')
    async def remove_clip(r):
        body=await r.json()
        async with lock:
            await idle();p=project_core(pack.COMFY).Project(str(pack.COMFY/'output'),body['name'])
            result=delete_clip(trash,p,body['index'],body.get('take'))
        return web.json_response(result)
    @routes.post('/api/delete/job')
    async def delete_job(r):
        body=await r.json();pid=body['id']
        # A finished job's files are independent of whatever ComfyUI is rendering now,
        # and files another job also lists are kept below, so no idle check is needed.
        async with lock:
            if pid not in jobs or jobs[pid].get('deleted'):raise ValueError('생성 결과가 없습니다.')
            j=jobs[pid]
            if j['state'] not in ('completed','failed','cancelled'):raise ValueError('진행 중인 작업은 먼저 취소하세요.')
            output=(pack.COMFY/'output').resolve();paths=[]
            def output_path(o):
                if o.get('type','output')!='output':return None
                p=(output/o.get('subfolder','')/o['filename']).resolve()
                if not p.is_relative_to(output):raise ValueError('출력 경로가 잘못되었습니다.')
                return p
            shared={output_path(o) for other in jobs.values() if other['id']!=pid for o in other.get('outputs',[])}
            for o in j.get('outputs',[]):
                p=output_path(o)
                # Project copies have their own explicit deletion controls.
                if p and p not in shared and not p.is_relative_to(output/'h3_projects'):paths.append(p)
            draft=j.get('settings',{}).get('_draft_project')
            if draft and draft.startswith(DRAFT_PREFIX):
                try:paths.append(Path(project_core(pack.COMFY).Project(str(output),draft).root))
                except Exception:pass
            result=trash.remove('생성 결과 '+pid[:8],'job',paths,payload={'job_id':pid})
            j['deleted']=result['id'];save('jobs.json',jobs)
        return web.json_response(result)
    @routes.post('/api/delete/saved-video')
    async def delete_saved_video(r):
        body=await r.json()
        async with lock:
            await idle();saved=load('project_saved_videos.json',{});items=saved.get(body['name'],[])
            item=next((v for v in items if v['job_id']==body['id']),None)
            if not item:raise ValueError('보관 영상이 없습니다.')
            p=project_core(pack.COMFY).Project(str(pack.COMFY/'output'),body['name'])
            path=(pack.COMFY/'output'/item['file']).resolve()
            if not path.is_relative_to(Path(p.root).resolve()/'studio_imports'):raise ValueError('보관 경로가 잘못되었습니다.')
            saved[body['name']]=[v for v in items if v['job_id']!=body['id']]
            result=trash.remove(item['label'],'saved-video',[path],[(DATA/'project_saved_videos.json',json.dumps(saved,ensure_ascii=False,indent=2))])
        return web.json_response(result)
    @routes.post('/api/delete/export')
    async def delete_export(r):
        body=await r.json()
        async with lock:
            p=project_core(pack.COMFY).Project(str(pack.COMFY/'output'),body['name'])
            filename=body['filename']
            if not isinstance(filename,str) or Path(filename).name!=filename or not filename.startswith('edit_') or not filename.endswith('.mp4'):raise ValueError('잘못된 내보내기 파일')
            path=Path(p.root)/'studio_exports'/filename
            if not path.is_file():raise ValueError('저장 영상이 없습니다.')
            result=trash.remove(body['name']+' · 연결 영상','export',[path])
        return web.json_response(result)
    @routes.get('/api/projects')
    async def projects(r):
        data=await remote('/h3_suite/projects')
        data['projects']=[p for p in data.get('projects',[]) if not (p if isinstance(p,str) else p.get('name',p.get('project_name',''))).startswith(DRAFT_PREFIX)]
        return web.json_response(data)
    @routes.get('/api/project')
    async def project(r):
        name=r.query['name'];data=await remote('/h3_suite/project/state?'+urlencode({'name':name}))
        data['edits']=load('timeline_edits.json',{}).get(name,{})
        project_root=Path(project_core(pack.COMFY).Project(str(pack.COMFY/'output'),name).root)
        data['exports']=[{'filename':p.name,'url':'/api/output?'+urlencode({'filename':p.name,'subfolder':str(p.parent.relative_to(pack.COMFY/'output')),'type':'output'})} for p in sorted((project_root/'studio_exports').glob('edit_*.mp4'))]
        saved=load('project_saved_videos.json',{}).get(name,[])
        data['saved_videos']=[{**v,'url':'/api/output?'+urlencode({'filename':Path(v['file']).name,'subfolder':str(Path(v['file']).parent),'type':'output'})} for v in saved]
        return web.json_response(data)
    @routes.post('/api/timeline/trim')
    async def timeline_trim(r):
        body=await r.json()
        async with lock:
            p=project_core(pack.COMFY).Project(str(pack.COMFY/'output'),body['name'])
            meta=await asyncio.to_thread(timeline.probe,timeline.clip_path(p,body['basename']))
            cut=timeline.interval(body.get('start'),body.get('end'),meta['duration'])
            edits=load('timeline_edits.json',{});edits.setdefault(body['name'],{})[body['basename']]=cut
            save('timeline_edits.json',edits)
        return web.json_response(cut)
    @routes.post('/api/timeline/use')
    async def timeline_use(r):
        body=await r.json()
        async with lock:
            await idle()
            p=project_core(pack.COMFY).Project(str(pack.COMFY/'output'),body['name'])
            pending=p.pending()
            if not pending or pending['index']!=int(body['index']):raise ValueError('후보 상태가 바뀌었습니다. 새로고침하세요.')
            p.select_take(int(body['index']),int(body['take']));p.approve()
        return web.json_response({'name':body['name']})
    @routes.post('/api/timeline/export')
    async def timeline_export(r):
        body=await r.json();name=body['name']
        async with lock:
            p=project_core(pack.COMFY).Project(str(pack.COMFY/'output'),name)
            target=await asyncio.to_thread(timeline.export,p,load('timeline_edits.json',{}).get(name,{}))
        root=(pack.COMFY/'output').resolve()
        return web.json_response({'name':name,'master_url':'/api/output?'+urlencode({'filename':target.name,'subfolder':str(target.parent.relative_to(root)),'type':'output'})})
    @routes.post('/api/timeline/retry')
    async def timeline_retry(r):
        body=await r.json();new_name=body['name']+'-v'+uuid.uuid4().hex[:8]
        async with lock:
            await idle()
            module=project_core(pack.COMFY)
            p=await asyncio.to_thread(module.branch_project,str(pack.COMFY/'output'),body['name'],int(body['index']),new_name)
            p.reopen(int(body['index']))
            edits=load('timeline_edits.json',{});edits[new_name]=dict(edits.get(body['name'],{}));save('timeline_edits.json',edits)
        return web.json_response({'name':new_name,'chain_active':p.chain_active()})
    @routes.post('/api/timeline/preview')
    async def timeline_preview(r):
        body=await r.json();name=body['name']
        async with lock:
            p=project_core(pack.COMFY).Project(str(pack.COMFY/'output'),name)
            index=int(body['index']);entry=next(c for c in p.clips if c['index']==index)
            chosen=next(t for t in p.takes_of(index) if t['take']==int(body['take']))
            previous=[c for c in p.approved() if c['index']==index-1]
            if not previous:raise ValueError('앞에 선택한 클립이 없습니다.')
            target=await asyncio.to_thread(timeline.export,p,load('timeline_edits.json',{}).get(name,{}),previous+[chosen],True)
        root=(pack.COMFY/'output').resolve()
        return web.json_response({'url':'/api/output?'+urlencode({'filename':target.name,'subfolder':str(target.parent.relative_to(root)),'type':'output'})})
    @routes.post('/api/inbox/save')
    async def inbox_save(r):
        body=await r.json();pid=body.get('job_id');name=str(body.get('name','')).strip()
        if pid not in jobs:raise ValueError('영상 작업을 찾을 수 없습니다.')
        async with lock:
            await idle()
            j=jobs[pid]
            if j.get('saved_project'):
                if j['saved_project']['name']==name:return web.json_response(j['saved_project'])
            if j.get('settings',{}).get('project')==name:return web.json_response({'name':name,'kind':'clip'})
            result=await asyncio.to_thread(adopt,pack.COMFY,j,name)
            if result['kind']=='clip':
                project=project_core(pack.COMFY).Project(str(pack.COMFY/'output'),name)
                if project.pending():project.approve()
            if result['kind']=='video':
                saved=load('project_saved_videos.json',{});items=saved.setdefault(name,[])
                if not any(v.get('job_id')==pid for v in items):items.append(result)
                save('project_saved_videos.json',saved)
            j['saved_project']=result;save('jobs.json',jobs)
            return web.json_response(result)
    @routes.post('/api/project/{action}')
    async def project_action(r):
        action=r.match_info['action']
        if action not in ('create','approve','reject','reopen','select_take','export','branch'):raise ValueError('허용되지 않는 작업')
        async with lock:
            await idle()
            data=await remote('/h3_suite/project/'+action,await r.json())
            if data.get('master'):
                root=(pack.COMFY/'output').resolve();master=Path(data['master']).resolve()
                if master.is_relative_to(root):data['master_url']='/api/output?'+urlencode({'filename':master.name,'subfolder':str(master.parent.relative_to(root)),'type':'output'})
            return web.json_response(data)
    @routes.get('/api/project/video')
    async def project_video(r):
        # Stream through ComfyUI so its project/path validation stays authoritative.
        url=cfg['comfy_url']+'/h3_suite/project/video?'+urlencode(dict(r.query))
        async with ClientSession() as session:
            async with session.get(url,headers={'Range':r.headers['Range']} if 'Range' in r.headers else {}) as resp:
                result=web.StreamResponse(status=resp.status,headers={k:v for k,v in resp.headers.items() if k.lower() in ('content-type','content-length','content-range','accept-ranges')})
                await result.prepare(r)
                async for chunk in resp.content.iter_chunked(262144):await result.write(chunk)
                return result
    @routes.get('/api/asset-projects')
    async def asset_projects(r):return web.json_response({'projects':assets.projects()})
    @routes.post('/api/asset-projects')
    async def asset_create(r):return web.json_response(assets.create((await r.json()).get('name','')))
    @routes.get('/api/asset-media')
    async def asset_media(r):
        _,path=assets.get(r.query['project'],r.query['id'])
        return web.FileResponse(path)
    @routes.post('/api/library/import')
    async def asset_import(r):
        from studio_pack.mmh3 import library
        library.root=lambda:str(pack.COMFY/'output/mmh3_library')
        b=await r.json()
        if b.get('kind') not in library.KINDS or not library._ID_RE.fullmatch(b.get('id','')):raise ValueError('잘못된 에셋입니다.')
        a=library.load(b['kind'],b['id']);_,fname=library.pick_file(a);path=Path(library.file_path(a,fname))
        kind='audio' if path.suffix.lower() in ('.wav','.mp3','.flac','.ogg','.m4a') else 'video' if path.suffix.lower() in ('.mp4','.mov','.mkv','.webm') else 'image'
        role={'actors':'character_full','costumes':'outfit','scenes':'background','props':'prop'}.get(b['kind'],'')
        return web.json_response(assets.store(b['project'],path,{'name':a.get('name',a['id']),'type':kind,'role':role,'purpose':library.description(a)}))
    @routes.get('/api/library')
    async def library_list(r):
        if r.query.get("project"):return web.json_response({"items":assets.items(r.query["project"])})
        from studio_pack.mmh3 import library
        library.root=lambda:str(pack.COMFY/'output/mmh3_library')
        return web.json_response({'kinds':list(library.KINDS),'items':[a for k in library.KINDS for a in library.list_assets(k)]})
    @routes.post('/api/library')
    async def library_save(r):
        from studio_pack.mmh3 import library
        library.root=lambda:str(pack.COMFY/'output/mmh3_library')
        b=await r.json();p=safe_media(b['file'])
        if b.get('project'):
            from studio_pack.mmh3 import shotcards
            b['role_label']=next((row[1] for row in shotcards.REF_ROLE if row[0]==b.get('role')),b.get('type','image'))
            return web.json_response(assets.store(b['project'],p,b))
        if b['kind'] not in library.KINDS:raise ValueError('에셋 종류를 선택하세요.')
        asset,_,_=library.save(b['kind'],b['name'],{'master':(p.suffix,p.read_bytes())},description_en=b.get('description',''))
        return web.json_response(asset)
    @routes.post('/api/library/use')
    async def library_use(r):
        body=await r.json()
        if body.get('project'):return web.json_response(assets.use(body['project'],body['id'],pack.COMFY/'input'))
        from studio_pack.mmh3 import library
        library.root=lambda:str(pack.COMFY/'output/mmh3_library')
        b=await r.json()
        if b.get('kind') not in library.KINDS or not library._ID_RE.fullmatch(b.get('id','')):raise ValueError('잘못된 에셋입니다.')
        a=library.load(b['kind'],b['id']);_,fname=library.pick_file(a)
        p=Path(library.file_path(a,fname));form=FormData()
        with p.open('rb') as f:
            form.add_field('image',f,filename=uuid.uuid4().hex+p.suffix);form.add_field('subfolder','mmh3_studio')
            async with ClientSession() as session:
                async with session.post(cfg['comfy_url']+'/upload/image',data=form) as resp:
                    if resp.status!=200:raise ValueError(await resp.text())
                    d=await resp.json()
        return web.json_response({'file':d.get('subfolder','')+'/'+d['name'],'name':a.get('name',a['id']),'type':'image','duration':1,'start':0,'enabled':True,'role':'character_full','purpose':library.description(a)})
    import studio_chat
    studio_chat.install(routes,DATA,cfg,remote,idle,pack,kill_now)
    from batch_runner import install
    batch_busy=install(app,routes,pack,assets,load,save,prompt,render,job,cancel,remote,idle,prepare)
    finish_busy=lambda:False
    @routes.post('/api/app/restart')
    async def app_restart(r):
        """Relaunch this server; a helper waits for the port to free first."""
        helper=DATA/'restart.cmd'
        script=['@echo off','ping -n 4 127.0.0.1 >nul',
                'start "" "%s" "%s" --no-browser' % (sys.executable, str(HERE/'server.py'))]
        helper.write_text('\r\n'.join(script)+'\r\n',encoding='utf-8')
        async def bye():
            await asyncio.sleep(0.4)
            subprocess.Popen(['cmd','/c',str(helper)],cwd=str(HERE),
                             creationflags=getattr(subprocess,'CREATE_NEW_CONSOLE',0))
            os._exit(0)
        asyncio.create_task(bye())
        return web.json_response({'restarting':True})

    @routes.post('/api/app/quit')
    async def app_quit(r):
        async def bye():
            await asyncio.sleep(0.4);os._exit(0)
        asyncio.create_task(bye())
        return web.json_response({'stopping':True})

    @routes.post('/api/kill-switch')
    async def kill_switch(r):
        requested=await r.json()
        if batch_busy():raise ValueError('먼저 폴더 순차 생성을 중지하세요.')
        if finish_busy():raise ValueError('먼저 고화질 마감을 중지하세요.')
        async with lock:
            await idle();schemas=await info()
            cls='MMH3_KillSwitch'
            if cls not in schemas:raise ValueError('설치된 Kill Switch 노드를 찾을 수 없습니다.')
            inputs=engine.defaults(schemas,cls);inputs['ollama_url']=cfg['ollama_url']
            inputs['node_cache']=False
            for key in ('comfy_models','isolated_workers','orphan_workers','ollama','node_cache','torch_cache'):
                if key in requested:
                    if not isinstance(requested[key],bool):raise ValueError(key+'는 ON/OFF 값이어야 합니다.')
                    inputs[key]=requested[key]
            graph={'studio_kill':{'class_type':cls,'inputs':inputs}}
            errors=engine.validate(graph,schemas)
            if errors:raise ValueError('\n'.join(errors))
            result=await remote('/prompt',{'prompt':graph,'client_id':'mmh3-studio'});pid=result['prompt_id']
            jobs[pid]={'id':pid,'created':time.time(),'state':'queued','settings':{'maintenance':'Kill Switch'},'outputs':[]}
            save('jobs.json',jobs)
        return web.json_response(jobs[pid])
    import reference_studio
    reference_studio.install(routes,comfy=pack.COMFY,assets=assets,load=load,save=save,remote=remote,info=info,jobs=jobs,job=job,lock=lock,safe_media=safe_media,validate=engine.validate,kill=kill_graph)
    app.add_routes(routes);app.router.add_static('/web/',HERE/'web')
    return app

if __name__=='__main__':
    import argparse
    ap=argparse.ArgumentParser();ap.add_argument('--port',type=int,default=8791);ap.add_argument('--no-browser',action='store_true');args=ap.parse_args()
    web.run_app(build_app(),host='127.0.0.1',port=args.port,print=print)
