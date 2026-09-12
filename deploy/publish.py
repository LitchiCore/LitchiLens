#!/usr/bin/env python3
"""发布完整静态目录，验证成功后保留版本；失败切回旧版本。"""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import shutil
import uuid
from maintain import verify, current_ip


def stage(site, release, token):
    catalog=json.loads((site/'catalog.json').read_text())
    if catalog.get('version')!=1 or not isinstance(catalog.get('photos'),list): raise ValueError('相册索引无效')
    assets=set()
    for photo in catalog['photos']:
        for value in (photo['thumb'],photo['preview'],photo['jpg']['url'],photo.get('nef',{}).get('url') if photo.get('nef') else None):
            if value is None: continue
            if not re.fullmatch(r'(media|downloads)/[a-f0-9-]+\.(jpg|nef)',value): raise ValueError('相册资产路径无效')
            path=site/value
            if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(site.resolve()): raise ValueError('照片文件不存在或越界')
            assets.add(value)
    destination=release/token; destination.mkdir(parents=True)
    for name in ('index.html','catalog.json','style.css','app.js','catalog.js','icon.svg','robots.txt','packages.html','packages.js','packages-data.js','packages.css',*sorted(assets)):
        target=destination/name; target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(site/name,target); target.chmod(0o644)
    for name in ('media','downloads'): (destination/name).mkdir(exist_ok=True)
    for item in release.rglob('*'):
        if item.is_dir(): item.chmod(0o755)
    release.chmod(0o755)


def main():
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--site',required=True); args=parser.parse_args()
    site=Path(args.site).resolve(strict=True)
    config=json.loads(Path('/etc/litchilens/site.json').read_text())
    root=Path('/srv/litchilens'); previous=(root/'current').resolve(strict=True)
    release=root/'releases'/(datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:8])
    stage(site,release,config['token'])
    temp=root/'current.next'; temp.symlink_to(release,target_is_directory=True); os.replace(temp,root/'current')
    try: verify(current_ip(),config['port'],config['token'])
    except Exception:
        temp.symlink_to(previous,target_is_directory=True); os.replace(temp,root/'current'); raise
    print('发布成功；旧版本保留在 releases 目录，可切回。')


if __name__=='__main__': main()
