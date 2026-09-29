"""Use the installed node implementations without importing the ComfyUI node registry."""
import importlib
import inspect
import json
import os
import sys
import types
from pathlib import Path

import act_parts

# install.cmd writes MMH3_COMFY into studio_env.cmd; the fallback is the portable build
# sitting next to the Studio folder.
COMFY = Path(os.environ.get('MMH3_COMFY') or Path(__file__).resolve().parent.parent/'ComfyUI_windows_portable_nvidia/ComfyUI_windows_portable/ComfyUI')
PACK = COMFY/'custom_nodes/ComfyUI-MinimaxH3-PromptDirector'
for name, path in [('studio_pack', PACK), ('studio_pack.nodes', PACK/'nodes')]:
    module = types.ModuleType(name); module.__path__ = [str(path)]; sys.modules[name] = module

# Needs the studio_pack registration above.
import director_overrides
for where in director_overrides.apply():
    print('[MMH3 Studio] 가이드라인 수정 건너뜀 (팩 원문이 바뀜): '+where)

def node(name):
    return importlib.import_module('studio_pack.nodes.'+name)

def defaults(cls):
    out = {}
    for group in ('required','optional'):
        for key, spec in cls.INPUT_TYPES().get(group,{}).items():
            config = spec[1] if len(spec)>1 else {}
            if 'default' in config: out[key] = config['default']
            elif isinstance(spec[0], (list,tuple)) and spec[0]: out[key] = spec[0][0]
            elif spec[0]=='COMBO' and config.get('options'):out[key]=config['options'][0]
    return out

def num(value, default=0.0):
    """Empty widgets arrive as '' or None; treat them as the default."""
    try:
        if value is None or value == "": return float(default)
        return float(value)
    except (TypeError, ValueError):
        return float(default)

def catalog():
    from studio_pack.mmh3 import shotcards as s, acts
    fields = {k: getattr(s,v) for k,v in {'size':'SIZE','angle':'ANGLE','viewpoint':'VIEWPOINT','facing':'FACING','motion':'MOTION','speed':'SPEED','amp':'AMPLITUDE','transition':'TRANSITION','shot_type':'SHOT_TYPE'}.items()}
    settings = node('shot_settings').MMH3_ShotSettings
    # Return the existing library verbatim; no second set of action descriptions.
    return {'fields':fields, 'settings_schema':settings.INPUT_TYPES(), 'settings_defaults':defaults(settings),
            'links':getattr(s,'SHOT_LINK_LABELS',[]), 'ref_roles':s.REF_ROLE,
            'acts':getattr(acts,'ACTS',{}), 'act_positions':acts.POSITION, 'movers':acts.MOVER,
            'writer_schema':node('prompt_writer').MMH3_OllamaPromptWriter.INPUT_TYPES(),
            'act_parts':{key:{'parts':act_parts.checklist(key),'named':any(s['kind']=='name' for s in segs)}
                         for key,segs in act_parts.ACT_PARTS.items()},
            'part_labels':act_parts.PARTS}

def brief(body):
    cards=body.get('cards',[])
    settings=body.get('settings',{})
    focus=[]
    if str(settings.get('depth_of_field','')).startswith('rack'):
        for i,c in enumerate(cards):
            start=str(c.get('focus_from','')).strip();end=str(c.get('focus_to','')).strip()
            if not start or not end:raise ValueError(f'샷 {i+1}: 포커스 이동의 시작 대상과 도착 대상을 입력하세요.')
            at=float(c.get('focus_at') or 0);duration=float(c.get('focus_duration') or 1)
            shot_start=float(c.get('at') or 0) if i else 0
            shot_end=num(cards[i+1].get('at')) if i+1<len(cards) else num(body.get('duration'))
            if at<0 or duration<=0 or (shot_end>shot_start and at+duration>shot_end-shot_start):
                raise ValueError(f'샷 {i+1}: 포커스 이동 시간이 샷 길이를 벗어납니다.')
            focus.append(f'[샷 {i+1}] 초점은 {start}에서 {end}(으)로 이동한다. 샷 시작 후 {at:g}초부터 {duration:g}초 동안 이동한다. 초점 변화만으로 카메라나 인물을 이동시키지 않는다.')
    shots={'shots':cards, 'refs':body.get('refs',[])}
    values=node('shot_builder').MMH3_ShotBuilder().run(json.dumps(shots,ensure_ascii=False),json.dumps(body.get('settings',{}),ensure_ascii=False))
    result=dict(zip(('brief','spec','report'),values))
    if focus:result['brief']+='\n포커스 이동 지정:\n'+'\n'.join(focus)
    return result

def write(body,ollama_url):
    cls=node('prompt_writer').MMH3_OllamaPromptWriter
    kw=defaults(cls); kw.update(body.get('writer',{}))
    kw.update(brief=body['brief'],spec=body.get('spec',''), mode=body.get('mode','REF2VA'),duration=num(body.get('duration'),5),
              shot_count=len(body.get('cards',[])),link_to_director=False,ollama_url=ollama_url,keep_alive='0',unload_after=True,
              continuation=bool(body.get('continuation')))
    notes=continuum_clip(body,kw)
    items=[]
    for i,r in enumerate(body.get('refs',[])):
        if not r.get('enabled',True): continue
        items.append({'type':r.get('type','image'),'value':str(COMFY/'input'/r['file']),
                      'enabled':True,'slot':sum(x['type']==r.get('type','image') for x in items),
                      'order':i,'start':r.get('start',0),'duration':r.get('duration',1)})
    if items:
        kw['link_to_director']=True
        kw['graph_prompt']={'director':{'class_type':'MiniMaxH3Director','inputs':{
            'mode':kw['mode'],'duration':int(kw['duration']),
            'timeline_data':json.dumps({'items':items})}}}
    valid=inspect.signature(cls.run).parameters
    result=cls().run(**{k:v for k,v in kw.items() if k in valid})
    if isinstance(result,dict): result=result['result']
    return {'prompt':result[0], 'report':'\n'.join([str(x) for x in result[1:]]+notes)}

def continuum_clip(body,kw):
    """A Continuum List clip after the first: tell the writer what is carried in and where it ended."""
    carry=int(num(body.get('carry_frames'),0))
    if carry<=0:return []
    seconds=carry/24.0
    clip=int(num(body.get('clip_index'),2));chunks=int(num(body.get('chunks'),0))
    early=[]
    for i,c in enumerate(body.get('cards',[]),1):
        times=([c.get('at')] if i>1 else [])+[x.get('at') for x in (c.get('lines') or [])+(c.get('acts') or [])]
        if any(t not in (None,'') and num(t,seconds)<seconds for t in times):early.append('샷 %d'%i)
    if early:
        raise ValueError('%s: 앞 클립에서 이어받는 %.2f초 구간 안에 시각이 있습니다. %.2f초 이후로 옮기세요.'%(', '.join(early),seconds,seconds))
    note=('CONTINUUM CLIP %d: this clip opens with the previous clip\'s last %d frames (%.2f s) already on '
          'screen, and the video model reads only this clip\'s prompt. [Shot 1] starts at 0 seconds in that '
          'carried state: restate where each visible person is, their posture and what they hold, as the '
          'previous clip leaves them. Motion already under way continues through the carried span; new '
          'events, lines and cuts begin after %.2f s.\n'
          'PREVIOUS CLIP PROMPT, supplied only to read its final state; its events are already finished:\n%s'
          % (clip,carry,seconds,seconds,str(body.get('previous_clip') or '').strip()))
    # The Shot Builder spec carries its own extra_directives and the writer prefers it.
    spec=json.loads(kw['spec']) if str(kw.get('spec') or '').strip() else None
    if spec is None:kw['extra_directives']=(str(kw.get('extra_directives') or '')+'\n'+note).strip()
    else:
        spec['extra_directives']=(str(spec.get('extra_directives') or '')+'\n'+note).strip()
        kw['spec']=json.dumps(spec,ensure_ascii=False)
    return ['클립 %d: 제작 설정의 청크 수(%d)보다 많습니다.'%(clip,chunks)] if chunks and clip>chunks else []

def freeze(body,ollama_url):
    result=node('prompt_freeze').MMH3_PromptFreeze().run(body['prompt'],revise=body['request'],revise_model=body['model'],revise_url=ollama_url)
    success=isinstance(result,dict)
    values=result['result'] if success else result
    return {'prompt':values[0], 'report':values[1], 'previous':values[2], 'applied':success}
