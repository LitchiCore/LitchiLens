import { faceConfig } from './face-config.js';
const $ = (id) => document.getElementById(id);
let humanPromise,
  generation = 0;
function clear() {
  generation++;
  $('face-choices').replaceChildren();
  $('clear-face').hidden = true;
  $('face-status').textContent = '本次自拍和候选特征已清除。';
}
$('clear-face').onclick = clear;
async function model() {
  if (!humanPromise)
    humanPromise = (async () => {
      $('face-status').textContent = '正在加载本地人脸模型，首次使用稍慢…';
      // 模型同样限流，忙时自动重试，不挤占照片浏览带宽。
      const nativeFetch = globalThis.fetch;
      globalThis.fetch = async (url, options) => {
        if (!String(url).includes('/vendor/')) return nativeFetch(url, options);
        for (let n = 0; n < 10; n++) {
          const response = await nativeFetch(url, options);
          if (response.status !== 429 || n === 9) return response;
          await new Promise((resolve) => setTimeout(resolve, 3000 + Math.random() * 3000));
        }
      };
      try {
        const moduleResponse = await globalThis.fetch(
          new URL('vendor/human.esm.js', location.href.split('#')[0]).href,
          { cache: 'force-cache' },
        );
        if (!moduleResponse.ok) throw new Error('人脸模型下载繁忙，请稍后再试。');
        await moduleResponse.arrayBuffer();
        const { Human } = await import('./vendor/human.esm.js');
        const human = new Human(
          faceConfig(new URL('vendor/models/', location.href.split('#')[0]).href),
        );
        await human.load();
        await human.tf.ready();
        return human;
      } finally {
        globalThis.fetch = nativeFetch;
      }
    })().catch((e) => {
      humanPromise = null;
      throw e;
    });
  return humanPromise;
}
export async function findSelfie(file, onEmbedding) {
  clear();
  const ticket = generation;
  if (file.size > 30_000_000)
    throw new Error('自拍超过 30MB，请先在相册中缩小，避免手机内存不足。');
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type))
    throw new Error('请使用 JPG、PNG 或 WebP 自拍。');
  let bitmap;
  try {
    bitmap = await createImageBitmap(file, { imageOrientation: 'from-image' });
  } catch {
    throw new Error('无法读取照片，请转换为 JPG 后重试。');
  }
  const scale = Math.min(1, 1600 / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext('2d').drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  bitmap.close();
  try {
    const human = await model();
    if (ticket !== generation) return;
    $('face-status').textContent = '正在手机本地提取人脸特征…';
    const result = await human.detect(canvas);
    if (ticket !== generation) return;
    const faces = result.face.filter((f) => f.embedding?.length === 1024 && f.boxScore >= 0.6);
    if (!faces.length) throw new Error('没有找到清晰人脸，请换一张正脸、光线充足的自拍。');
    const submit = async (face) => {
      if (ticket !== generation) return;
      $('face-status').textContent = '正在查找相似照片…';
      try {
        await onEmbedding(Array.from(face.embedding));
        clear();
      } catch (e) {
        $('face-status').textContent = e.message;
      }
    };
    if (faces.length === 1) await submit(faces[0]);
    else {
      $('face-status').textContent = '检测到多张脸，请点选你自己。';
      $('clear-face').hidden = false;
      for (const face of faces) {
        const button = document.createElement('button');
        button.className = 'face-choice';
        button.setAttribute('aria-label', '用这张脸查找');
        const thumb = document.createElement('canvas');
        thumb.width = 112;
        thumb.height = 112;
        const [x, y, w, h] = face.box;
        thumb.getContext('2d').drawImage(canvas, x, y, w, h, 0, 0, 112, 112);
        button.append(thumb);
        button.onclick = () => submit(face);
        $('face-choices').append(button);
      }
    }
  } finally {
    canvas.width = 0;
    canvas.height = 0;
  }
}
