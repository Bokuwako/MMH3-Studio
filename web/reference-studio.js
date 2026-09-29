import {uiConfirm,uiPrompt,userOption,uiLocale} from './i18n.js';
const CHARACTER_EDIT=`Create a professional character reference sheet based strictly on <image1>.

The character is the same person shown in <image2>. Use <image2> as an additional reference to capture more accurate facial features, proportions, hairstyle, clothing details, accessories, and other fine details.

Character consistency:

* Preserve the character’s exact face, facial structure, hairstyle, proportions, clothing, colors, accessories, and identifiable details from the references.
* Do not redesign, reinterpret, beautify, or alter the face.
* Maintain the exact same person and identity across every panel.
* Capture all fine details from both reference images.
* Use <image2> whenever it provides additional information or details not clearly visible in <image1>.

Top section — full-body turnaround:
Place three full-body character views across the top:

1. Front view
2. Side/profile view
3. Back view

* Same outfit and identical character proportions in all three views.
* Use the same neutral standing pose for every view.
* Arms slightly separated from the torso so the silhouette and clothing are clearly visible.
* Hands relaxed and naturally posed.
* Keep the camera height, framing, scale, and perspective consistent between all three views.
* No pose drift, proportion drift, outfit changes, or character redesign.
* The back view must accurately match the front and side views.

Bottom section — expressions and props:
Use the bottom area for a clean collection of smaller reference panels.

Include three facial expression close-ups:

* Open mouth
* Smiling
* Surprised expression

Also include several **small, clearly separated square panels showing different character props/accessories** relevant to the reference.

Each prop should be isolated, clearly visible, and presented like a professional character-design reference sheet.

Right side — large portrait:
Place one large, highly detailed shoulder-up portrait of the same person on the right side.

* Preserve the exact face and identity from <image1> and <image2>.
* Use <image2> to improve facial accuracy and capture details that may be missing from <image1>.
* High facial detail and accurate proportions.
* Clean, centered composition.
* Professional character-sheet presentation.
* The portrait must clearly match the face shown in all turnaround views and expression panels.

Layout and quality:

* Clean, professional character-sheet layout.
* Clearly separated panels with consistent spacing.
* Nothing may overlap, collide, merge, or bleed into another panel.
* No element should cross into another frame.
* Keep every character, expression, prop, and portrait completely contained within its designated area.
* No cropped heads, hands, feet, props, or important clothing details.
* Balanced spacing and clear visual hierarchy.
* High resolution and highly detailed.
* Maintain absolute character consistency across the entire sheet.
* Zero identity drift, zero outfit drift, zero proportion drift, and zero visual inconsistency.`;
// Same ratio chips and sizes as Resolution Pixaroma, so a size picked there can be picked here.
const SIZES={'1:1':[[512,512],[768,768],[1024,1024],[1280,1280],[1328,1328],[1408,1408],[1536,1536],[2048,2048]],
 '16:9':[[832,480],[1280,720],[1344,768],[1536,864],[1600,896],[1664,928],[1792,1008],[1920,1088]],
 '9:16':[[480,832],[720,1280],[768,1344],[864,1536],[896,1600],[928,1664],[1008,1792],[1088,1920]],
 '2:1':[[512,256],[1024,512],[1280,640],[1536,768],[1600,800],[1792,896],[1920,960],[2048,1024]],
 '3:2':[[768,512],[1024,680],[1152,768],[1344,896],[1536,1024],[1632,1088],[1728,1152],[1920,1280]],
 '2:3':[[512,768],[680,1024],[768,1152],[896,1344],[1024,1536],[1088,1632],[1152,1728],[1280,1920]],
 '4:3':[[512,384],[640,480],[768,576],[1024,768],[1280,960],[1408,1056],[1600,1200],[1920,1440]],
 '3:4':[[384,512],[480,640],[576,768],[768,1024],[960,1280],[1056,1408],[1200,1600],[1440,1920]],
 '4:5':[[512,640],[640,800],[768,960],[832,1040],[1024,1280],[1152,1440],[1280,1600],[1536,1920]]};
export function referenceDesk({api,toast,onAsset}) {
 let state={},catalog=null,loaded=false,loading=false,timer,saveTimer,watching=false;
 const host=document.querySelector('#reference'),$=s=>host.querySelector(s);
 const el=(tag,text,cls)=>{const e=document.createElement(tag);if(text!=null)e.textContent=text;if(cls)e.className=cls;return e};
 const preset={character:{body:'reference sheet, character turnaround, same character in three distinct full-body views: front, side profile, back. Standing neutral pose, consistent outfit and proportions, plain white background, evenly spaced, entire body visible.',detail:'facial reference sheet, same character in front, three-quarter and side-profile close-up portraits. Consistent face, hairstyle, eye color and accessories, plain white background.',edit:CHARACTER_EDIT},environment:{body:'Environment reference sheet, wide establishing view of the same location with clearly readable spatial layout, architecture, materials and lighting. No people, consistent art style.',detail:'Environment detail reference sheet of the same location, close-up views of distinctive architectural features, props, surfaces and materials, consistent lighting. No people.',edit:'Create one coherent environment reference sheet from the supplied images. Use <image1> for the location and layout, and any additional images for material and prop details. Preserve the architecture, spatial relationships, palette and lighting. Arrange a large establishing view and supporting detail views with clean separation. Do not add people.'}};
 async function save(){clearTimeout(saveTimer);await api('/api/ref-studio/state',state)}
 function changed(){clearTimeout(saveTimer);saveTimer=setTimeout(()=>save().catch(e=>toast(e.message)),600)}
 function button(text,fn,cls){const b=el('button',text,cls);b.onclick=async()=>{b.disabled=true;try{await fn()}catch(e){toast(e.message)}finally{b.disabled=false}};return b}
 function field(label,obj,key,type='text',values){const wrap=el('label',label),input=values?el('select'):el(type==='textarea'?'textarea':'input');if(values){for(const v of values)input.append(new Option(Array.isArray(v)?v[1]:v,Array.isArray(v)?v[0]:v));if(obj[key]&&!values.some(v=>(Array.isArray(v)?v[0]:v)===obj[key]))input.append(new Option(obj[key]+' · 현재 미설치',obj[key]));input.value=obj[key]??''}else if(type==='checkbox'){input.type='checkbox';input.checked=!!obj[key]}else{if(type!=='textarea')input.type=type;input.value=obj[key]??'';if(type==='number')input.step='any'}input.setAttribute('aria-label',label);input.onchange=()=>{obj[key]=type==='checkbox'?input.checked:type==='number'?Number(input.value):input.value;changed()};wrap.append(input);return wrap}
 function preview(src){let dialog=document.querySelector('#ref-image-preview');if(!dialog){dialog=el('dialog');dialog.id='ref-image-preview';document.body.append(dialog)}dialog.replaceChildren(button('닫기',()=>dialog.close()));const img=el('img');img.src=src;img.alt='레퍼런스 원본';dialog.append(img);dialog.showModal()}
 function image(src,alt){const img=el('img');img.src=src;img.alt=alt;img.loading='lazy';img.onclick=()=>preview(src);return img}
 function settings(stage){const p=state[stage],models=catalog.models,detail=el('details',null,'ref-settings');detail.append(el('summary',stage==='anima'?'모델 · 해상도 · 고급 설정':'Qwen 모델 · 편집 설정'));const grid=el('div',null,'form-grid');
  if(stage==='anima'){
   grid.append(field('이미지 체크포인트',p,'model','text',models.checkpoints),field('모델 계열',p,'profile','text',[['anima','Anima'],['standard','일반 SD / SDXL 체크포인트']]),field('이미지 VAE · 비우면 체크포인트',p,'vae','text',['',...models.vaes]),field('가로',p,'width','number'),field('세로',p,'height','number'),field('얼굴 시트 가로 · 비우면 전신의 절반',p,'face_width','number'),field('SageAttention',p,'sage','checkbox'),field('DCW · Anima만 적용',p,'dcw','checkbox'),field('Flow shift · Anima',p,'shift','number'),field('2차 업스케일 + refine',p,'upscale','checkbox'),field('업스케일 모델',p,'upscaler','text',models.upscalers),field('Refine 스텝',p,'refine_steps','number'),field('Refine CFG',p,'refine_cfg','number'),field('Refine denoise',p,'refine_denoise','number'),field('Refine 샘플러',p,'refine_sampler','text',models.samplers),field('Refine 스케줄러',p,'refine_scheduler','text',models.schedulers),field('검출 영역 보정 · Detailer',p,'face','checkbox'),field('보정할 영역의 검출 모델',p,'detector','text',models.detectors));
  }else{
   const loader=field('Qwen 모델 형식',p,'loader','text',[['UNETLoader','Safetensors'],['UnetLoaderGGUF','GGUF']]);loader.querySelector('select').addEventListener('change',()=>render());grid.append(loader,field('Qwen 이미지 모델',p,'model','text',p.loader==='UnetLoaderGGUF'?models.gguf:models.diffusion),field('Qwen 텍스트 인코더',p,'clip','text',models.clips),field('Qwen VAE',p,'vae','text',models.vaes),field('입력 해상도 기준 · 0은 원본',p,'resolution','number'),field('KV 캐시 위치',p,'cache_device','text',['auto','gpu','cpu','off']),field('KV 캐시 정밀도',p,'cache_dtype','text',['default','int8','int4']));
  }
  grid.append(field('스텝',p,'steps','number'),field('CFG',p,'cfg','number'),field('샘플러',p,'sampler','text',models.samplers),field('스케줄러',p,'scheduler','text',models.schedulers),field('시드',p,'seed','number'),field('생성마다 새 시드',p,'random_seed','checkbox'));detail.append(grid,field('네거티브 프롬프트',p,'negative','textarea'));
  detail.append(el('p',stage==='anima'?'다른 체크포인트를 고를 때 모델 계열·VAE·LoRA도 함께 맞춰 주세요. Detailer는 선택한 검출 모델의 영역을 보정합니다. person은 인물 전체, face는 얼굴입니다.':'Qwen Image 2.1과 호환되는 모델·인코더·VAE 조합을 선택하세요. 출력 비율은 첫 입력 이미지에서 가져옵니다.','hint'));
  const box=el('div');box.append(detail);
  if(stage==='anima'){box.append(loraList(p,'loras','1차 생성 LoRA','시트를 처음 그릴 때 적용합니다.'),loraList(p,'refine_loras','2차 refine LoRA','업스케일 뒤 refine에만 적용합니다. 원래 워크플로우의 LoRA 스택이 여기에 있었습니다.'))}
  else{box.prepend(sizePicker(p));box.append(loraList(p,'loras','LoRA','Qwen 편집에 적용합니다.'))}
  return box;
 }
 function sizePicker(p){
  const wrap=el('div',null,'ref-size');p.size_mode??='fixed';wrap.append(el('h3','출력 크기'));
  const mode=field('크기 정하기',p,'size_mode','text',[['fixed','직접 지정 · Pixaroma 프리셋'],['input','첫 입력 이미지 크기 따르기']]);mode.querySelector('select').addEventListener('change',()=>render());wrap.append(mode);
  if(p.size_mode!=='fixed'){wrap.append(el('p','첫 입력 이미지의 비율을 따르고, 크기는 아래 고급 설정의 입력 해상도 기준을 따릅니다.','hint'));return wrap}
  const grid=el('div',null,'form-grid'),ratios=[...Object.keys(SIZES),['custom','직접 입력']];
  const ratio=field('비율',p,'ratio','text',ratios);ratio.querySelector('select').addEventListener('change',()=>{const list=SIZES[p.ratio];if(list){const [w,h]=list.reduce((a,b)=>Math.abs(b[0]*b[1]-1048576)<Math.abs(a[0]*a[1]-1048576)?b:a);p.width=w;p.height=h;changed()}render()});grid.append(ratio);
  const list=SIZES[p.ratio];
  if(list){const size=el('label','크기'),select=el('select');for(const [w,h] of list)select.append(new Option(`${w} × ${h}`,`${w}x${h}`));select.value=`${p.width}x${p.height}`;if(!list.some(([w,h])=>w===p.width&&h===p.height))select.append(new Option(`${p.width} × ${p.height} · 직접 입력`,`${p.width}x${p.height}`));select.value=`${p.width}x${p.height}`;select.setAttribute('aria-label','출력 크기');select.onchange=()=>{[p.width,p.height]=select.value.split('x').map(Number);changed();render()};size.append(select);grid.append(size)}
  grid.append(field('가로',p,'width','number'),field('세로',p,'height','number'));wrap.append(grid,el('p',`${p.width} × ${p.height} · ${((p.width*p.height)/1e6).toFixed(2)}MP`,'hint'));return wrap;
 }
 function characterPicker(refresh){
  const wrap=el('div',null,'ref-characters');state.characters??=[];wrap.append(el('span','2. 캐릭터 · 단부루 이름 검색 또는 직접 입력','ref-field-title'));
  const chips=el('div',null,'ref-chips');for(const [i,c] of state.characters.entries()){const chip=el('span',null,'ref-chip'+(c.count?'':' free'));chip.append(el('strong',animaTag(c.tag)),el('small',c.count?`${c.count.toLocaleString(uiLocale())}건${c.series?' · '+animaTag(c.series):''}`:'직접 입력 · 목록에 없음'));chip.append(button('✕',()=>{state.characters.splice(i,1);changed();render()}));chips.append(chip)}wrap.append(chips);
  const box=el('div',null,'ref-search'),input=el('input'),list=el('div',null,'ref-suggest');input.placeholder='이름 입력 · 한국어도 됩니다 (예: 시로코, frieren)';input.setAttribute('aria-label','캐릭터 검색');
  const add=c=>{if(!state.characters.some(x=>x.tag===c.tag))state.characters.push(c);changed();render();host.querySelector('.ref-search input')?.focus()};
  let timer,found=[];
  const show=()=>{list.replaceChildren();for(const c of found){const item=el('button',null,'ref-suggest-item');item.type='button';item.append(el('strong',animaTag(c.tag)),el('small',`${c.count.toLocaleString(uiLocale())}건${c.series?' · '+animaTag(c.series):''}${c.count<200?' · 학습이 약할 수 있음':''}`));if(c.note)item.append(el('span',c.note));item.onclick=()=>add(c);list.append(item)}
   if(input.value.trim()){const free=el('button',null,'ref-suggest-item free');free.type='button';free.append(el('strong',`"${input.value.trim()}" 그대로 추가`),el('small','목록에서 확인되지 않은 이름'));free.onclick=()=>add({tag:input.value.trim()});list.append(free)}};
  input.oninput=()=>{clearTimeout(timer);const q=input.value;timer=setTimeout(async()=>{try{found=q.trim()?await api('/api/ref-studio/characters?'+new URLSearchParams({q})):[];if(input.value===q)show()}catch(e){toast(e.message)}},180)};
  input.onkeydown=e=>{if(e.key==='Enter'){e.preventDefault();if(found.length&&!e.shiftKey)add(found[0]);else if(input.value.trim())add({tag:input.value.trim()})}if(e.key==='Escape')list.replaceChildren()};
  box.append(input,list);wrap.append(box,el('p','Enter: 첫 후보 선택 · Shift+Enter: 입력한 그대로 추가. 고른 캐릭터 뒤에 작품 태그가 자동으로 붙고, 괄호는 Anima 형식으로 바뀝니다.','hint'));
  refresh();return wrap;
 }
 function loraList(p,key,title,note){
  const models=catalog.models,wrap=el('details',null,'ref-lora-block'),id=(p===state.qwen?'qwen:':'anima:')+key;p[key]??=[];if(openLoras.has(id))wrap.open=true;wrap.ontoggle=()=>wrap.open?openLoras.add(id):openLoras.delete(id);
  const head=el('summary',null,'ref-lora-head');head.append(el('h3',title),el('small',`${p[key].filter(l=>l.enabled&&l.model).length} / ${p[key].length}개 사용`));wrap.append(head,el('p',note,'hint'));
  for(const [i,l] of p[key].entries()){const row=el('div',null,'ref-lora'),pick=field('LoRA',l,'model','text',['',...models.loras]),select=pick.querySelector('select');
   const search=el('input',null,'option-filter');search.type='search';search.placeholder='LoRA 검색…';search.setAttribute('aria-label',title+' 검색');
   search.oninput=()=>{const words=search.value.trim().toLowerCase().split(/\s+/).filter(Boolean);for(const o of select.options)o.hidden=!words.every(w=>(o.textContent+' '+o.value).toLowerCase().includes(w))};
   pick.insertBefore(search,select);
   row.append(field('사용',l,'enabled','checkbox'),pick,field('강도',l,'strength','number'),button('제거',()=>{p[key].splice(i,1);changed();render()},'danger'));wrap.append(row)}
  if(!p[key].length)wrap.append(el('p','LoRA 없음','hint'));
  wrap.append(button('＋ LoRA 추가',()=>{p[key].push({enabled:true,model:'',strength:1});changed();render()}));
  return wrap;
 }
 // Anima reads Danbooru tags with spaces, and ComfyUI would take bare parentheses as weights.
 const animaTag=t=>String(t).trim().replace(/_/g,' ').replace(/(?<!\\)([()])/g,'\\$1');
 function assembled(slot){const names=[],series=[];for(const c of state.characters||[]){names.push(animaTag(c.tag));if(c.series&&!series.includes(c.series))series.push(c.series)}
  return [state.quality,[...names,...series.map(animaTag)].join(', '),state.description,state[slot+'Prompt']].map(x=>String(x||'').trim().replace(/,\s*$/,'')).filter(Boolean).join(',\n')}
 async function generate(stage,slot){await save();const prompt=stage==='anima'?assembled(slot):state.editPrompt;const job=await api('/api/ref-studio/generate',{stage,slot,target:state.mode,label:stage==='qwen'?'최종 레퍼런스':slot==='body'?(state.mode==='character'?'전신 시트':'장소 시트'):(state.mode==='character'?'얼굴 시트':'공간 디테일'),prompt,settings:state[stage],sources:stage==='qwen'?state.sources:[]});toast('생성을 큐에 추가했습니다.');await refreshJobs();return job}
 function render(){host.replaceChildren();
  const intro=el('div',null,'ref-flow');for(const [n,title,sub] of [['01','재료 만들기','전신 · 얼굴 · 배경'],['02','한 장으로 편집','선택한 이미지를 Qwen으로'],['03','에셋에 보관','영상 제작에 바로 사용']]){const item=el('div');item.append(el('small',n),el('strong',title),el('span',sub));intro.append(item)}host.append(intro);
  const layout=el('div',null,'reference-layout'),left=el('section',null,'panel reference-stage'),right=el('section',null,'panel reference-stage');layout.append(left,right);host.append(layout);
  left.append(el('div','ANIMA / SOURCE SHEETS','eyebrow'),el('h2','1. 레퍼런스 재료 만들기'));
  const mode=field('제작 대상',state,'mode','text',[['character','캐릭터'],['environment','배경 · 장소']]);const before=state.mode;mode.querySelector('select').addEventListener('change',()=>{
   // Each target keeps its own edited prompts; the preset only fills a target never edited.
   state.prompts??={};state.prompts[before]={body:state.bodyPrompt,detail:state.detailPrompt,edit:state.editPrompt};
   const kept=state.prompts[state.mode]||{},p=preset[state.mode];state.bodyPrompt=kept.body??p.body;state.detailPrompt=kept.detail??p.detail;state.editPrompt=kept.edit??p.edit;state.detailEnabled=state.mode==='character';state.role=state.mode==='character'?'character_full':'background';changed();render()});const quality=field('1. 퀄리티 태그',state,'quality','textarea'),described=field('3. 공통 묘사 · 두 시트에 함께 적용',state,'description','textarea');quality.querySelector('textarea').rows=2;described.querySelector('textarea').placeholder='인물의 외형·의상·스타일 또는 장소의 구조·재질·조명을 적으세요.';
  const preview=el('pre',null,'ref-assembled'),refresh=()=>{preview.textContent=assembled('body')};for(const box of [quality,described])box.querySelector('textarea').addEventListener('input',e=>{state[box===quality?'quality':'description']=e.target.value;refresh()});
  left.append(mode,quality,characterPicker(refresh),described);const shown=el('details',null,'ref-assembled-box');shown.append(el('summary','실제로 들어가는 프롬프트 · 전신 시트'),preview);refresh();
  const sheets=el('div',null,'ref-sheet-forms');for(const slot of ['body','detail']){const card=el('div',null,'ref-sheet-form');const label=slot==='body'?(state.mode==='character'?'전신 · 여러 구도':'배경 · 전체 모습'):(state.mode==='character'?'얼굴 · 여러 구도':'배경 · 세부 모습');card.append(field(label,state,slot+'Prompt','textarea'),button('이 시트 생성',()=>generate('anima',slot)));sheets.append(card)}left.append(shown,sheets,field('두 번째 시트도 함께 생성',state,'detailEnabled','checkbox'));const actions=el('div',null,'actions');actions.append(button('선택한 시트 생성',async()=>{if(!state.description.trim()&&!(state.characters||[]).length)throw Error('캐릭터나 공통 묘사를 입력하세요.');await generate('anima','body');if(state.detailEnabled)await generate('anima','detail')},'primary'));left.append(actions,settings('anima'),el('h3','생성한 시트'));const gallery=el('div',null,'ref-results');gallery.id='ref-source-results';left.append(gallery);
  right.append(el('div','QWEN IMAGE EDIT / FINAL REFERENCE','eyebrow'),el('h2','2. 한 장으로 정리하기'),el('p','왼쪽 결과를 골라 추가하거나 기존 이미지를 업로드하세요. 표시된 순서가 image1, image2가 됩니다.','hint'));
  const inputs=el('div',null,'ref-inputs');state.sources??=[];for(const [i,source] of state.sources.entries()){const tile=el('div',null,'ref-input');tile.append(image(source.url,source.label||'입력 이미지'),el('strong',`image${i+1}`));const row=el('div',null,'actions');if(i)row.append(button('앞으로',()=>{[state.sources[i-1],state.sources[i]]=[source,state.sources[i-1]];changed();render()}));row.append(button('제외',()=>{state.sources.splice(i,1);changed();render()}));tile.append(row);inputs.append(tile)}if(!state.sources.length)inputs.append(el('div','아직 선택한 이미지가 없습니다.','ref-input-empty'));right.append(inputs);
  const upload=el('input');upload.type='file';upload.accept='image/png,image/jpeg,image/webp';upload.multiple=true;upload.setAttribute('aria-label','편집할 이미지 업로드');upload.onchange=async()=>{try{for(const file of upload.files){if(state.sources.length>=16)throw Error('이미지는 16장까지 선택할 수 있습니다.');const data=new FormData();data.append('file',file);const response=await fetch('/api/upload',{method:'POST',body:data});const source=await response.json();if(!response.ok)throw Error(source.error||'업로드 실패');state.sources.push({file:source.file,label:source.name,url:'/api/media?'+new URLSearchParams({file:source.file})})}changed();render()}catch(e){toast(e.message)}};right.append(upload,field('편집 지시',state,'editPrompt','textarea'));right.append(settings('qwen'));const edit=button('최종 레퍼런스 생성',()=>generate('qwen','final'),'primary full');edit.disabled=!state.sources.length;right.append(edit,el('h3','편집 결과'));const finals=el('div',null,'ref-results');finals.id='ref-final-results';right.append(finals);
  const saveBox=el('section',null,'panel reference-save');saveBox.append(el('div','LIBRARY / HANDOFF','eyebrow'),el('h2','3. 완성본을 프로젝트 에셋으로'));const previewBox=el('div');previewBox.id='ref-chosen';if(state.final)previewBox.append(image(state.final.url,'선택한 완성본'));else previewBox.append(el('p','편집 결과에서 보관할 이미지를 선택하세요.','hint'));saveBox.append(previewBox);
  const grid=el('div',null,'form-grid');const projects=field('저장할 에셋 프로젝트',state,'project','text',[['','프로젝트 선택'],...(catalog.projects||[]).map(p=>[p.id,p.name])]);grid.append(projects,field('에셋 이름',state,'assetName'),field('이미지 용도',state,'role','text',[['character_full','캐릭터 전체'],['character','인물 외형'],['background','배경 / 장소'],['','용도 미지정']]),field('용도 메모',state,'purpose'));saveBox.append(grid);
  const newProject=el('input');newProject.placeholder='새 에셋 프로젝트 이름';newProject.setAttribute('aria-label','새 레퍼런스 프로젝트 이름');const row=el('div',null,'actions');row.append(newProject,button('프로젝트 만들기',async()=>{if(!newProject.value.trim())throw Error('프로젝트 이름을 입력하세요.');const p=await api('/api/asset-projects',{name:newProject.value.trim()});state.project=p.id;catalog.projects=(await api('/api/asset-projects')).projects;changed();render()}));const store=button('프로젝트 에셋에 저장',async()=>{if(!state.final||!state.project)throw Error('이미지와 에셋 프로젝트를 선택하세요.');await api('/api/ref-studio/asset',{...state.final,project:state.project,name:state.assetName||'레퍼런스 이미지',role:state.role,purpose:state.purpose});await onAsset(state.project);toast('에셋에 저장했습니다. 에셋 탭에서 레퍼런스로 추가할 수 있습니다.')},'primary');store.disabled=!state.final;row.append(store);saveBox.append(row);host.append(saveBox);paintJobs();
 }
 let jobList=[];const openPrompts=new Set(),openLoras=new Set(),tiles=new Map();const live={job:'',at:'',url:''};
 // Sampler previews reach Studio's websocket like every other preview; show the one
 // that belongs to the running reference job.
 async function livePreview(){const running=jobList.find(j=>j.state==='running');if(!running)return;
  try{const r=await fetch('/api/preview?t='+Date.now());if(r.status!==200||r.headers.get('X-Job')!==running.id)return;const at=r.headers.get('X-At')||'';if(at&&at===live.at&&live.job===running.id)return;
   const url=URL.createObjectURL(await r.blob());if(live.url)URL.revokeObjectURL(live.url);Object.assign(live,{job:running.id,at,url})}catch{}}
 function paintJobs(){const want={'#ref-source-results':[],'#ref-final-results':[]};for(const j of jobList.slice(0,40)){const stage=j.settings.stage,target=stage==='qwen'?'#ref-final-results':'#ref-source-results';
  // Rebuilding a finished tile on every poll restarted its image download before a large sheet
  // could finish loading, so a tile is rebuilt only when something it shows has changed.
  const sig=JSON.stringify([j.state,j.progress?.value,j.progress?.max,(j.outputs||[]).length,j.errors?.length||0,j.state==='running'&&live.job===j.id?live.at:'']);
  const kept=tiles.get(j.id);if(kept&&kept.sig===sig){want[target].push(kept.tile);continue}const tile=el('article',null,'ref-result');tile.append(el('strong',j.settings.label||stage),el('small',`${({queued:'대기 중',running:'생성 중',completed:'완료',failed:'실패',cancelled:'취소됨'})[j.state]||j.state} · seed ${j.settings.settings?.seed??''}`));
  if(j.settings.prompt){const used=el('details',null,'ref-used-prompt');if(openPrompts.has(j.id))used.open=true;used.ontoggle=()=>used.open?openPrompts.add(j.id):openPrompts.delete(j.id);used.append(el('summary','사용한 프롬프트'),el('pre',j.settings.prompt),button('복사',async()=>{await navigator.clipboard.writeText(j.settings.prompt);toast('프롬프트를 복사했습니다.')}));tile.append(used)}if(j.state==='running'&&j.progress){const progress=el('progress');progress.max=j.progress.max;progress.value=j.progress.value;tile.append(progress)}if(j.state==='running'&&live.job===j.id&&live.url){const img=el('img',null,'ref-live');img.src=live.url;img.alt='생성 중 미리보기';tile.append(img)}
  const outputs=(j.outputs||[]).filter(o=>o.node==='save'&&/\.(png|jpg|webp)$/i.test(o.filename));outputs.forEach((o,index)=>{const source={job_id:j.id,index,url:o.url,label:j.settings.label};tile.append(image(o.url,source.label));const row=el('div',null,'actions');row.append(button('편집에 추가',()=>{if(state.sources.length>=16)throw Error('이미지는 16장까지 선택할 수 있습니다.');if(!state.sources.some(x=>x.job_id===j.id&&x.index===index))state.sources.push(source);changed();render()}),button('이 이미지 보관',()=>{state.final=source;changed();render();$('#ref-chosen').scrollIntoView({behavior:'smooth',block:'center'})}));const download=el('a','원본');download.href=o.url;download.target='_blank';row.append(download);tile.append(row)});
  if(j.errors?.length)tile.append(el('pre',j.errors.join('\n')));if(['queued','running'].includes(j.state))tile.append(button('이 작업 취소',async()=>{await api('/api/jobs/'+j.id+'/cancel',{});await refreshJobs()}));else tile.append(button('결과 삭제',async()=>{if(!uiConfirm('이 생성 결과를 휴지통으로 옮길까요? 에셋에 보관한 사본은 유지됩니다.'))return;await api('/api/delete/job',{id:j.id});state.sources=state.sources.filter(x=>x.job_id!==j.id);if(state.final?.job_id===j.id)state.final=null;changed();await refreshJobs();render()},'danger'));tiles.set(j.id,{sig,tile});want[target].push(tile)}
  for(const [id,list] of Object.entries(want)){const box=$(id);if(box&&(box.children.length!==list.length||list.some((t,i)=>box.children[i]!==t)))box.replaceChildren(...list)}
 }
 async function refreshJobs(){jobList=await api('/api/ref-studio/jobs');for(const j of jobList.filter(x=>['queued','running','unknown'].includes(x.state))){try{Object.assign(j,await api('/api/jobs/'+j.id))}catch{}}await livePreview();paintJobs()}
 async function tick(){if(watching)return;watching=true;try{if(loaded&&document.visibilityState==='visible'&&host.classList.contains('active'))await refreshJobs()}catch(e){toast(e.message)}finally{watching=false;timer=setTimeout(tick,2500)}}
 return {save,async show(){if(loading)return;loading=true;try{if(!loaded){host.replaceChildren(el('p','워크플로우와 설치된 모델을 확인하고 있습니다…'));const [c,s]=await Promise.all([api('/api/ref-studio/catalog'),api('/api/ref-studio/state')]);catalog=c;state={mode:'character',description:'',characters:[],bodyPrompt:preset.character.body,detailPrompt:preset.character.detail,editPrompt:preset.character.edit,detailEnabled:true,sources:[],assetName:'',role:'character_full',purpose:'',...s,anima:{...c.defaults.anima,...s.anima},qwen:{...c.defaults.qwen,...s.qwen}};
    if(state.quality===undefined){state.quality='masterpiece, best quality';const strip=t=>typeof t==='string'?t.replace(/^\s*masterpiece,\s*best quality,\s*/i,''):t;state.bodyPrompt=strip(state.bodyPrompt);state.detailPrompt=strip(state.detailPrompt);for(const kept of Object.values(state.prompts||{})){kept.body=strip(kept.body);kept.detail=strip(kept.detail)}}loaded=true;tick()}catalog.projects=(await api('/api/asset-projects')).projects;render();await refreshJobs()}catch(e){host.replaceChildren(el('p',e.message),button('다시 연결',()=>this.show()));toast(e.message)}finally{loading=false}}};
}
