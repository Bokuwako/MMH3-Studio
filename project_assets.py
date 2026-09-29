"""Studio project assets; role metadata is the only classification source."""
import json
import re
import shutil
import uuid
from pathlib import Path

ID = re.compile(r'^[a-f0-9]{32}$')

class ProjectAssets:
    def __init__(self, root):
        self.root = Path(root)

    def project(self, key):
        if not isinstance(key,str) or not ID.fullmatch(key):
            raise ValueError('올바른 에셋 프로젝트를 선택하세요.')
        p=self.root/key
        if not (p/'project.json').is_file():
            raise ValueError('에셋 프로젝트가 없습니다.')
        return p

    @staticmethod
    def read(p):
        return json.loads(p.read_text(encoding='utf-8'))

    @staticmethod
    def write(p,data):
        tmp=p.with_suffix('.tmp')
        tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
        tmp.replace(p)

    def projects(self):
        return [self.read(p) for p in sorted(self.root.glob('*/project.json'))]

    def create(self,name):
        name=str(name).strip()
        if not name or len(name)>100:raise ValueError('프로젝트 이름은 1~100자로 입력하세요.')
        if any(p['name']==name for p in self.projects()):raise ValueError('같은 이름의 프로젝트가 있습니다.')
        data={'id':uuid.uuid4().hex,'name':name}
        p=self.root/data['id'];p.mkdir(parents=True)
        self.write(p/'project.json',data)
        return data

    def items(self,key):
        return [self.read(p) for p in sorted(self.project(key).glob('*/asset.json'))]

    def get(self,key,aid):
        if not isinstance(aid,str) or not ID.fullmatch(aid):raise ValueError('잘못된 에셋입니다.')
        base=self.project(key)/aid
        a=self.read(base/'asset.json');p=(base/a['stored_file']).resolve()
        if not p.is_relative_to(base.resolve()) or not p.is_file():raise ValueError('에셋 파일이 없습니다.')
        return a,p

    def store(self,key,source,metadata):
        project=self.project(key);source=Path(source)
        kind=metadata.get('type','image')
        if kind not in ('image','audio','video'):raise ValueError('지원하지 않는 에셋입니다.')
        a={k:metadata[k] for k in ('name','type','role','purpose','duration','trim_start','trim_end','media_mode','role_label') if k in metadata}
        # Targets and shot numbers belong to the clip, not the reusable asset.
        a.update(id=uuid.uuid4().hex,type=kind,name=metadata.get('name') or source.name,stored_file='media'+source.suffix.lower())
        base=project/a['id'];base.mkdir()
        shutil.copy2(source,base/a['stored_file']);self.write(base/'asset.json',a)
        return a

    def use(self,key,aid,input_root):
        a,p=self.get(key,aid)
        dst=Path(input_root)/'mmh3_studio'/(uuid.uuid4().hex+p.suffix)
        dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,dst)
        return {**{k:v for k,v in a.items() if k not in ('id','stored_file','role_label')},'file':'mmh3_studio/'+dst.name,'scope':'','target':'','start':0,'enabled':True}
