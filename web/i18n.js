// UI-only localization. Never rewrite form values, prompts or API payloads.
const LANGUAGES={'ko':'한국어','en':'English','ja':'日本語','zh-CN':'简体中文'};
const KEY='mmh3.ui-language';
let language='ko',dictionary={},observer,scheduled=false,templates=[];
try{const saved=localStorage.getItem(KEY);if(LANGUAGES[saved])language=saved}catch{}
const records=new WeakMap(),attrs=new WeakMap();
const protectedAreas='textarea,pre,script,style,[contenteditable],[data-i18n-skip],.chat-text,.chat-checks div,.chat-version span,.chat-title,.ref-title strong,.ref-chip-text strong,.asset-card strong,.project-button,.ref-input strong,.timeline-title h2,.job h3';
function translated(source){
 if(language==='ko')return source;
 const trimmed=source.trim(),entry=dictionary[trimmed]||dictionary[source];
 if(entry?.[language])return source.replace(trimmed,entry[language]);
 for(const {pattern,key} of templates){const match=trimmed.match(pattern);if(match)return source.replace(trimmed,dictionary[key][language].replace(/\{(\d+)\}/g,(_,i)=>{const value=match[Number(i)+1]??'';return key==='{0} 검색'?translated(value):value}))}
 if(/^(완료|생성 중|대기 중|실패|취소됨) · seed /.test(trimmed))return source.replace(/^[^·]+/,x=>translated(x));
 // Structured UI counters only: keep user-provided suffixes verbatim.
 const patterns=[
  [/^이미지 (\d+)(.*)$/,'Image','画像','图像'],
  [/^샷 (\d+)(.*)$/,'Shot','ショット','镜头'],
  [/^클립 (\d+)(.*)$/,'Clip','クリップ','片段'],
 ];
 for(const [pattern,en,ja,zh] of patterns){const m=trimmed.match(pattern);if(m)return source.replace(trimmed,`${({en,ja,'zh-CN':zh})[language]} ${m[1]}${m[2]}`)}
 if(/^(ComfyUI|Ollama) (연결됨|연결 확인 필요)$/.test(trimmed))return source.replace(/연결됨|연결 확인 필요/,x=>dictionary[x]?.[language]||x);
 if(/^\d+개 일치$/.test(trimmed))return trimmed.match(/^\d+/)[0]+' '+({en:'matches',ja:'件一致','zh-CN':'项匹配'})[language];
 if(/^(completed|running|queued|failed|cancelled) · /.test(trimmed))return source.replace(/오전|오후/g,x=>({en:{오전:'AM',오후:'PM'},ja:{오전:'午前',오후:'午後'},'zh-CN':{오전:'上午',오후:'下午'}})[language][x]);
 return source;
}
export const t=source=>typeof source==='string'?translated(source):source;
export const uiLocale=()=>language;
export const uiConfirm=message=>window.confirm(t(message));
export const uiPrompt=(message,value)=>window.prompt(t(message),value);
export function userOption(label,value){const option=new Option(label,value);option.dataset.i18nSkip='';return option}
function excluded(element){
 if(!element||element.closest(protectedAreas))return true;
 if(element.tagName==='OPTION'){
  const select=element.closest('select'),value=element.value;
  if((select?.matches('#asset-project,#llm')&&value)||/^[a-f0-9]{32}$/.test(value)||/^(pic:|named:)/.test(value)||/\.(safetensors|gguf|pt|pth|ckpt|bin)$/i.test(value))return true;
 }
 return false;
}
function translateText(text){
 const parent=text.parentElement;
 if(excluded(parent))return;
 // Anchors and free-form titles are usually filenames, project names or user text.
 if(parent.closest('#chat-list strong'))return;
 let record=records.get(text);
 if(!record||text.nodeValue!==record.last)record={source:text.nodeValue,last:text.nodeValue};
 const next=translated(record.source);
 if(next!==text.nodeValue){
  // Option text is also its value unless explicitly set. Freeze the original value.
  if(parent.tagName==='OPTION'&&!parent.hasAttribute('value'))parent.setAttribute('value',parent.value);
  text.nodeValue=next;
 }
 record.last=text.nodeValue;records.set(text,record);
}
function translateAttributes(element){
 if(excluded(element.tagName==='TEXTAREA'?element.parentElement:element))return;
 let saved=attrs.get(element)||{};
 for(const name of ['placeholder','title','aria-label']){
  const value=element.getAttribute(name);if(value===null)continue;
  let record=saved[name];if(!record||value!==record.last)record={source:value,last:value};
  const next=translated(record.source);if(next!==value)element.setAttribute(name,next);
  record.last=next;saved[name]=record;
 }
 attrs.set(element,saved);
}
function visit(root){
 if(root.nodeType===Node.TEXT_NODE){translateText(root);return}
 if(root.nodeType!==Node.ELEMENT_NODE)return;
 translateAttributes(root);
 const walker=document.createTreeWalker(root,NodeFilter.SHOW_ELEMENT|NodeFilter.SHOW_TEXT);
 while(walker.nextNode()){const n=walker.currentNode;if(n.nodeType===Node.TEXT_NODE)translateText(n);else translateAttributes(n)}
}
function observe(){observer.observe(document.body,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['placeholder','title','aria-label']})}
function refresh(){observer?.disconnect();visit(document.body);document.documentElement.lang=language;const caption=document.querySelector('#ui-language-caption');if(caption)caption.textContent=({ko:'화면 언어',en:'UI language',ja:'表示言語','zh-CN':'界面语言'})[language];observe()}
export async function initI18n(){
 const response=await fetch('/web/ui-translations.json');if(!response.ok)throw Error('UI translation catalog unavailable');dictionary=await response.json();
 for(const [key,value] of Object.entries(dictionary))if(!dictionary[key.trim()])dictionary[key.trim()]=value;
 templates=Object.keys(dictionary).filter(k=>/\{0\}/.test(k)&&k!=='샷 {0}').map(key=>({key,pattern:new RegExp('^'+key.split(/\{\d+\}/).map(x=>x.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('(.+?)')+'$')}));
 const label=document.createElement('label');label.className='ui-language';label.dataset.i18nSkip='';
 const caption=document.createElement('span');caption.id='ui-language-caption';caption.textContent='UI language';
 const select=document.createElement('select');select.id='ui-language';select.setAttribute('aria-label','UI language');
 for(const [value,text] of Object.entries(LANGUAGES)){const o=new Option(text,value);select.append(o)}select.value=language;
 label.append(caption,select);document.querySelector('.header-actions').prepend(label);
 const pending=new Set();
 observer=new MutationObserver(changes=>{
  for(const change of changes){if(change.type==='childList'){for(const n of change.addedNodes)pending.add(n)}else pending.add(change.target)}
  if(scheduled)return;scheduled=true;queueMicrotask(()=>{scheduled=false;observer.disconnect();for(const n of pending)if(n.isConnected)visit(n);pending.clear();observe()});
 });
 select.onchange=()=>{language=select.value;try{localStorage.setItem(KEY,language)}catch{}refresh();window.dispatchEvent(new CustomEvent('studio-ui-language',{detail:language}))};
 refresh();
}
