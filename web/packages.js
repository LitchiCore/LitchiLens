import { validatePackages } from './packages-data.js';
const $ = (id) => document.getElementById(id);
let packages = [];
const size = (bytes) => `${(bytes / 1024 ** 3).toFixed(2)} GiB`;
async function load() {
  $('copy').disabled = true;
  $('notice').textContent = '';
  $('links').hidden = true;
  try {
    const response = await fetch('bundles/packages.json', { cache: 'no-cache' });
    if (!response.ok) throw new Error('分包清单暂不可用');
    packages = validatePackages(await response.json());
    $('packages').replaceChildren();
    $('bundle-empty').hidden = packages.length > 0;
    $('summary').textContent =
      `${packages.length} 个分包 · ${packages.reduce((n, p) => n + p.count, 0)} 张 NEF · 共 ${size(packages.reduce((n, p) => n + p.bytes, 0))}`;
    for (const p of packages) {
      const card = document.createElement('article');
      card.className = 'package';
      const number = document.createElement('span');
      number.className = 'package-number';
      number.textContent = String(p.number).padStart(2, '0');
      const body = document.createElement('div');
      body.className = 'package-content';
      const title = document.createElement('h2');
      title.textContent = `第 ${p.number} 包 · ${p.count} 张原片`;
      const meta = document.createElement('p');
      meta.className = 'package-meta';
      meta.textContent = `${p.dates[0]}${p.dates.length > 1 ? ' 至 ' + p.dates.at(-1) : ''} · ${size(p.bytes)}`;
      const link = document.createElement('a');
      link.className = 'button primary';
      link.href = p.url;
      link.download = p.name;
      link.textContent = `下载 ZIP · ${size(p.bytes)}`;
      const details = document.createElement('details');
      const label = document.createElement('summary');
      label.textContent = '文件完整性校验（SHA-256）';
      const checksum = document.createElement('code');
      checksum.textContent = p.sha256;
      details.append(label, checksum);
      body.append(title, meta, link, details);
      card.append(number, body);
      $('packages').append(card);
    }
    $('copy').disabled = !packages.length;
  } catch {
    packages = [];
    $('packages').replaceChildren();
    $('bundle-empty').hidden = false;
    $('summary').textContent = '分包暂时无法读取';
    $('notice').textContent = '请检查网络后重新加载。';
  }
}
$('copy').onclick = async () => {
  const links = packages.map((p) => new URL(p.url, location.href).href).join('\n');
  try {
    await navigator.clipboard.writeText(links);
    $('notice').textContent = '已复制全部链接，可粘贴到下载工具。';
  } catch {
    $('links').value = links;
    $('links').hidden = false;
    $('links').focus();
    $('links').select();
    $('notice').textContent = '请复制下方链接。';
  }
};
$('reload').onclick = load;
load();
