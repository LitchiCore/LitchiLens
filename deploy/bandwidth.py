#!/usr/bin/env python3
"""只对相册端口实施总出口限速；按 TCP 流公平排队，其他端口走独立队列。"""
import argparse
import json
from pathlib import Path
import re
import subprocess


def run(*args):
    result=subprocess.run(args,capture_output=True,text=True)
    if result.returncode:raise RuntimeError(f'{args}: {result.stderr.strip()}')
    return result.stdout


def apply(config, stop=False):
    interface=config['interface'];port=int(config['port']);mbit=int(config.get('mbit',48))
    if not re.fullmatch(r'[a-zA-Z0-9_.-]{1,15}',interface) or not 1<=port<=65535 or not 8<=mbit<=100:
        raise ValueError('网卡、端口或总带宽配置无效')
    roots=[q for q in json.loads(run('tc','-j','qdisc','show','dev',interface)) if q.get('root')]
    owned=bool(roots and roots[0].get('kind')=='htb' and roots[0].get('handle')=='9000:')
    if stop:
        if owned:run('tc','qdisc','replace','dev',interface,'root','fq_codel')
        return
    options=roots[0].get('options',{}) if roots else {}
    default_fq=(len(roots)==1 and roots[0]['kind']=='fq_codel' and options.get('limit')==10240
        and options.get('flows')==1024 and options.get('quantum')==1514
        and options.get('target') in (4999,5000) and options.get('interval') in (99999,100000)
        and options.get('memory_limit')==33554432 and options.get('ecn') is True)
    if not owned and not default_fq:
        raise RuntimeError('网卡已有其他流控配置，未覆盖')
    try:
        run('tc','qdisc','replace','dev',interface,'root','handle','9000:','htb','default','20')
        # 独立顶层类别：相册共享限额；其他服务不受相册的带宽额度约束。
        for minor,rate in [('10',f'{mbit}mbit'),('20','10000mbit')]:
            burst='64kb' if minor=='10' else '2mb'
            run('tc','class','replace','dev',interface,'parent','9000:','classid',f'9000:{minor}',
                'htb','rate',rate,'ceil',rate,'burst',burst,'cburst',burst,'quantum','1514')
            run('tc','qdisc','replace','dev',interface,'parent',f'9000:{minor}',
                'handle',f'{minor}:','fq_codel','quantum','1514')
        for priority,protocol in enumerate(['ipv6','ip'],10):
            run('tc','filter','add','dev',interface,'parent','9000:','protocol',protocol,'prio',str(priority),
                'flower','ip_proto','tcp','src_port',str(port),'classid','9000:10')
    except Exception:
        run('tc','qdisc','replace','dev',interface,'root','fq_codel')
        raise


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config',default='/etc/litchilens/bandwidth.json')
    parser.add_argument('--stop',action='store_true')
    args=parser.parse_args()
    apply(json.loads(Path(args.config).read_text()),args.stop)
