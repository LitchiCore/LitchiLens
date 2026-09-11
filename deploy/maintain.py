#!/usr/bin/env python3
"""以 root 运行：维护固定站点 IPv6 证书，并校验实际 HTTPS。"""
import fcntl
import ipaddress
import json
from pathlib import Path
import shutil
import socket
import ssl
import subprocess
import sys
import time

CONFIG = Path('/etc/litchilens/site.json')


def run(command, timeout=240):
    return subprocess.run(command, check=True, capture_output=True, text=True, timeout=timeout).stdout


def current_ip():
    routes=json.loads(run(['ip','-j','-6','route','show','default']))
    if not routes: raise RuntimeError('没有 IPv6 默认路由')
    addresses=json.loads(run(['ip','-j','-6','addr','show','dev',routes[0]['dev']]))
    candidates=[]
    for interface in addresses:
        for item in interface.get('addr_info',[]):
            address=ipaddress.ip_address(item['local'])
            if address.is_global and not item.get('temporary') and not item.get('deprecated') and item.get('preferred_life_time') != 0:
                candidates.append(str(address))
    if len(candidates)!=1: raise RuntimeError('无法唯一确定稳定公网 IPv6')
    return candidates[0]


def verify(ip, port, token):
    # Nginx reload 返回后，新 worker 可能尚未监听；重试但不跳过 TLS 校验。
    for attempt in range(15):
        try:
            with socket.create_connection(('::1',port),timeout=3) as raw:
                with ssl.create_default_context().wrap_socket(raw,server_hostname=ip) as conn:
                    conn.sendall(f'GET /{token}/ HTTP/1.1\r\nHost: [{ip}]:{port}\r\nConnection: close\r\n\r\n'.encode())
                    with conn.makefile('rb') as response: status=response.readline(4096).decode().strip()
                    if len(status.split())<2 or status.split()[1]!='200': raise RuntimeError(f'页面检查失败：{status}')
                    return
        except (OSError, RuntimeError):
            if attempt==14: raise
            time.sleep(1)


def main():
    with open('/run/litchilens-maintain.lock','w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        config=json.loads(CONFIG.read_text())
        ip=current_ip()
        command=[shutil.which('certbot') or '/snap/bin/certbot','certonly','--webroot','--webroot-path','/var/lib/letsencrypt',
                 '--preferred-profile','shortlived','--ip-address',ip,'--cert-name','litchilens-ipv6','--agree-tos','--non-interactive']
        if config.get('ipv6') and config['ipv6']!=ip: command.append('--force-renewal')
        run(command)
        run(['/usr/sbin/nginx','-t'],30)
        run(['systemctl','reload','nginx'],30)
        verify(ip,config['port'],config['token'])
        config['ipv6']=ip
        temp=CONFIG.with_suffix('.tmp'); temp.write_text(json.dumps(config,ensure_ascii=False,indent=2)); temp.chmod(0o600); temp.replace(CONFIG)
        print(f'HTTPS 校验通过：https://[{ip}]:{config["port"]}/{config["token"]}/')


if __name__=='__main__':
    try: main()
    except Exception as exc:
        print(f'维护失败：{exc}',file=sys.stderr)
        sys.exit(1)
