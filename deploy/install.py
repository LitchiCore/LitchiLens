#!/usr/bin/env python3
"""首次安装专用静态站点；不覆盖已有站点。需要 root 与现有 ACME webroot。"""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import secrets
import shutil
import subprocess
from datetime import datetime, timezone
from publish import stage


def run(args):
    return subprocess.run(args,check=True,capture_output=True,text=True,timeout=240).stdout


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--site',required=True,help='已构建的静态目录')
    parser.add_argument('--port',type=int,default=8444)
    parser.add_argument('--resume',action='store_true',help='恢复同一站点中断的首次安装')
    args=parser.parse_args()
    site=Path(args.site).resolve(strict=True)
    if not 1024<=args.port<=65535: raise ValueError('端口应在 1024 至 65535 之间')
    for name in ('index.html','catalog.json','style.css','app.js','catalog.js','icon.svg'):
        if not (site/name).is_file(): raise ValueError(f'缺少构建文件：{name}')
    exists=Path('/etc/litchilens').exists() or Path('/srv/litchilens').exists()
    if exists and not args.resume: raise RuntimeError('已有安装，拒绝覆盖。更新使用 publish.py；恢复中断的首次安装使用 --resume。')
    if not args.resume and re.search(rf':{args.port}\s',run(['ss','-lnt'])): raise RuntimeError('端口已被占用')
    spec=importlib.util.spec_from_file_location('maintain',Path(__file__).with_name('maintain.py'))
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    ip=module.current_ip()
    if args.resume:
        previous=json.loads(Path('/etc/litchilens/site.json').read_text())
        if previous['port']!=args.port or not re.fullmatch('[a-f0-9]{32}',previous['token']): raise ValueError('恢复配置不匹配')
        if not Path('/srv/litchilens/current').resolve(strict=True).is_relative_to('/srv/litchilens/releases'): raise ValueError('发布目录不匹配')
        token=previous['token']
    else:
        token=secrets.token_hex(16)
    certbot=shutil.which('certbot') or '/snap/bin/certbot'
    run([certbot,'certonly','--webroot','--webroot-path','/var/lib/letsencrypt','--preferred-profile','shortlived',
         '--ip-address',ip,'--cert-name','litchilens-ipv6','--agree-tos','--non-interactive'])
    config_dir=Path('/etc/litchilens'); config_dir.mkdir(mode=0o700,exist_ok=args.resume)
    config=config_dir/'site.json'; config.write_text(json.dumps({'port':args.port,'token':token,'ipv6':ip})); config.chmod(0o600)
    root=Path('/srv/litchilens'); release=root/'releases'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    # 只复制索引引用的资产，不把上次失败留下的文件公开。
    if not args.resume:
        stage(site,release,token)
        (root/'current').symlink_to(release,target_is_directory=True)
    for item in root.rglob('*'):
        if not item.is_symlink(): item.chmod(0o755 if item.is_dir() else 0o644)
    bundles=root/'bundles'; bundles.mkdir(exist_ok=True)
    if not (bundles/'packages.json').exists():
        (bundles/'packages.json').write_text('{"version":1,"packages":[]}')
    nginx=Path('/etc/nginx/sites-available/litchilens')
    nginx.write_text(f'''# 荔枝镜头专用站点，分享路径不是身份认证。
limit_conn_zone $binary_remote_addr zone=litchilens_per_ip:10m;
limit_conn_zone $server_name zone=litchilens_total:1m;
server {{
    listen [::]:{args.port} ssl ipv6only=on;
    server_name litchilens;
    root /srv/litchilens/current;
    ssl_certificate /etc/letsencrypt/live/litchilens-ipv6/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/litchilens-ipv6/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    server_tokens off;
    autoindex off;
    access_log off;
    error_log /var/log/nginx/litchilens-error.log warn;
    sendfile on;
    limit_conn_status 429;
    add_header X-Content-Type-Options nosniff always;
    add_header X-Robots-Tag "noindex, nofollow, noarchive" always;
    add_header Referrer-Policy no-referrer always;
    add_header Content-Security-Policy "default-src 'self'; img-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'" always;
    location = / {{ return 302 /{token}/; }}
    location = /nef {{ return 302 /{token}/packages.html; }}
    location / {{ return 404; }}
    location = /robots.txt {{ default_type text/plain; return 200 "User-agent: *\\nDisallow: /\\n"; }}
    location = /{token} {{ return 302 /{token}/; }}
    location /{token}/ {{
        limit_except GET {{ deny all; }}
        index index.html;
        try_files $uri $uri/ =404;
        expires -1;
    }}
    location /{token}/media/ {{
        limit_except GET {{ deny all; }}
        try_files $uri =404;
        expires 30d;
    }}
    location /{token}/bundles/ {{
        alias /srv/litchilens/bundles/;
        limit_except GET {{ deny all; }}
        limit_conn litchilens_per_ip 2;
        limit_conn litchilens_total 4;
        limit_rate 6m;
        max_ranges 1;
        default_type application/octet-stream;
        add_header Content-Disposition attachment;
        add_header X-Content-Type-Options nosniff always;
        add_header X-Robots-Tag "noindex, nofollow, noarchive" always;
    }}
    location /{token}/downloads/ {{
        limit_except GET {{ deny all; }}
        try_files $uri =404;
        limit_conn litchilens_per_ip 2;
        limit_conn litchilens_total 12;
        limit_rate 512k;
        max_ranges 1;
        default_type application/octet-stream;
        add_header Content-Disposition attachment;
        add_header X-Content-Type-Options nosniff always;
        add_header X-Robots-Tag "noindex, nofollow, noarchive" always;
        expires 30d;
    }}
    location ~ /\\. {{ deny all; }}
}}
''')
    enabled=Path('/etc/nginx/sites-enabled/litchilens')
    if not enabled.exists(): enabled.symlink_to(nginx)
    try:
        run(['/usr/sbin/nginx','-t']); run(['systemctl','reload','nginx'])
        module.verify(ip,args.port,token)
    except Exception:
        enabled.unlink(missing_ok=True)
        run(['/usr/sbin/nginx','-t']); run(['systemctl','reload','nginx'])
        raise
    helper=Path('/usr/local/sbin/litchilens-maintain'); shutil.copyfile(Path(__file__).with_name('maintain.py'),helper); helper.chmod(0o755)
    Path('/etc/systemd/system/litchilens-maintain.service').write_text('''[Unit]
Description=LitchiLens IPv6 and certificate maintenance
After=network-online.target nginx.service
Wants=network-online.target
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /usr/local/sbin/litchilens-maintain
TimeoutStartSec=300
UMask=0077
''')
    Path('/etc/systemd/system/litchilens-maintain.timer').write_text('''[Unit]
Description=Hourly LitchiLens HTTPS maintenance
[Timer]
OnBootSec=3min
OnUnitActiveSec=1h
RandomizedDelaySec=60
[Install]
WantedBy=timers.target
''')
    run(['systemctl','daemon-reload']); run(['systemctl','enable','--now','litchilens-maintain.timer'])
    run(['systemctl','start','litchilens-maintain.service'])
    ufw=shutil.which('ufw')
    if ufw:
        # 只增加本端口规则，不改变 UFW 启用状态；不依赖本地化状态文本。
        run([ufw,'allow',f'{args.port}/tcp','comment','LitchiLens HTTPS'])
    print(f'网站已安装：https://[{ip}]:{args.port}/{token}/')


if __name__=='__main__': main()
