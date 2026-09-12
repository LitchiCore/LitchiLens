// 离线提取匿名人脸向量；输出必须放在站点公开目录之外。
import fs from 'node:fs';
import path from 'node:path';
import {createRequire} from 'node:module';
import {pathToFileURL, fileURLToPath} from 'node:url';
import sharp from 'sharp';
import {faceConfig} from '../web/face-config.js';
const require = createRequire(import.meta.url);
const {Human} = require(path.resolve('node_modules/@vladmandic/human/dist/human.node-wasm.js'));
const [siteArg, outArg, limitArg='0', shardArg='0', shardsArg='1'] = process.argv.slice(2);
if (!siteArg || !outArg) throw new Error('参数：站点目录 私有人脸索引 [测试数量]');
const site = path.resolve(siteArg), output = path.resolve(outArg);
if (output.startsWith(site + path.sep)) throw new Error('人脸特征不能输出到公开站点目录');
const modelPath = path.resolve('node_modules/@vladmandic/human/models').replaceAll('\\','/');
const nativeFetch = globalThis.fetch;
globalThis.fetch = async (url, options) => {
  if (String(url).startsWith('file:')) {
    const file = path.resolve(fileURLToPath(String(url)));
    if (!file.startsWith(path.resolve(modelPath) + path.sep)) throw new Error('模型文件越界');
    return new Response(fs.readFileSync(file), {headers:{'content-type':file.endsWith('.json')?'application/json':'application/octet-stream'}});
  }
  return nativeFetch(url, options);
};
const human = new Human({...faceConfig(pathToFileURL(modelPath + '/').href, 'wasm'),
  wasmPath: path.resolve('node_modules/@tensorflow/tfjs-backend-wasm/dist').replaceAll('\\','/') + '/',
  wasmPlatformFetch: false});
await human.load(); await human.tf.ready();
const catalog = JSON.parse(fs.readFileSync(path.join(site, 'catalog.json')));
const previous = fs.existsSync(output) ? JSON.parse(fs.readFileSync(output)) : {photos: []};
const cache = new Map((previous.pipeline==='overlap-tiles-v2'?previous.photos:[]).map(p => [p.id, p]));
const results = [];
const allPhotos = Number(limitArg)>0 ? catalog.photos.slice(0, Number(limitArg)) : catalog.photos;
const photos = allPhotos.filter((p,i)=>i%Number(shardsArg)===Number(shardArg));
for (const [index, photo] of photos.entries()) {
  // 同一 ID 只为默认版本建索引，返回结果时可选择全部版本。
  if (cache.get(photo.id)?.preview === photo.preview) results.push(cache.get(photo.id));
  else {
    const file = path.resolve(site, photo.preview);
    if (!file.startsWith(site + path.sep)) throw new Error('预览路径越界');
    const normalized=await sharp(file).rotate().resize({width:1920,height:1920,fit:'inside',withoutEnlargement:true}).removeAlpha().png().toBuffer();
    const metadata=await sharp(normalized).metadata();
    const windows=[{left:0,top:0,width:metadata.width,height:metadata.height}];
    if(Math.max(metadata.width,metadata.height)>1000){
      const w=Math.min(metadata.width,Math.ceil(metadata.width*0.62)),h=Math.min(metadata.height,Math.ceil(metadata.height*0.62));
      for(const left of [0,metadata.width-w])for(const top of [0,metadata.height-h])windows.push({left,top,width:w,height:h});
    }
    const faces=[];
    for(const window of windows){
      const {data,info}=await sharp(normalized).extract(window).resize({width:1600,height:1600,fit:'inside',withoutEnlargement:true}).raw().toBuffer({resolveWithObject:true});
      const tensor=human.tf.tensor4d(data,[1,info.height,info.width,3],'float32');
      const found=await human.detect(tensor);tensor.dispose();
      if(found.error)throw new Error(found.error);
      for(const f of found.face.filter(f=>f.embedding?.length===1024&&f.boxScore>=0.6)){
        const scale=window.width/info.width;
        const box=[f.box[0]*scale+window.left,f.box[1]*scale+window.top,f.box[2]*scale,f.box[3]*scale];
        const duplicate=faces.some(previous=>{const a=previous.box;const intersection=Math.max(0,Math.min(a[0]+a[2],box[0]+box[2])-Math.max(a[0],box[0]))*Math.max(0,Math.min(a[1]+a[3],box[1]+box[3])-Math.max(a[1],box[1]));return intersection/Math.min(a[2]*a[3],box[2]*box[3])>0.5;});
        if(!duplicate)faces.push({box,embedding:Array.from(f.embedding)});
      }
    }
    results.push({id:photo.id,preview:photo.preview,faces});
  }
  if ((index + 1) % 10 === 0 || index + 1 === photos.length) {
    fs.mkdirSync(path.dirname(output),{recursive:true});
    fs.writeFileSync(output+'.tmp',JSON.stringify({version:1,pipeline:'overlap-tiles-v2',model:'human-3.3.6-faceres',photos:results}));
    fs.renameSync(output+'.tmp',output);
    console.log(`人脸索引 ${index+1}/${photos.length}；累计 ${results.reduce((n,p)=>n+p.faces.length,0)} 张脸`);
  }
}
