export function validatePackages(data) {
  if (data.version !== 1 || !Array.isArray(data.packages)) throw new Error('分包清单格式无效');
  const numbers = new Set(),
    urls = new Set();
  for (const p of data.packages) {
    if (
      !Number.isInteger(p.number) ||
      p.number < 1 ||
      numbers.has(p.number) ||
      urls.has(p.url) ||
      !/^bundles\/[0-9-]+\/nef-\d+\.zip$/.test(p.url) ||
      typeof p.name !== 'string' ||
      !Number.isSafeInteger(p.bytes) ||
      p.bytes <= 0 ||
      !Number.isInteger(p.count) ||
      p.count < 1 ||
      p.count > 100 ||
      !/^[a-f0-9]{64}$/.test(p.sha256) ||
      !Array.isArray(p.dates) ||
      !p.dates.length ||
      !p.dates.every((d) => /^\d{4}-\d{1,2}-\d{1,2}$/.test(d))
    )
      throw new Error('分包记录无效');
    numbers.add(p.number);
    urls.add(p.url);
  }
  return [...data.packages].sort((a, b) => a.number - b.number);
}
