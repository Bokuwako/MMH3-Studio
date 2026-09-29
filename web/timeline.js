import {uiConfirm,uiPrompt,userOption,uiLocale} from './i18n.js';
// Project editing uses immutable take videos; trims affect playback/export only.
export function mountTimeline({box, name, data:d, node, action, api, toast, prepare, refresh, exported, deleted}) {
 const releaseMedia=()=>box.querySelectorAll('video').forEach(v=>{v.pause();v.removeAttribute('src');v.load()});
 const url=c=>'/api/project/video?'+new URLSearchParams({name,basename:c.basename});
 const title=node('div',null,'timeline-title');title.append(node('h2',name),node('small','후보 생성 → 이 버전 사용 → 다음 클립','hint'));box.append(title);
 const selected=(d.clips||[]).filter(c=>c.status==='approved');
 const player=node('video',null,'timeline-player');player.controls=true;player.preload='metadata';box.append(player);
 const label=node('p','클립을 선택하거나 전체 이어보기를 누르세요.','hint');box.append(label);
 let playlist=[],cursor=0,advancing=false;
 const range=c=>d.edits?.[c.basename]||{start:0,end:null};
 function playList(list){playlist=list;cursor=0;loadClip()}
 function loadClip(){if(cursor>=playlist.length){player.pause();label.textContent='재생 완료';return}const c=playlist[cursor];advancing=false;label.textContent=`클립 ${c.index} · 후보 ${c.take}`;player.src=url(c);player.onloadedmetadata=()=>{player.currentTime=range(c).start||0;player.play().catch(()=>{})}}
 function next(){if(advancing)return;advancing=true;cursor++;loadClip()}
 player.ontimeupdate=()=>{const c=playlist[cursor];if(c&&range(c).end!=null&&player.currentTime>=range(c).end)next()};player.onended=next;
 const tools=node('div',null,'actions');
 const removeProject=node('button','프로젝트 삭제','danger');action(removeProject,async()=>{if(!uiConfirm(`${name} 프로젝트와 모든 클립을 휴지통으로 옮길까요?`))return;releaseMedia();await api('/api/delete/project',{name});await deleted(name);toast('프로젝트를 휴지통으로 옮겼습니다.')});tools.append(removeProject);
 const play=node('button','전체 이어보기');play.disabled=!selected.length;action(play,async()=>{label.textContent='선택 구간을 연결하고 있습니다…';const result=await api('/api/timeline/export',{name});playlist=[];player.onloadedmetadata=null;player.src=result.master_url;label.textContent='선택한 클립 전체 이어보기';await player.play()});tools.append(play);
 const output=node('button','사용 구간으로 영상 저장');output.disabled=!selected.length;action(output,async()=>{const result=await api('/api/timeline/export',{name});exported(result);toast('선택한 구간을 연결해 저장했습니다.');await refresh(name)});tools.append(output);
 const nextButton=node('button',d.pending?`클립 ${d.pending.index} · 다른 후보 만들기`:`클립 ${d.next_save?.index||1} 만들기`,'primary');action(nextButton,()=>prepare(name,!!d.chain_active,!!d.pending));tools.append(nextButton);box.append(tools);
 box.append(node('small','구간 편집은 이어보기와 저장 영상에 적용됩니다. 다음 생성은 선택한 원본 클립의 끝에서 이어집니다.','hint'));
 const track=node('div',null,'clip-track');box.append(track);
 for(const c of d.clips||[]){
  const card=node('article',null,'clip-slot '+(c.status==='approved'?'chosen':'candidate'));
  card.append(node('h3',`클립 ${c.index}`),node('small',c.status==='approved'?'사용 중':'후보 선택 중','clip-badge'));
  const takes=c.takes?.length?c.takes:[c];
  const select=node('select');select.setAttribute('aria-label',`클립 ${c.index} 후보`);for(const t of takes)select.append(new Option(`후보 ${t.take}${t.take===c.take?' · 현재':''}`,t.take));select.value=c.take;card.append(select);
  const chosen=()=>({...c,...takes.find(t=>String(t.take)===select.value)});
  const thumbnail=node('video');thumbnail.controls=true;thumbnail.preload='metadata';thumbnail.src=url(chosen());card.append(thumbnail);
  const cuts=node('div',null,'trim-fields');const start=node('input'),end=node('input');for(const input of [start,end]){input.type='number';input.min=0;input.step=.01;input.setAttribute('aria-label',input===start?'사용 시작 초':'사용 끝 초')}
  function showRange(){const cut=range(chosen());start.value=cut.start||0;end.value=cut.end??'';end.placeholder='영상 끝'}showRange();
  select.onchange=()=>{thumbnail.src=url(chosen());showRange()};
  for(const [text,input] of [['시작 (초)',start],['끝 (초)',end]]){const l=node('label',text);l.append(input);cuts.append(l)}card.append(cuts);
  const marks=node('div',null,'actions');for(const [text,input] of [['현재 위치를 시작으로',start],['현재 위치를 끝으로',end]]){const b=node('button',text);action(b,()=>{input.value=thumbnail.currentTime.toFixed(2)});marks.append(b)}card.append(marks);
  const row=node('div',null,'actions');const trim=node('button','사용 구간 저장');action(trim,async()=>{const t=chosen();const cut=await api('/api/timeline/trim',{name,basename:t.basename,start:start.value,end:end.value});d.edits??={};d.edits[t.basename]=cut;toast('사용 구간을 저장했습니다. 원본은 유지됩니다.')});row.append(trim);
  const preview=node('button',c.index>1?'이음새 2초 미리보기':'이 클립 재생');action(preview,async()=>{const t=chosen();if(c.index===1){playList([t]);return}const result=await api('/api/timeline/preview',{name,index:c.index,take:t.take});playlist=[];player.onloadedmetadata=null;player.src=result.url;label.textContent=`클립 ${c.index-1} 끝 1초 → 클립 ${c.index} 시작 1초`;await player.play();player.scrollIntoView({behavior:'smooth',block:'center'})});row.append(preview);
  if(c.status==='pending'){
   const use=node('button','이 버전 사용','primary');action(use,async()=>{await api('/api/timeline/use',{name,index:c.index,take:Number(select.value)});toast(`클립 ${c.index}을 선택했습니다. 다음 클립을 만들 수 있습니다.`);await refresh(name)});row.append(use);
  } else {
   const retry=node('button','이 클립부터 다시 만들기');action(retry,async()=>{const result=await api('/api/timeline/retry',{name,index:c.index});await refresh(result.name);prepare(result.name,result.chain_active,true);toast('기존 프로젝트는 보존했습니다. 새 버전에서 현재 설정을 확인하고 생성하세요.')});row.append(retry);
   const branch=node('button','이 후보에서 새 버전 이어가기');action(branch,async()=>{const newName=name+'-v'+Date.now().toString(36);await api('/api/project/branch',{name,index:c.index,take:Number(select.value),new_name:newName});toast('기존 프로젝트를 보존하고 새 버전을 만들었습니다.');await refresh(newName);prepare(newName,true,false)});row.append(branch);
  }
  const download=node('a','원본 영상');download.href=url(chosen());download.target='_blank';select.addEventListener('change',()=>download.href=url(chosen()));row.append(download);card.append(row);track.append(card);
  const removeRow=node('div',null,'actions');
  const removeTake=node('button','이 후보 삭제','danger');action(removeTake,async()=>{const t=chosen();if(!uiConfirm(`클립 ${c.index}의 후보 ${t.take}을 휴지통으로 옮길까요?`))return;releaseMedia();await api('/api/delete/clip',{name,index:c.index,take:t.take});toast('후보를 휴지통으로 옮겼습니다.');await refresh(name)});removeRow.append(removeTake);
  const removeClip=node('button','클립 삭제','danger');action(removeClip,async()=>{const affected=(d.clips||[]).filter(x=>x.index>=c.index).map(x=>x.index).join(', ');if(!uiConfirm(`클립 ${affected}을 휴지통으로 옮길까요?\n뒤 클립도 이 클립에 연결되어 함께 제거됩니다.`))return;releaseMedia();await api('/api/delete/clip',{name,index:c.index});toast('클립을 휴지통으로 옮겼습니다.');await refresh(name)});removeRow.append(removeClip);card.append(removeRow);
 }
 if(!d.clips?.length)track.append(node('p','클립 1을 생성하면 여기에 후보가 나타납니다.','empty'));
 for(const file of d.exports||[]){const row=node('div',null,'actions');const a=node('a','연결 영상 · '+file.filename);a.href=file.url;a.target='_blank';row.append(a);const remove=node('button','연결 영상 삭제','danger');action(remove,async()=>{if(!uiConfirm('이 연결 영상을 휴지통으로 옮길까요? 클립 원본은 유지됩니다.'))return;await api('/api/delete/export',{name,filename:file.filename});await refresh(name)});row.append(remove);box.append(row)}
 for(const saved of d.saved_videos||[]){const item=node('div',null,'job');item.append(node('h3',saved.label),node('small','보관 영상 · 이어받기 데이터 없음'));const v=node('video');v.controls=true;v.preload='none';v.src=saved.url;item.append(v);const remove=node('button','보관 영상 삭제','danger');action(remove,async()=>{if(!uiConfirm('보관 영상을 휴지통으로 옮길까요?'))return;releaseMedia();await api('/api/delete/saved-video',{name,id:saved.job_id});await refresh(name)});item.append(remove);box.append(item)}
}
