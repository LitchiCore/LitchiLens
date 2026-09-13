#!/usr/bin/env python3
"""安装照片库 API 和专用 Nginx 配置，失败回滚；不改动其他站点。"""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
from urllib.request import urlopen
from maintain import current_ip, verify


def run(command):
    return subprocess.run(command, check=True, capture_output=True, text=True, timeout=120).stdout


def nginx_config(token, port):
    prefix = f"/{token}/"
    proxy = """proxy_set_header X-Forwarded-Host $http_host;
        proxy_set_header X-Request-Id $request_id;
        proxy_set_header X-Forwarded-Proto https;
        proxy_http_version 1.1;
        proxy_connect_timeout 3s;
        proxy_read_timeout 60s;"""
    return f'''# LitchiLens；网站共享总带宽由 litchilens-bandwidth 管理，不设置逐连接限速。
log_format lens_transfer escape=json '{{"id":"$request_id"}}';
limit_conn_zone $server_name zone=lens_zip_total:1m;
limit_conn_zone $server_name zone=lens_bulk_total:1m;
limit_conn_zone $server_name zone=lens_search_total:1m;
limit_conn_zone $server_name zone=lens_models_total:1m;
limit_req_zone $binary_remote_addr zone=lens_actions:10m rate=30r/m;
limit_req_zone $binary_remote_addr zone=lens_search:10m rate=6r/m;
server {{
    listen [::]:{port} ssl ipv6only=on;
    server_name litchilens;
    ssl_certificate /etc/letsencrypt/live/litchilens-ipv6/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/litchilens-ipv6/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    server_tokens off;
    autoindex off;
    access_log off;
    error_log /var/log/nginx/litchilens-error.log warn;
    sendfile on;
    client_max_body_size 64k;
    client_body_timeout 10s;
    limit_conn_status 429;
    limit_req_status 429;
    error_page 429 = @busy;
    gzip on;
    gzip_types application/json application/javascript text/css;
    add_header X-Content-Type-Options nosniff always;
    add_header X-Robots-Tag "noindex, nofollow, noarchive" always;
    add_header Referrer-Policy no-referrer always;
    add_header Content-Security-Policy "default-src 'self'; img-src 'self' blob:; style-src 'self'; script-src 'self' 'wasm-unsafe-eval'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'" always;
    location = / {{ return 302 {prefix}; }}
    location = /{token} {{ return 302 {prefix}; }}
    location = /nef {{ return 302 "{prefix}#library"; }}
    location = /robots.txt {{ default_type text/plain; return 200 "User-agent: *\\nDisallow: /\\n"; }}
    location = {prefix} {{ alias /srv/litchilens/library-current/; index index.html; expires -1; }}
    # 旧的预制包不受逐 ID 隐藏控制，升级后停止公开，磁盘文件保留。
    location {prefix}bundles/ {{ return 410; }}
    location = {prefix}packages.html {{ return 302 "{prefix}#library"; }}
    location = {prefix}catalog.json {{
        limit_except GET {{ deny all; }}
        {proxy}
        proxy_pass http://127.0.0.1:8766/catalog.json;
    }}
    location = {prefix}api/search {{
        limit_except POST {{ deny all; }}
        limit_req zone=lens_search burst=2 nodelay;
        limit_conn lens_search_total 2;
        {proxy}
        proxy_pass http://127.0.0.1:8766/api/search;
    }}
    # 精确匹配创建请求，避免下方尾斜杠 location 自动重定向 POST。
    location = {prefix}api/download {{
        limit_except POST {{ deny all; }}
        limit_req zone=lens_actions burst=5 nodelay;
        {proxy}
        proxy_pass http://127.0.0.1:8766/api/download;
    }}
    location {prefix}api/download/ {{
        limit_except GET {{ deny all; }}
        limit_conn lens_zip_total 16;
        limit_conn lens_bulk_total 128;
        {proxy}
        proxy_buffering on;
        proxy_max_temp_file_size 0;
        proxy_pass http://127.0.0.1:8766/api/download/;
    }}
    location {prefix}api/ {{
        limit_req zone=lens_actions burst=5 nodelay;
        {proxy}
        proxy_pass http://127.0.0.1:8766/api/;
    }}
    location {prefix}media/ {{
        limit_except GET {{ deny all; }}
        {proxy}
        proxy_pass http://127.0.0.1:8766/media/;
    }}
    location {prefix}downloads/ {{
        limit_except GET {{ deny all; }}
        {proxy}
        proxy_pass http://127.0.0.1:8766/downloads/;
    }}
    location /__litchilens_assets/media/ {{
        internal;
        alias /srv/litchilens/library-current/media/;
        add_header Cache-Control "no-store" always;
    }}
    location /__litchilens_assets/downloads/ {{
        internal;
        access_log /var/log/nginx/litchilens-transfers.log lens_transfer;
        alias /srv/litchilens/library-current/downloads/;
        limit_conn lens_bulk_total 128;
        max_ranges 1;
        add_header Cache-Control "no-store" always;
        add_header Content-Disposition attachment;
    }}
    location {prefix}vendor/ {{
        alias /srv/litchilens/library-current/vendor/;
        limit_except GET {{ deny all; }}
        limit_conn lens_models_total 4;
        expires 7d;
    }}
    location @busy {{
        access_log /var/log/nginx/litchilens-transfers.log lens_transfer;
        default_type application/json;
        add_header Retry-After 5 always;
        return 429 '{{"error":"当前下载或操作较多，请稍后重试；照片浏览仍可使用"}}';
    }}
    location ~ ^/{token}/(index\\.html|app\\.js|catalog\\.js|style\\.css|library\\.css|sponsor\\.css|find-face\\.js|face-config\\.js|icon\\.svg|sponsor\\.png)$ {{
        alias /srv/litchilens/library-current/$1;
        limit_except GET {{ deny all; }}
        expires -1;
    }}
    location / {{ return 404; }}
}}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--site", required=True)
    parser.add_argument("--faces", required=True)
    args = parser.parse_args()
    # 新版不设逐连接限速，发布前必须先启用共享出口流控。
    run(["systemctl", "is-active", "--quiet", "litchilens-bandwidth.service"])
    site = Path(args.site).resolve(strict=True)
    if not site.is_relative_to("/srv/litchilens/library-releases"):
        raise ValueError("只发布专用 library-releases 下已验证的目录")
    config = json.loads(Path("/etc/litchilens/site.json").read_text())
    nginx = Path("/etc/nginx/sites-available/litchilens")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = Path("/srv/litchilens/backups") / stamp
    backup.mkdir(parents=True)
    shutil.copyfile(nginx, backup / "nginx.conf")
    unit = Path("/etc/systemd/system/litchilens-library.service")
    if unit.exists():
        shutil.copyfile(unit, backup / "service")
    current = Path("/srv/litchilens/library-current")
    previous = current.resolve() if current.is_symlink() else None
    try:
        account = pwd.getpwnam("litchilens")
    except KeyError:
        run(
            [
                "useradd",
                "--system",
                "--home",
                "/var/lib/litchilens",
                "--shell",
                "/usr/sbin/nologin",
                "litchilens",
            ]
        )
        account = pwd.getpwnam("litchilens")
    state = Path("/var/lib/litchilens")
    state.mkdir(mode=0o700, exist_ok=True)
    os.chown(state, account.pw_uid, account.pw_gid)
    completions = Path("/var/log/nginx/litchilens-transfers.log")
    completions.touch(exist_ok=True)
    completions.chmod(0o640)
    os.chown(completions, pwd.getpwnam("www-data").pw_uid, account.pw_gid)
    faces = state / "faces.json"
    if faces.exists():
        shutil.copyfile(faces, backup / "faces.json")
    shutil.copyfile(args.faces, faces)
    faces.chmod(0o600)
    os.chown(faces, account.pw_uid, account.pw_gid)
    helper = Path("/usr/local/lib/litchilens")
    helper.mkdir(parents=True, exist_ok=True)
    if (helper / "library_server.py").exists():
        shutil.copyfile(helper / "library_server.py", backup / "library_server.py")
    shutil.copyfile(Path(__file__).with_name("library_server.py"), helper / "library_server.py")
    for name in ("admin_server.py", "admin.html"):
        if (helper / name).exists():
            shutil.copyfile(helper / name, backup / name)
        shutil.copyfile(Path(__file__).with_name(name), helper / name)
    for p in site.rglob("*"):
        if p.is_symlink():
            raise ValueError("发布目录不能包含链接")
        p.chmod(0o755 if p.is_dir() else 0o644)
    site.chmod(0o755)
    temp = current.with_name("library-next")
    temp.symlink_to(site, target_is_directory=True)
    os.replace(temp, current)
    unit.write_text("""[Unit]
Description=LitchiLens photo library
After=network.target
[Service]
User=litchilens
Group=litchilens
ExecStart=/usr/bin/python3 /usr/local/lib/litchilens/library_server.py --site /srv/litchilens/library-current --state /var/lib/litchilens/state.json --faces /var/lib/litchilens/faces.json --completion-log /var/log/nginx/litchilens-transfers.log
Restart=on-failure
RestartSec=3
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/litchilens
PrivateTmp=true
UMask=0077
MemoryMax=1536M
CPUQuota=200%
TasksMax=80
[Install]
WantedBy=multi-user.target
""")
    try:
        nginx.write_text(nginx_config(config["token"], config["port"]))
        run(["/usr/sbin/nginx", "-t"])
        run(["systemctl", "daemon-reload"])
        run(["systemctl", "enable", "--now", "litchilens-library.service"])
        run(["systemctl", "restart", "litchilens-library.service"])
        import time

        for attempt in range(40):
            try:
                with urlopen("http://127.0.0.1:8766/api/status", timeout=3) as response:
                    if not json.load(response)["faces_ready"]:
                        raise RuntimeError("人脸索引未加载")
                break
            except OSError:
                if attempt == 39:
                    raise
                time.sleep(1)
        run(["systemctl", "reload", "nginx"])
        time.sleep(1)
        verify(current_ip(), config["port"], config["token"])
    except Exception:
        shutil.copyfile(backup / "nginx.conf", nginx)
        if previous:
            temp.symlink_to(previous, target_is_directory=True)
            os.replace(temp, current)
        else:
            current.unlink(missing_ok=True)
        for name, target in [
            ("library_server.py", helper / "library_server.py"),
            ("admin_server.py", helper / "admin_server.py"),
            ("admin.html", helper / "admin.html"),
            ("faces.json", faces),
            ("service", unit),
        ]:
            if (backup / name).exists():
                shutil.copyfile(backup / name, target)
        run(["systemctl", "daemon-reload"])
        run(["systemctl", "restart" if previous else "stop", "litchilens-library.service"])
        run(["/usr/sbin/nginx", "-t"])
        run(["systemctl", "reload", "nginx"])
        raise
    print(f"照片库已发布；备份：{backup}")


if __name__ == "__main__":
    main()
