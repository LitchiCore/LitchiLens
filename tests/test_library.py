"""真实 HTTP 入口测试：版本绑定、全站隐藏、重启持久化和 ZIP 内容。"""
import io
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
from urllib.request import Request,urlopen
from urllib.error import HTTPError
import zipfile
from concurrent.futures import ThreadPoolExecutor
from http.server import ThreadingHTTPServer
from PIL import Image

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'deploy'),str(ROOT/'scripts')]
from library_server import Library,handler
from photo_sources import collect

class LibraryTest(unittest.TestCase):
    def test_source_dates_and_ambiguity(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'raw';day=source/'2026-8-26';day.mkdir(parents=True)
            (day/'DSC_0001.NEF').write_bytes(b'raw')
            recycle=source/'回收站';recycle.mkdir();(recycle/'DSC_0002.NEF').write_bytes(b'excluded')
            exports=root/'exports'/'wrong-date';exports.mkdir(parents=True)
            Image.new('RGB',(30,30)).save(exports/'DSC_0001-2.jpg')
            Image.new('RGB',(30,30)).save(exports/'DSC_0002.jpg')
            records,warnings=collect(source,exports.parent)
            self.assertEqual(len(records),1);self.assertEqual(records[0]['date'],'2026-08-26')
            self.assertEqual(len(records[0]['versions']),1);self.assertEqual(len(warnings['unmatched_jpg']),1)
            other=source/'2026-8-27';other.mkdir();(other/'DSC_0001.NEF').write_bytes(b'raw2')
            records,warnings=collect(source,exports.parent)
            self.assertEqual(len(warnings['ambiguous_jpg']),1)
            self.assertTrue(all(not r['versions'] for r in records))

    def test_http_hide_download_recolor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);site=root/'site';site.mkdir()
            for folder in ('media','downloads'):(site/folder).mkdir()
            versions=[]
            for n,label in enumerate(('精调','标准转换')):
                key=str(n)*64
                for suffix in ('-0.jpg','-1.jpg'):Image.new('RGB',(32,32)).save(site/'media'/(key+suffix))
                Image.new('RGB',(32,32)).save(site/'downloads'/(key+'.jpg'))
                versions.append({'id':key,'label':label,'thumb':f'media/{key}-0.jpg','preview':f'media/{key}-1.jpg','jpg':{'url':f'downloads/{key}.jpg','bytes':(site/'downloads'/(key+'.jpg')).stat().st_size}})
            raw=site/'downloads'/('a'*64+'.nef');raw.write_bytes(b'raw-file')
            photo={'id':'2026-08-26_DSC_0001','name':'DSC_0001','date':'2026-08-26','versions':versions,'nef':{'url':'downloads/'+raw.name,'bytes':8},'preview':versions[0]['preview']}
            catalog={'version':2,'photos':[photo],'dates':['2026-08-26']};(site/'catalog.json').write_text(json.dumps(catalog))
            state=root/'state.json';library=Library(site,state)
            server=ThreadingHTTPServer(('127.0.0.1',0),handler(library));thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base=f'http://127.0.0.1:{server.server_port}/'
            def request(route,data=None,headers=None):
                req=Request(base+route,data=json.dumps(data).encode() if data is not None else None,headers=headers or {'Content-Type':'application/json','X-LitchiLens':'1'})
                try:
                    with urlopen(req) as response:return response.status,response.read(),response.headers
                except HTTPError as exc:return exc.code,exc.read(),exc.headers
            try:
                ids=[photo['id']]
                status,payload,_=request('api/download',{'ids':ids,'kind':'standard'});self.assertEqual(status,200)
                result=json.loads(payload);self.assertEqual(result['mode'],'files')
                ticket=result['files'][0]['url'];status,payload,headers=request(ticket)
                self.assertEqual(status,200)
                self.assertEqual(ticket,versions[1]['jpg']['url'])
                self.assertEqual(headers['X-Accel-Redirect'],'/__litchilens_assets/'+ticket)
                self.assertEqual(request('api/recolor',{'ids':ids,'reason':'提亮一点'})[0],200)
                with ThreadPoolExecutor(max_workers=8) as pool:
                    statuses=list(pool.map(lambda n:request('api/recolor',{'ids':ids,'reason':f'并发留言 {n}'})[0],range(8)))
                self.assertEqual(statuses,[200]*8)
                self.assertEqual(request('api/hide',{'ids':ids})[0],400)
                self.assertEqual(request('api/hide',{'ids':['invalid'],'confirmed':True})[0],400)
                self.assertEqual(request('api/search',{'embedding':[0]*1023})[0],400)
                self.assertEqual(request('api/hide',{'ids':ids,'confirmed':True}, {'Content-Type':'application/json','X-LitchiLens':'1','Origin':'https://evil.example'})[0],403)
                self.assertEqual(request('api/hide',{'ids':ids,'confirmed':True})[0],200)
                self.assertEqual(json.loads(request('catalog.json')[1])['photos'],[])
                for version in versions:
                    for asset in (version['thumb'],version['preview'],version['jpg']['url']):self.assertEqual(request(asset)[0],404)
                self.assertEqual(request(photo['nef']['url'])[0],404)
                self.assertEqual(request(ticket)[0],404)
                self.assertFalse(Library(site,state).visible(photo['id']))
                self.assertEqual(len(json.loads(state.read_text())['requests']),9)
                self.assertTrue(raw.exists())
                raw.unlink()
                with self.assertRaises(FileNotFoundError):Library(site,state)
            finally:
                server.shutdown();server.server_close();thread.join()

    def test_download_file_threshold(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'downloads').mkdir();(root/'media').mkdir()
            photos=[]
            for n in range(11):
                key=f'{n:064x}';jpg=f'downloads/{key}.jpg';preview=f'media/{key}-0.jpg'
                Image.new('RGB',(8,8)).save(root/jpg);Image.new('RGB',(8,8)).save(root/preview)
                raw=f'downloads/{key}.nef';(root/raw).write_bytes(b'raw')
                photos.append({'id':f'2026-08-26_DSC_{n:04d}','versions':[{'label':'标准转换','jpg':{'url':jpg},'thumb':preview,'preview':preview}],
                    'nef':{'url':raw} if n<10 else None})
            (root/'catalog.json').write_text(json.dumps({'version':2,'photos':photos}))
            library=Library(root,root/'state.json')
            server=ThreadingHTTPServer(('127.0.0.1',0),handler(library))
            thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
            base=f'http://127.0.0.1:{server.server_port}/'
            def prepare(count,kind='jpg'):
                req=Request(base+'api/download',data=json.dumps({'ids':[p['id'] for p in photos[:count]],'kind':kind}).encode(),
                    headers={'Content-Type':'application/json','X-LitchiLens':'1'})
                with urlopen(req) as response:return json.load(response)
            try:
                for count in (1,10):
                    result=prepare(count);self.assertEqual(result['mode'],'files');self.assertEqual(len(result['files']),count)
                    self.assertEqual(result['files'][0]['name'],photos[0]['id']+'.jpg')
                raw=prepare(11,'nef');self.assertEqual(raw['mode'],'files');self.assertEqual(raw['missing'],1)
                self.assertTrue(all(f['name'].endswith('.NEF') for f in raw['files']))
                result=prepare(11);self.assertEqual(result['mode'],'zip')
                # 链接生成后下架的 ID，也不能被旧 ZIP 链接继续导出。
                library.state['hidden'][photos[0]['id']]={}
                with urlopen(base+result['url']) as response:payload=response.read()
                with zipfile.ZipFile(io.BytesIO(payload)) as archive:
                    self.assertIsNone(archive.testzip());self.assertEqual(len(archive.namelist()),10)
                    self.assertNotIn(photos[0]['id']+'.jpg',archive.namelist())
                    self.assertEqual(archive.read(photos[1]['id']+'.jpg'),(root/photos[1]['versions'][0]['jpg']['url']).read_bytes())
            finally:
                server.shutdown();server.server_close();thread.join()

    def test_traffic_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'catalog.json').write_text('{"version":2,"photos":[]}')
            log=root/'completion.log';log.touch()
            library=Library(root,root/'state.json',completion_log=log)
            import time
            library.downloads['a'*32]=time.time()
            status=library.traffic('12345678-1234-1234-1234-123456789abc')
            self.assertEqual(status['downloads'],1);self.assertEqual(status['visitors'],1)
            for _ in range(5):
                self.assertEqual(library.traffic('12345678-1234-1234-1234-123456789abc')['visitors'],1)
            self.assertEqual(library.traffic('')['visitors'],1)
            self.assertEqual(library.traffic('87654321-1234-1234-1234-123456789abc')['visitors'],2)
            log.write_text(json.dumps({'id':'a'*32})+'\n')
            self.assertEqual(library.traffic()['downloads'],0)
            library.visitors={k:v-100 for k,v in library.visitors.items()}
            self.assertEqual(library.traffic()['visitors'],0)

if __name__=='__main__':unittest.main()
