import {filterPhotos, formatBytes, safeAsset, validateCatalog} from './catalog.js';
const $ = id => document.getElementById(id);
let catalog, filtered=[], shown=0, day='', current=-1, selected=new Set(), actionIds=[], matches=null, loading;
let lastFocus;
const pageSize=48;
const visitor=crypto.randomUUID();
async function traffic(){if(document.hidden)return;try{const r=await fetch(`api/presence?id=${visitor}`,{cache:'no-store'});if(!r.ok)throw Error();const t=await r.json();$('traffic').textContent=`在线约 ${t.visitors} 人 · 下载 ${t.downloads}/${t.download_limit}`;$('traffic').title='在线人数按最近 90 秒活跃浏览器会话估算；下载为正在传输的任务数。';if(catalog&&t.revision!==catalog.revision&&!document.querySelector('dialog[open]'))await load();}catch{$('traffic').textContent='在线状态暂不可用';}}
traffic();setInterval(traffic,20000);
export async function post(route,data) {
  const response=await fetch(`api/${route}`,{method:'POST',headers:{'Content-Type':'application/json','X-LitchiLens':'1'},body:JSON.stringify(data)});
  const result=await response.json();
  if(!response.ok) throw new Error(result.error || '操作失败，请重试');
  return result;
}
function modal(id) {lastFocus=document.activeElement; $(id).showModal();}
$('sponsor-open').onclick=()=>{$('sponsor-image').src='sponsor.png';modal('sponsor-dialog');};
function updateSelection() {
  $('selection').hidden=!selected.size;
  $('selection-count').textContent=`已选 ${selected.size} 张`;
}
function choose(id, checked) {
  if(checked && selected.size>=100) {$('status').textContent='一次最多选择 100 张。'; return false;}
  if(checked) selected.add(id); else selected.delete(id);
  updateSelection(); return true;
}
function variant(photo) {return photo.versions.find(v=>v.label===$('version-filter').value) || photo.versions[0];}
function addPage() {
  const fragment=document.createDocumentFragment();
  const end=Math.min(shown+pageSize,filtered.length);
  for(let i=shown;i<end;i++) {
    const p=filtered[i], v=variant(p);
    const card=document.createElement('article');card.className='photo-card';
    const button=document.createElement('button');button.className='photo';button.type='button';button.setAttribute('aria-label',`查看 ${p.id}`);
    const frame=document.createElement('div');frame.className='photo-image';
    const img=new Image(480,360);img.src=safeAsset(v.thumb);img.alt=p.name;img.loading='lazy';img.decoding='async';frame.append(img);
    let retries=0;img.onerror=()=>{if(retries++<2)setTimeout(()=>{if(img.isConnected)img.src=safeAsset(v.thumb)+`?retry=${retries}`;},1500*retries);else img.alt=p.name+' · 暂时无法读取';};
    const badge=document.createElement('span');badge.className='raw';badge.textContent=`${v.label} · ${p.versions.length} 个版本`;frame.append(badge);
    const info=document.createElement('div');info.className='photo-info';
    const name=document.createElement('span');name.className='photo-name';name.textContent=p.name;
    const date=document.createElement('time');date.dateTime=p.date;date.textContent=p.date.slice(5);info.append(name,date);
    button.append(frame,info);button.onclick=()=>openPhoto(i);
    const label=document.createElement('label');label.className='check-photo';
    const check=document.createElement('input');check.type='checkbox';check.checked=selected.has(p.id);check.setAttribute('aria-label',`勾选 ${p.id}`);check.onchange=()=>{if(!choose(p.id,check.checked))check.checked=false;};
    label.append(check);card.append(button,label);fragment.append(card);
  }
  $('gallery').append(fragment);shown=end;$('more').hidden=shown>=filtered.length;
  $('more').textContent=`加载更多 · 剩余 ${filtered.length-shown} 张`;
}
function render() {
  if(!catalog)return;
  filtered=filterPhotos(catalog.photos,day,$('search').value).filter(p=>(!matches||matches.has(p.id))&&(!$('version-filter').value||p.versions.some(v=>v.label===$('version-filter').value)));
  if(matches) filtered.sort((a,b)=>matches.get(b.id)-matches.get(a.id));
  shown=0;$('gallery').replaceChildren();$('result-count').textContent=`${filtered.length} 个 ID`;
  $('list-title').textContent=matches?'可能有你的照片':'全部照片';$('clear-matches').hidden=!matches;
  $('status').textContent=filtered.length?'':'没有符合条件的照片，试试其他日期或版本。';
  addPage();updateSelection();
}
function buildDates() {
  $('dates').replaceChildren();
  for(const value of ['',...catalog.dates]) {
    const button=document.createElement('button');button.className='date';button.textContent=value?value.slice(5).replace('-','月')+'日':'全部日期';button.setAttribute('aria-pressed',String(day===value));
    button.onclick=()=>{day=value;buildDates();render();};$('dates').append(button);
  }
}
async function load() {
  if(loading)return loading;
  loading=(async()=>{
    try {
      const response=await fetch('catalog.json',{cache:'no-store'});if(!response.ok)throw new Error('照片库连接失败');
      const nextCatalog=validateCatalog(await response.json());
      if(catalog && JSON.stringify(catalog)===JSON.stringify(nextCatalog))return;
      catalog=nextCatalog;
      const available=new Set(catalog.photos.map(p=>p.id));selected=new Set([...selected].filter(i=>available.has(i)));
      $('total').textContent=catalog.photos.length.toLocaleString('zh-CN');$('updated').textContent=`更新于 ${catalog.updated.slice(0,10)}`;
      buildDates();render();
    }catch(error){$('status').textContent=error.message+'，请刷新重试。';}
    finally{loading=null;}
  })();return loading;
}
function showVersion() {
  const p=filtered[current],v=p.versions[Number($('photo-version').value)];
  $('large').src=safeAsset(v.preview);$('large').alt=p.id;
  $('photo-date').textContent=`${p.date} · ${v.width} × ${v.height} · ${v.label}`;
  $('download-jpg').href=safeAsset(v.jpg.url);$('download-jpg').download=`${p.id}-${v.label}.jpg`;
  $('download-jpg').textContent=`下载 JPG · ${formatBytes(v.jpg.bytes)}`;
}
function openPhoto(index) {
  if(index<0||index>=filtered.length)return;
  current=index;const p=filtered[index];$('photo-title').textContent=p.id;$('photo-version').replaceChildren();
  p.versions.forEach((v,i)=>{const opt=new Option(v.label,String(i));$('photo-version').append(opt);});
  $('photo-version').value=String(Math.max(0,p.versions.findIndex(v=>v.label===$('version-filter').value)));
  $('previous').disabled=index===0;$('next').disabled=index===filtered.length-1;$('raw-open').hidden=!p.nef;
  showVersion();if(!$('viewer').open)modal('viewer');
}
function feedback(ids) {
  actionIds=[...ids];$('reason').value='';$('feedback-status').textContent='';modal('feedback-dialog');
}
function download(ids,kind='jpg') {
  actionIds=[...ids];$('download-kind').value=kind;$('zip-link').hidden=true;$('download-status').textContent='';$('prepare-download').hidden=false;
  $('raw-note').hidden=kind!=='nef';modal('download-dialog');
}
async function route() {
  const hash=location.hash || '#home';$('home').hidden=hash!=='#home';$('find').hidden=hash!=='#find';$('library').hidden=hash!=='#library';
  if(hash==='#library'&&!catalog)await load();
  if(hash==='#find') {
    try {const response=await fetch('api/status',{cache:'no-store'});const data=await response.json();$('face-status').textContent=data.faces_ready?'请选择自拍开始查找。':'人脸索引正在准备，你可以先浏览照片库。';$('selfie').disabled=!data.faces_ready;}
    catch{$('face-status').textContent='无法连接检索服务，请稍后重试。';}
  }
}
$('search').oninput=render;$('version-filter').onchange=render;$('more').onclick=addPage;
$('clear-selection').onclick=()=>{selected.clear();render();};
$('select-page').onclick=()=>{for(const p of filtered.slice(0,shown)){if(selected.size>=100)break;selected.add(p.id);}render();};
$('clear-matches').onclick=()=>{matches=null;render();};
$('batch-download').onclick=()=>download(selected);$('unhappy').onclick=()=>feedback(selected);
$('photo-unhappy').onclick=()=>feedback([filtered[current].id]);$('raw-open').onclick=()=>download([filtered[current].id],'nef');
$('photo-version').onchange=showVersion;$('close').onclick=()=>$('viewer').close();
$('previous').onclick=()=>openPhoto(current-1);$('next').onclick=()=>openPhoto(current+1);
$('download-kind').onchange=()=>{$('raw-note').hidden=$('download-kind').value!=='nef';$('zip-link').hidden=true;$('prepare-download').hidden=false;};
$('prepare-download').onclick=async()=>{
  $('prepare-download').disabled=true;$('download-status').textContent='正在准备…';
  try{const result=await post('download',{ids:actionIds,kind:$('download-kind').value});$('zip-link').href=result.url;$('zip-link').hidden=false;$('prepare-download').hidden=true;$('download-status').textContent=`包含 ${result.count} 张。${result.missing?`${result.missing} 张没有所选版本或已下架。`:''}点击保存 ZIP 开始下载。`;}
  catch(e){$('download-status').textContent=e.message;}finally{$('prepare-download').disabled=false;}
};
$('submit-recolor').onclick=async()=>{
  if(!$('reason').value.trim()){$('feedback-status').textContent='请简单写下希望如何调整。';return;}
  $('submit-recolor').disabled=true;
  try{const r=await post('recolor',{ids:actionIds,reason:$('reason').value});$('feedback-status').textContent=`已提交给拍摄者，申请编号 ${r.request_id}。`;}
  catch(e){$('feedback-status').textContent=e.message;}finally{$('submit-recolor').disabled=false;}
};
$('ask-hide').onclick=()=>{$('hide-summary').textContent=`你选中了 ${actionIds.length} 个照片 ID：${actionIds.slice(0,5).join('、')}${actionIds.length>5?'…':''}`;$('hide-confirm').checked=false;$('submit-hide').disabled=true;$('hide-status').textContent='';modal('hide-dialog');};
$('hide-confirm').onchange=()=>{$('submit-hide').disabled=!$('hide-confirm').checked;};
$('submit-hide').onclick=async()=>{
  $('submit-hide').disabled=true;
  try{const r=await post('hide',{ids:actionIds,confirmed:$('hide-confirm').checked});for(const id of r.hidden)selected.delete(id);$('hide-dialog').close();$('feedback-dialog').close();if($('viewer').open)$('viewer').close();await load();$('status').textContent=`已下架 ${r.hidden.length} 个照片 ID 的全部版本。`;}
  catch(e){$('hide-status').textContent=e.message;$('submit-hide').disabled=false;}
};
for(const button of document.querySelectorAll('[data-close]'))button.onclick=()=>$(button.dataset.close).close();
for(const dialog of document.querySelectorAll('dialog'))dialog.addEventListener('close',()=>lastFocus?.focus());
document.addEventListener('keydown',e=>{if($('viewer').open&&!$('feedback-dialog').open&&!$('download-dialog').open&&['ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();openPhoto(current+(e.key==='ArrowLeft'?-1:1));}});
window.addEventListener('hashchange',route);
// 查询模块只有选择自拍时才下载，不增加首页和照片库首屏负担。
$('selfie').onchange=async()=>{
  const file=$('selfie').files[0];if(!file)return;
  $('selfie').disabled=true;
  try{const {findSelfie}=await import('./find-face.js');await findSelfie(file,async embedding=>{const data=await post('search',{embedding});matches=new Map(data.matches.map(m=>[m.id,m.score]));day='';$('search').value='';$('version-filter').value='';await load();location.hash='library';render();$('status').textContent=data.matches.length?'这些是相似候选，请自己确认。':'暂时没找到相似候选，可以换一张自拍或按日期浏览。';});}
  catch(e){$('face-status').textContent=e.message;}finally{$('selfie').disabled=false;$('selfie').value='';}
};
document.addEventListener('visibilitychange',()=>{if(!document.hidden)traffic();});
route();
