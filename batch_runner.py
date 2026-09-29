"""Sequential folder jobs reuse Studio's writer and render paths."""
import asyncio,copy,json,re,shutil,uuid
from pathlib import Path
from aiohttp import web

def scan(folder):
    root=Path(str(folder).strip()).expanduser().resolve()
    if not str(folder).strip() or not root.is_dir():raise ValueError('이미지 폴더 경로를 확인하세요.')
    files=[p for p in root.iterdir() if p.is_file() and p.suffix.lower() in ('.png','.jpg','.jpeg','.webp') and p.resolve().is_relative_to(root)]
    def natural(p):return [int(x) if x.isdigit() else x.casefold() for x in re.split(r'(\d+)',p.name)]
    files.sort(key=natural)
    if not files:raise ValueError('폴더에 지원하는 이미지가 없습니다.')
    return files

class JsonBody:
    def __init__(self,body=None,pid=None):self.body=body;self.match_info={'pid':pid}
    async def json(self):return copy.deepcopy(self.body)

def unpack(response):return json.loads(response.body)

def install(app,routes,pack,assets,load,save,prompt,render,job,cancel,remote,idle,prepare=None):
    state=load('batch.json',{'state':'idle'})
    if state.get('state') in ('running','writing','rendering','waiting_approval','stopping'):
        state.update(state='interrupted',error='서버가 재시작되어 순차 생성을 중단했습니다. 작업 기록을 확인하세요.')
    task=None;stop=False
    def update(**kw):state.update(kw);save('batch.json',state)
    async def runner(body,files):
        nonlocal stop
        try:
            for index,src in enumerate(files):
                if stop:break
                cfg=copy.deepcopy(body)
                if cfg.get('project'):
                    from urllib.parse import urlencode
                    while not stop:
                        proj=await remote('/h3_suite/project/state?'+urlencode({'name':cfg['project']}))
                        if not proj.get('pending'):break
                        update(state='waiting_approval',current=src.name)
                        await asyncio.sleep(2)
                if stop:break
                await idle()
                from PIL import Image
                with Image.open(src) as im:
                    w,h=im.size;im.verify()
                dst=pack.COMFY/'input/mmh3_studio'/(uuid.uuid4().hex+src.suffix.lower());dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dst)
                refs=cfg.setdefault('refs',[]);first=next((i for i,r in enumerate(refs) if r.get('type','image')=='image' and r.get('enabled',True)),None)
                new={**(refs[first] if first is not None else {'role':'first_frame'}),'type':'image','enabled':True,'name':src.name,'file':'mmh3_studio/'+dst.name,'start':0,'duration':1}
                if first is None:refs.insert(0,new)
                else:refs[first]=new
                if cfg.get('resolution_mode')=='preset' and cfg.get('aspect')=='auto':
                    pixels=float(cfg.get('preset_megapixels',.52))*1024*1024
                    height=(pixels/(w/h))**.5
                    cfg['width']=max(32,int(height*w/h/32+.5)*32);cfg['height']=max(32,int(height/32+.5)*32)
                active=[r for r in refs if r.get('enabled',True) and r.get('type','image')=='image']
                mapped=[{'n':i+1,'role':r.get('role',''),'target':r.get('target',''),'shots':[int(x) for x in str(r.get('scope','')).split(',') if x.strip().isdigit()]} for i,r in enumerate(active)]
                if prepare:
                    _,meta=await prepare(cfg)
                    if meta['errors']:raise ValueError('\n'.join(meta['errors']))
                brief=await asyncio.to_thread(pack.brief,{**cfg,'refs':mapped})
                counts={};notes=[]
                for ref in refs:
                    if not ref.get('enabled',True):continue
                    kind=ref.get('type','image');counts[kind]=counts.get(kind,0)+1
                    if ref.get('purpose'):notes.append(f"{dict(image='Picture',audio='Audio',video='Video')[kind]} {counts[kind]}: {ref['purpose']}")
                extra='\n'.join(notes)
                update(state='writing',current=src.name,index=index,prompt_id=None)
                result=unpack(await prompt(JsonBody({**cfg,**brief,'brief':brief['brief']+('\n'+extra if extra else '')})))
                if stop:break
                cfg['prompt']=result['prompt']
                queued=unpack(await render(JsonBody(cfg)));pid=queued['id'];update(state='rendering',prompt_id=pid)
                if stop:
                    await cancel(JsonBody(pid=pid));break
                while not stop:
                    status=unpack(await job(JsonBody(pid=pid)))
                    if status['state']=='completed':break
                    if status['state'] in ('failed','cancelled','unknown'):raise ValueError('영상 생성 중단: '+'; '.join(status.get('errors',[])))
                    await asyncio.sleep(2)
                if stop:break
                update(completed=index+1,prompt_id=None)
            update(state='stopped' if stop else 'completed',prompt_id=None)
        except asyncio.CancelledError:
            update(state='interrupted');raise
        except Exception as exc:update(state='failed',error=str(exc))
    @routes.get('/api/batch')
    async def status(r):return web.json_response(state)
    @routes.post('/api/batch/scan')
    async def preview(r):return web.json_response({'files':[{'name':p.name} for p in scan((await r.json()).get('folder',''))]})
    @routes.post('/api/batch/start')
    async def start(r):
        nonlocal task,stop
        if task and not task.done():raise ValueError('이미 순차 생성 중입니다.')
        body=await r.json();files=scan(body.get('folder',''))
        if not body.get('writer',{}).get('model'):raise ValueError('Ollama 모델을 선택하세요.')
        await idle();stop=False
        state.clear();update(state='running',total=len(files),completed=0,current='',error='')
        task=asyncio.create_task(runner(body,files));return web.json_response(state)
    @routes.post('/api/batch/stop')
    async def halt(r):
        nonlocal stop
        stop=True
        if task and not task.done():
            update(state='stopping')
            if state.get('prompt_id'):await cancel(JsonBody(pid=state['prompt_id']))
        return web.json_response(state)
    async def cleanup(app):
        if task and not task.done():
            task.cancel()
            try:await task
            except asyncio.CancelledError:pass
    app.on_cleanup.append(cleanup)
    return lambda:bool(task and not task.done())
