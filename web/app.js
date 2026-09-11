import {filterPhotos, formatBytes, safeAsset, validateCatalog} from './catalog.js';
const $ = id => document.getElementById(id);
const pageSize = 48;
let catalog, filtered = [], shown = 0, selectedDate = '', current = -1, lastFocus;
const viewer = $('viewer');
function dateLabel(date) { const parts = date.split('-'); return `${Number(parts[1])}月${Number(parts[2])}日`; }
function setLink(element, file, label, name) {
  element.hidden = !file;
  if (!file) { element.removeAttribute('href'); return; }
  element.href = safeAsset(file.url);
  element.download = name;
  element.textContent = `${label} · ${formatBytes(file.bytes)}`;
}
function openPhoto(index) {
  if (index < 0 || index >= filtered.length) return;
  const p = filtered[index]; current = index;
  $('photo-title').textContent = p.name;
  $('photo-date').textContent = `${p.date} · ${p.width} × ${p.height}`;
  $('position').textContent = `${index + 1} / ${filtered.length}`;
  $('image-error').hidden = true;
  $('large').alt = `${dateLabel(p.date)}，${p.name}`;
  $('large').src = safeAsset(p.preview);
  $('previous').disabled = index === 0;
  $('next').disabled = index === filtered.length - 1;
  setLink($('download-jpg'), p.jpg, '高清 JPG', p.name);
  setLink($('download-nef'), p.nef, 'NEF 原片', p.nef?.name || '原片.NEF');
  if (!viewer.open) { lastFocus = document.activeElement; viewer.showModal(); }
}
function addPage() {
  const fragment = document.createDocumentFragment();
  const end = Math.min(shown + pageSize, filtered.length);
  for (let index = shown; index < end; index++) {
    const p = filtered[index];
    const button = document.createElement('button'); button.className = 'photo'; button.type = 'button';
    button.setAttribute('aria-label', `查看 ${p.name}`);
    const frame = document.createElement('div'); frame.className = 'photo-image';
    const img = document.createElement('img'); img.src = safeAsset(p.thumb); img.alt = p.name; img.loading = 'lazy'; img.decoding = 'async'; img.width = 480; img.height = 360;
    img.addEventListener('error', () => { img.alt = `${p.name} · 缩略图暂不可用`; });
    frame.append(img);
    if (p.nef) { const badge = document.createElement('span'); badge.className = 'raw'; badge.textContent = 'JPG + NEF'; frame.append(badge); }
    const info = document.createElement('div'); info.className = 'photo-info';
    const name = document.createElement('span'); name.className = 'photo-name'; name.textContent = p.name;
    const time = document.createElement('time'); time.dateTime = p.date; time.textContent = dateLabel(p.date);
    info.append(name, time); button.append(frame, info); button.addEventListener('click', () => openPhoto(index)); fragment.append(button);
  }
  $('gallery').append(fragment); shown = end; $('more').hidden = shown >= filtered.length;
  $('more').textContent = `加载更多 · 还有 ${filtered.length - shown} 张`;
}
function render() {
  if (!catalog) return;
  filtered = filterPhotos(catalog.photos, selectedDate, $('search').value); shown = 0;
  $('gallery').replaceChildren(); $('result-count').textContent = `${filtered.length} 张`;
  $('empty').hidden = filtered.length > 0; $('status').textContent = '';
  const waiting = !catalog.photos.length || (selectedDate && !catalog.photos.some(p => p.date === selectedDate));
  $('empty-title').textContent = waiting ? '照片正在整理中' : '没有找到这张照片';
  $('empty-text').textContent = waiting ? '高清照片准备好后，会分批上传到这里。过几天再来看看。' : '试试其他日期，或输入照片编号的一部分，例如 DSC_3901。';
  $('retry').textContent = waiting ? '刷新相册' : '清除筛选';
  $('retry').onclick = waiting ? load : () => { selectedDate = ''; $('search').value = ''; buildDates(); render(); };
  addPage();
}
function buildDates() {
  $('dates').replaceChildren();
  for (const date of ['', ...catalog.dates]) {
    const button = document.createElement('button'); button.type = 'button'; button.className = 'date';
    button.textContent = date ? dateLabel(date) : '全部日期'; button.setAttribute('aria-pressed', String(date === selectedDate));
    button.onclick = () => { selectedDate = date; for (const el of $('dates').children) el.setAttribute('aria-pressed', String(el === button)); render(); };
    $('dates').append(button);
  }
}
async function load() {
  $('status').textContent = '正在读取相册…'; $('retry').disabled = true;
  try {
    const response = await fetch('catalog.json', {cache: 'no-cache'});
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    catalog = validateCatalog(await response.json());
    if (!catalog.dates.includes(selectedDate)) selectedDate = '';
    $('title').replaceChildren(document.createTextNode(catalog.title));
    const dot = document.createElement('span'); dot.className = 'title-dot'; dot.textContent = '.'; $('title').append(dot);
    document.title = `${catalog.title} · 荔枝镜头`;
    $('total').textContent = catalog.photos.length.toLocaleString('zh-CN');
    $('intro-text').textContent = catalog.photos.length ? '找到喜欢的瞬间，把高清照片带走。' : '照片陆续整理中，留住每一个在场的瞬间。';
    $('updated').textContent = catalog.updated ? `更新于 ${catalog.updated.slice(0, 10)}` : '照片分批更新';
    buildDates(); render();
  } catch (error) {
    catalog = undefined; $('gallery').replaceChildren(); $('dates').replaceChildren(); $('more').hidden = true; $('empty').hidden = false;
    $('status').textContent = '相册暂时无法读取。'; $('empty-title').textContent = '连接没有成功'; $('empty-text').textContent = '请检查网络后重试，或稍后再次打开分享链接。'; $('retry').textContent = '重新加载'; $('retry').onclick = load;
  } finally { $('retry').disabled = false; }
}
$('search').addEventListener('input', render); $('more').onclick = addPage;
$('close').onclick = () => viewer.close(); $('previous').onclick = () => openPhoto(current - 1); $('next').onclick = () => openPhoto(current + 1);
$('large').onerror = () => { $('image-error').hidden = false; };
viewer.addEventListener('close', () => { $('large').removeAttribute('src'); lastFocus?.focus(); });
viewer.addEventListener('click', event => { if (event.target === viewer) { const r = viewer.getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) viewer.close(); } });
document.addEventListener('keydown', event => { if (viewer.open && ['ArrowLeft','ArrowRight'].includes(event.key)) { event.preventDefault(); openPhoto(current + (event.key === 'ArrowLeft' ? -1 : 1)); } });
load();
