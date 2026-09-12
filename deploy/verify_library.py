#!/usr/bin/env python3
"""发布前验证真实资产字节、引用和敏感目录隔离。"""
import argparse
import hashlib
import json
from pathlib import Path
import re

def verify(site):
    catalog=json.loads((site/'catalog.json').read_text(encoding='utf-8'))
    if catalog.get('version')!=2:raise ValueError('目录版本不正确')
    files={};media=set();ids=set()
    for photo in catalog['photos']:
        if photo['id'] in ids:raise ValueError('重复 ID')
        ids.add(photo['id'])
        for version in photo['versions']:
            files[version['jpg']['url']]=version['jpg']
            media.update((version['thumb'],version['preview']))
        if photo['nef']:files[photo['nef']['url']]=photo['nef']
    for n,(name,record) in enumerate(files.items(),1):
        if not re.fullmatch(r'downloads/[a-f0-9]{64}\.(jpg|nef)',name):raise ValueError('资产路径不正确')
        file=site/name
        if file.is_symlink() or not file.resolve(strict=True).is_relative_to(site.resolve()):raise ValueError('资产越界')
        if file.stat().st_size!=record['bytes']:raise ValueError(f'文件大小不匹配：{name}')
        with file.open('rb') as handle:
            if hashlib.file_digest(handle,'sha256').hexdigest()!=record['sha256']:raise ValueError(f'SHA256 不匹配：{name}')
        if n%500==0:print(f'已校验 {n}/{len(files)} 个下载文件',flush=True)
    for name in media:
        if not re.fullmatch(r'media/[a-f0-9]{64}-[01]\.jpg',name):raise ValueError('预览路径不正确')
        file=site/name
        with file.open('rb') as handle:
            if handle.read(2)!=b'\xff\xd8':raise ValueError('无效预览图')
    for name in ('index.html','app.js','catalog.js','style.css','library.css','sponsor.css','find-face.js','face-config.js','sponsor.png','vendor/human.esm.js'):
        if not (site/name).is_file():raise ValueError(f'缺少网站文件：{name}')
    print(f'校验通过：{len(ids)} 个 ID，{len(files)} 个下载文件，{len(media)} 个预览文件',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('site',type=Path);args=parser.parse_args();verify(args.site)
