"""Recoverable local deletion with bounded paths and conflict-safe restoration."""
import json
import time
import uuid
from pathlib import Path


class Trash:
    def __init__(self, root, allowed):
        self.root=Path(root).resolve()
        self.allowed=[Path(p).resolve() for p in allowed]

    def checked(self, path):
        p=Path(path).resolve()
        if not any(p!=r and p.is_relative_to(r) for r in self.allowed):
            raise ValueError('관리 대상 밖의 파일입니다.')
        return p

    @staticmethod
    def write(path, text):
        temp=path.with_name(path.name+'.studio-tmp')
        temp.write_text(text,encoding='utf-8');temp.replace(path)

    def list(self):
        result=[]
        for p in self.root.glob('*/entry.json'):
            d=json.loads(p.read_text(encoding='utf-8'))
            if d['state']=='deleted':result.append({k:d[k] for k in ('id','label','kind','created')})
        return sorted(result,key=lambda x:x['created'],reverse=True)

    def remove(self, label, kind, paths=(), patches=(), payload=None):
        sources=list(dict.fromkeys(self.checked(p) for p in paths if Path(p).exists()))
        if any(a!=b and a.is_relative_to(b) for a in sources for b in sources):raise ValueError('중복 삭제 경로')
        edits=[]
        for path,after in patches:
            p=self.checked(path)
            edits.append({'path':str(p),'before':p.read_text(encoding='utf-8'),'after':after})
        key=uuid.uuid4().hex;directory=self.root/key;directory.mkdir(parents=True)
        data={'id':key,'label':label,'kind':kind,'created':time.time(),'state':'preparing','moves':[{'source':str(p),'stored':str(i)} for i,p in enumerate(sources)],'patches':edits,'payload':payload or {}}
        record=directory/'entry.json'
        self.write(record,json.dumps(data,ensure_ascii=False))
        moved=[];changed=[]
        try:
            for item in data['moves']:
                self.checked(item['source']).rename(directory/item['stored']);moved.append(item)
            for edit in edits:
                self.write(self.checked(edit['path']),edit['after']);changed.append(edit)
            data['state']='deleted';self.write(record,json.dumps(data,ensure_ascii=False))
        except Exception:
            for edit in reversed(changed):self.write(Path(edit['path']),edit['before'])
            for item in reversed(moved):(directory/item['stored']).rename(item['source'])
            raise
        return {'id':key,'label':label}

    def restore(self,key):
        if not isinstance(key,str) or len(key)!=32 or any(c not in '0123456789abcdef' for c in key):raise ValueError('잘못된 휴지통 항목')
        directory=self.root/key;record=directory/'entry.json';data=json.loads(record.read_text(encoding='utf-8'))
        if data['state']!='deleted':raise ValueError('이미 복구된 항목입니다.')
        for edit in data['patches']:
            p=self.checked(edit['path'])
            if not p.exists() or p.read_text(encoding='utf-8')!=edit['after']:raise ValueError('삭제 후 프로젝트가 변경되어 덮어쓰지 않고 복구를 중단했습니다. 이후 변경을 먼저 되돌려 주세요.')
        for item in data['moves']:
            if self.checked(item['source']).exists():raise ValueError('같은 경로에 새 파일이 있어 복구할 수 없습니다.')
            if not (directory/item['stored']).exists():raise ValueError('휴지통 파일이 없습니다.')
        moved=[];changed=[]
        try:
            for item in data['moves']:
                target=self.checked(item['source']);target.parent.mkdir(parents=True,exist_ok=True)
                (directory/item['stored']).rename(target);moved.append(item)
            for edit in data['patches']:
                self.write(Path(edit['path']),edit['before']);changed.append(edit)
            data['state']='restored';self.write(record,json.dumps(data,ensure_ascii=False))
        except Exception:
            for edit in reversed(changed):self.write(Path(edit['path']),edit['after'])
            for item in reversed(moved):Path(item['source']).rename(directory/item['stored'])
            raise
        return data


def delete_clip(trash,project,index,take=None):
    index=int(index)
    entry=next((c for c in project.clips if c['index']==index),None)
    if entry is None:raise ValueError('클립이 없습니다.')
    paths=[]
    if take is None:
        removed=project.clips[index-1:]
        targets=[t for c in removed for t in project.takes_of(c['index'])]
        project.clips=project.clips[:index-1]
        label=f'{project.name} · 클립 {index}~{removed[-1]["index"]}'
    else:
        take=int(take);takes=project.takes_of(index)
        targets=[t for t in takes if t['take']==take]
        if not targets:raise ValueError('후보가 없습니다.')
        if entry['take']==take and index<len(project.clips):raise ValueError('뒤 클립이 사용하는 후보입니다. 다른 후보만 삭제하거나 클립 전체 삭제를 사용하세요.')
        remaining=[t for t in takes if t['take']!=take]
        if not remaining:return delete_clip(trash,project,index)
        entry['takes']=remaining
        if entry['take']==take:
            chosen=remaining[-1];entry.update(take=chosen['take'],basename=chosen['basename'],meta=chosen.get('meta',{}),status='pending')
        label=f'{project.name} · 클립 {index} 후보 {take}'
    for t in targets:
        directory=project.locate_pair(t['basename'])
        if directory:
            for ext in ('.mp4','.safetensors','.json'):
                paths.append(Path(directory)/(t['basename']+ext))
    project._check_invariants()
    manifest=Path(project.manifest_path);data=json.loads(manifest.read_text(encoding='utf-8'));data['clips']=project.clips
    return trash.remove(label,'clip',paths,[(manifest,json.dumps(data,ensure_ascii=False,indent=2))])
