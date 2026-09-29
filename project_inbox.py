"""Adopt completed standalone renders without rerunning the video model."""
import importlib.util
import json
import os
import shutil
from pathlib import Path

DRAFT_PREFIX='StudioInbox-'

def core(comfy):
    spec=importlib.util.spec_from_file_location('studio_project_core',Path(comfy)/'custom_nodes/ComfyUI-H3-Project-Suite/project.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def video_output(job):
    return next((o for o in job.get('outputs',[]) if Path(o.get('filename','')).suffix.lower() in ('.mp4','.webm','.mov')),None)

def copy_file(source,target):
    temp=target.with_suffix(target.suffix+'.tmp')
    shutil.copy2(source,temp);os.replace(temp,target)

def adopt(comfy,job,name):
    """The request identifies a recorded job, never an arbitrary input path."""
    if job.get('state')!='completed':raise ValueError('완료된 영상만 저장할 수 있습니다.')
    if name.startswith(DRAFT_PREFIX):raise ValueError('예약된 프로젝트 이름입니다.')
    module=core(comfy);output=(Path(comfy)/'output').resolve()
    target=module.Project(str(output),name,create=False)
    draft=job.get('settings',{}).get('_draft_project')
    if draft:
        source=module.Project(str(output),draft,create=False)
        # Suite exposes the pending or accepted source through its public methods.
        clip=source.pending() or source.chain_tail()
        if clip is None:raise ValueError('임시 클립 저장이 완료되지 않았습니다.')
        if target.pending():raise ValueError('대상 프로젝트의 미승인 클립을 먼저 승인하거나 거절하세요.')
        index,take,basename=target.next_save()
        src=Path(source.clips_dir);dst=Path(target.clips_dir);dst.mkdir(parents=True,exist_ok=True)
        for ext in ('.mp4','.safetensors'):
            file=src/(clip['basename']+ext)
            if not file.is_file():raise ValueError('임시 클립 데이터가 없습니다: '+ext)
        for ext in ('.mp4','.safetensors'):
            copy_file(src/(clip['basename']+ext),dst/(basename+ext))
        side=json.loads((src/(clip['basename']+'.json')).read_text(encoding='utf-8'))
        side.update(project=name,clip=basename,index=index,take=take)
        side['source_job']=job['id']
        temp=dst/(basename+'.json.tmp');temp.write_text(json.dumps(side,ensure_ascii=False,indent=2),encoding='utf-8')
        os.replace(temp,dst/(basename+'.json'))
        target.record_render(index,take,clip.get('meta',{}))
        return {'name':name,'basename':basename,'kind':'clip'}
    # Older standalone renders have no recoverable generation latent. Preserve
    # the actual video as an archive instead of inventing an exact continuation.
    item=video_output(job)
    if not item or item.get('type','output')!='output':raise ValueError('저장할 출력 영상이 없습니다.')
    file=(output/item.get('subfolder','')/item['filename']).resolve()
    if not file.is_relative_to(output) or not file.is_file():raise ValueError('출력 영상을 찾을 수 없습니다.')
    directory=Path(target.clips_dir).parent/'studio_imports';directory.mkdir(exist_ok=True)
    # Job IDs originate from ComfyUI; reject malformed persisted records as well.
    import uuid
    job_id=str(uuid.UUID(job['id']))
    destination=directory/(job_id+file.suffix.lower());copy_file(file,destination)
    return {'name':name,'kind':'video','file':str(destination.relative_to(output)),
            'label':item['filename'],'job_id':job_id}
