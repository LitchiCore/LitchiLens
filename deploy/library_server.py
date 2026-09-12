#!/usr/bin/env python3
"""照片库的小型 API：全站隐藏、调色申请、流式下载和匿名人脸候选检索。"""
import argparse
from array import array
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import hashlib
import math
import os
from pathlib import Path
import re
import secrets
import threading
import time
from urllib.parse import urlsplit,parse_qs
import zipfile

class BoundedHTTPServer(ThreadingHTTPServer):
    request_queue_size=512
    daemon_threads=True
    def __init__(self,*args,**kwargs):
        self.slots=threading.BoundedSemaphore(48)
        super().__init__(*args,**kwargs)
    def process_request(self,request,address):
        self.slots.acquire()
        request.settimeout(60)
        try:super().process_request(request,address)
        except Exception:
            self.slots.release()
            raise
    def process_request_thread(self,request,address):
        try:super().process_request_thread(request,address)
        finally:self.slots.release()

class Library:
    def __init__(self, site, state, faces=None, completion_log=None):
        self.site, self.state_path = Path(site).resolve(strict=True), Path(state)
        self.lock = threading.RLock()
        self.catalog = json.loads((self.site / 'catalog.json').read_text(encoding='utf-8'))
        if self.catalog.get('version') != 2:
            raise ValueError('需要第二版照片库索引')
        self.photos, self.assets = {}, {}
        for photo in self.catalog['photos']:
            identity = photo['id']
            if not re.fullmatch(r'\d{4}-\d{2}-\d{2}_[A-Z0-9_-]+', identity) or identity in self.photos:
                raise ValueError('照片 ID 无效或重复')
            self.photos[identity] = photo
            for version in photo['versions']:
                for asset in (version['thumb'],version['preview'],version['jpg']['url']):
                    self.add_asset(asset, identity)
            if photo.get('nef'):
                self.add_asset(photo['nef']['url'], identity)
        self.state = json.loads(self.state_path.read_text(encoding='utf-8')) if self.state_path.exists() else {'hidden':{}, 'requests':[]}
        self.refresh_revision()
        self.tickets = {}
        self.visitors, self.downloads = {}, {}
        self.completion_log = Path(completion_log) if completion_log else None
        self.log_offset = self.completion_log.stat().st_size if self.completion_log and self.completion_log.exists() else 0
        self.faces = []
        if faces and Path(faces).exists():
            data = json.loads(Path(faces).read_text(encoding='utf-8'))
            if data.get('model') != 'human-3.3.6-faceres':
                raise ValueError('人脸模型版本不匹配')
            for photo in data['photos']:
                if photo['id'] in self.photos and photo['preview'] == self.photos[photo['id']]['preview']:
                    for face in photo['faces']:
                        vector=face['embedding']
                        if len(vector)!=1024 or not all(type(v) in (int,float) and math.isfinite(v) for v in vector):
                            raise ValueError('人脸索引向量无效')
                        self.faces.append((photo['id'], array('f',vector)))

    def add_asset(self, asset, identity):
        if not re.fullmatch(r'(media|downloads)/[a-f0-9-]+\.(jpg|nef)',asset):
            raise ValueError('资产路径无效')
        file = (self.site / asset).resolve(strict=True)
        if not file.is_relative_to(self.site) or not file.is_file():
            raise ValueError('资产不存在或越界')
        self.assets.setdefault(asset,set()).add(identity)

    def persist(self):
        self.state_path.parent.mkdir(parents=True,exist_ok=True)
        temp = self.state_path.with_suffix('.tmp')
        with temp.open('w',encoding='utf-8') as handle:
            json.dump(self.state,handle,ensure_ascii=False)
            handle.flush(); os.fsync(handle.fileno())
        os.replace(temp,self.state_path)
        self.refresh_revision()

    def refresh_revision(self):
        self.revision=str(self.catalog.get('updated',''))+':'+hashlib.sha256(json.dumps(sorted(self.state['hidden'])).encode()).hexdigest()[:12]

    def traffic(self, visitor=None):
        now=time.time()
        self.visitors={k:v for k,v in self.visitors.items() if v>now-90}
        if visitor and re.fullmatch(r'[a-f0-9-]{36}',visitor) and len(self.visitors)<5000:self.visitors[visitor]=now
        self.downloads={k:v for k,v in self.downloads.items() if v>now-10800}
        if self.completion_log and self.completion_log.exists():
            if self.completion_log.stat().st_size<self.log_offset:self.log_offset=0
            with self.completion_log.open() as handle:
                handle.seek(self.log_offset)
                for line in handle:
                    try:self.downloads.pop(json.loads(line)['id'],None)
                    except (ValueError,KeyError):pass
                self.log_offset=handle.tell()
        return {'visitors':len(self.visitors),'downloads':len(self.downloads),'download_limit':4,'visitors_estimated':True,'revision':self.revision}

    def visible(self, identity):
        return identity in self.photos and identity not in self.state['hidden']

    def ids(self, data):
        ids = data.get('ids')
        if not isinstance(ids,list) or not 1 <= len(ids) <= 100 or not all(isinstance(i,str) and i in self.photos for i in ids):
            raise ValueError('请选择 1 至 100 个有效照片 ID')
        return list(dict.fromkeys(ids))

    def selected_files(self, ids, kind):
        result = []
        labels = {'standard':'标准转换','edited':'批量调色','retouched':'精调'}
        for identity in ids:
            if not self.visible(identity):
                continue
            p = self.photos[identity]
            if kind == 'nef':
                file = p.get('nef')
                if file: result.append((identity,file['url'],identity+'.NEF'))
            else:
                variants = p['versions'] if kind == 'jpg' else [v for v in p['versions'] if v['label'] == labels[kind]]
                if variants:
                    v = variants[0]
                    result.append((identity,v['jpg']['url'],identity+'.jpg'))
        return result

def handler(library):
    class Handler(BaseHTTPRequestHandler):
        server_version = 'LitchiLens'
        def log_message(self,*args):
            pass  # 不记录查询内容、特征和用户地址。

        def reply(self,status,data,head=False):
            payload = json.dumps(data,ensure_ascii=False,separators=(',',':')).encode()
            self.send_response(status)
            self.send_header('Content-Type','application/json; charset=utf-8')
            self.send_header('Cache-Control','no-store')
            self.send_header('Content-Length',str(len(payload)))
            self.end_headers()
            if not head: self.wfile.write(payload)

        def do_HEAD(self):
            self.do_GET(head=True)

        def do_GET(self,head=False):
            route = urlsplit(self.path).path.lstrip('/')
            if route == 'catalog.json':
                with library.lock:
                    data = dict(library.catalog,revision=library.revision,photos=[p for p in library.catalog['photos'] if library.visible(p['id'])])
                # 大目录序列化与网络写入不占用状态锁，慢连接不会阻塞下架和留言。
                return self.reply(200,data,head)
            with library.lock:
                if route == 'api/status':
                    return self.reply(200,{'faces_ready':bool(library.faces),'face_photos':len({i for i,_ in library.faces if library.visible(i)})},head)
                if route == 'api/presence':
                    visitor=parse_qs(urlsplit(self.path).query).get('id',[''])[0]
                    return self.reply(200,library.traffic(visitor),head)
                if route.startswith(('media/','downloads/')):
                    owners = library.assets.get(route,set())
                    if not any(library.visible(i) for i in owners): return self.reply(404,{'error':'照片不存在或已隐藏'},head)
                    if route.startswith('downloads/') and not head:
                        request_id=self.headers.get('X-Request-Id','')
                        if re.fullmatch(r'[a-f0-9]{32}',request_id):library.downloads[request_id]=time.time()
                    self.send_response(200)
                    self.send_header('X-Accel-Redirect','/__litchilens_assets/'+route)
                    self.send_header('Cache-Control','no-store')
                    if route.startswith('downloads/'):
                        self.send_header('Content-Disposition','attachment')
                    self.end_headers()
                    return
                if route.startswith('api/download/'):
                    ticket = library.tickets.get(route.rsplit('/',1)[-1])
                    if not ticket or ticket['expires'] < time.time(): return self.reply(410,{'error':'下载链接已过期，请重新选择'},head)
                    files = library.selected_files(ticket['ids'],ticket['kind'])
                    if not files: return self.reply(410,{'error':'所选照片已隐藏或没有此版本'},head)
                else:
                    return self.reply(404,{'error':'页面不存在'},head)
            self.send_response(200)
            self.send_header('Content-Type','application/zip')
            self.send_header('Content-Disposition','attachment; filename="LitchiLens-photos.zip"')
            self.send_header('Cache-Control','no-store')
            self.end_headers()
            if head: return
            request_id=secrets.token_hex(16)
            with library.lock:library.downloads[request_id]=time.time()
            try:
                with zipfile.ZipFile(self.wfile,'w',compression=zipfile.ZIP_STORED,allowZip64=True) as archive:
                    for identity, asset, name in files:
                        with library.lock:
                            if not library.visible(identity): continue
                        archive.write(library.site/asset,name)
            except (BrokenPipeError,ConnectionResetError):
                pass
            finally:
                with library.lock:library.downloads.pop(request_id,None)

        def do_POST(self):
            # JSON + 自定义请求头要求浏览器同源；不提供 CORS。
            origin = self.headers.get('Origin')
            host = self.headers.get('X-Forwarded-Host',self.headers.get('Host'))
            if self.headers.get('X-LitchiLens') != '1' or (origin and origin not in ('https://'+host,'http://'+host)):
                return self.reply(403,{'error':'请在照片网站内操作'})
            if self.headers.get('Content-Type','').split(';')[0] != 'application/json':
                return self.reply(415,{'error':'仅接受 JSON 请求'})
            try:
                size = int(self.headers.get('Content-Length','0'))
                if not 0 < size <= 65536: return self.reply(413,{'error':'请求过大或为空'})
                data = json.loads(self.rfile.read(size))
                if not isinstance(data,dict): raise ValueError('无效请求')
                route = urlsplit(self.path).path
                if route == '/api/search':
                    vector = data.get('embedding')
                    if not isinstance(vector,list) or len(vector) != 1024 or not all(type(x) in (float,int) and math.isfinite(x) and abs(x)<100 for x in vector):
                        raise ValueError('人脸特征无效，请重新选择自拍')
                    if not library.faces: return self.reply(503,{'error':'人脸索引正在准备，请先浏览照片库'})
                    scores = {}
                    with library.lock:
                        hidden = set(library.state['hidden'])
                    for identity, target in library.faces:
                        if identity in hidden: continue
                        squared = sum((a-b)**2 for a,b in zip(vector,target))
                        score = max(0,min(1,(1-math.sqrt(25*squared)/100-0.2)/0.6))
                        if score >= 0.55: scores[identity] = max(scores.get(identity,0),score)
                    with library.lock:
                        matches = [{'id':i,'score':round(s,3)} for i,s in sorted(scores.items(),key=lambda x:-x[1]) if library.visible(i)][:100]
                    return self.reply(200,{'matches':matches,'notice':'相似度只用于排序，不代表身份概率'})
                with library.lock:
                    ids = library.ids(data)
                    now = datetime.now(timezone.utc).isoformat()
                    if route == '/api/hide':
                        if data.get('confirmed') is not True: raise ValueError('需要二次确认')
                        old = dict(library.state['hidden'])
                        for identity in ids: library.state['hidden'][identity] = now
                        try: library.persist()
                        except Exception:
                            library.state['hidden'] = old
                            raise
                        return self.reply(200,{'hidden':ids})
                    if route == '/api/recolor':
                        reason = data.get('reason','')
                        if not isinstance(reason,str) or not 1<=len(reason.strip())<=500: raise ValueError('请填写 1 至 500 字调色需求')
                        ids = [i for i in ids if library.visible(i)]
                        if not ids: raise ValueError('所选照片已隐藏')
                        record = {'id':secrets.token_hex(8),'ids':ids,'reason':reason.strip(),'created':now,'status':'待处理'}
                        library.state['requests'].append(record)
                        try: library.persist()
                        except Exception:
                            library.state['requests'].pop()
                            raise
                        return self.reply(200,{'request_id':record['id']})
                    if route == '/api/download':
                        kind = data.get('kind','jpg')
                        if kind not in ('jpg','nef','standard','edited','retouched'): raise ValueError('下载版本无效')
                        files = library.selected_files(ids,kind)
                        if not files: raise ValueError('所选照片没有此版本，或已经隐藏')
                        library.tickets = {k:v for k,v in library.tickets.items() if v['expires']>time.time()}
                        if len(library.tickets)>2000: return self.reply(429,{'error':'下载繁忙，请稍后重试'})
                        token = secrets.token_urlsafe(24)
                        library.tickets[token] = {'ids':ids,'kind':kind,'expires':time.time()+1800}
                        return self.reply(200,{'url':'api/download/'+token,'count':len(files),'missing':len(ids)-len(files)})
                    return self.reply(404,{'error':'操作不存在'})
            except (ValueError,TypeError,KeyError):
                return self.reply(400,{'error':'请求无效，请检查所选照片、版本和填写内容'})
            except OSError:
                return self.reply(503,{'error':'暂时无法保存，请稍后重试；本次操作未完成'})
    return Handler

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site',required=True)
    parser.add_argument('--state',required=True)
    parser.add_argument('--faces')
    parser.add_argument('--port',type=int,default=8766)
    parser.add_argument('--admin-port',type=int,default=8769)
    parser.add_argument('--completion-log')
    args = parser.parse_args()
    library = Library(args.site,args.state,args.faces,args.completion_log)
    from admin_server import admin_handler
    admin = BoundedHTTPServer(('127.0.0.1',args.admin_port),admin_handler(library))
    threading.Thread(target=admin.serve_forever,daemon=True).start()
    server = BoundedHTTPServer(('127.0.0.1',args.port),handler(library))
    server.daemon_threads = True
    print(f'LitchiLens API 已启动：{len(library.photos)} 个 ID，{len(library.faces)} 张脸',flush=True)
    server.serve_forever()
