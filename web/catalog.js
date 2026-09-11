// 相册纯数据逻辑，浏览器与 Node 验证共用。
export function filterPhotos(photos, date, query) {
  const needle = query.trim().toLocaleLowerCase();
  return photos.filter(p => (!date || p.date === date) && (!needle || p.name.toLocaleLowerCase().includes(needle)));
}
export function formatBytes(bytes) {
  if (!Number.isFinite(bytes) || bytes < 0) return '';
  return bytes >= 1024 ** 3 ? `${(bytes / 1024 ** 3).toFixed(1)} GB` : `${(bytes / 1024 ** 2).toFixed(1)} MB`;
}
export function safeAsset(path) {
  // 只允许构建器生成的相对文件路径，分享前缀不可被跳过。
  if (typeof path !== 'string' || !/^(media|downloads)\/[a-f0-9-]+\.(jpg|nef)$/.test(path)) throw new Error('照片路径无效');
  return path;
}
export function validateCatalog(data) {
  if (data.version !== 1 || !Array.isArray(data.photos) || !Array.isArray(data.dates)) throw new Error('相册索引格式不受支持');
  if (typeof data.title !== 'string' || !data.dates.every(d => /^\d{4}-\d{2}-\d{2}$/.test(d))) throw new Error('相册信息不完整');
  const ids = new Set();
  for (const p of data.photos) {
    if (typeof p.id !== 'string' || ids.has(p.id) || typeof p.name !== 'string' || !data.dates.includes(p.date)) throw new Error('照片信息不完整');
    ids.add(p.id);
    safeAsset(p.thumb); safeAsset(p.preview); safeAsset(p.jpg?.url);
    if (p.nef) safeAsset(p.nef.url);
  }
  return data;
}
