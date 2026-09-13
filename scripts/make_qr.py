"""生成分享二维码；输出文件留在本地，不提交真实分享链接。"""

import argparse
from pathlib import Path
import urllib.parse
import qrcode

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("url", help="完整 HTTPS 分享链接")
parser.add_argument("--output", default="output/share-qr.png")
args = parser.parse_args()
parsed = urllib.parse.urlparse(args.url)
if parsed.scheme != "https" or not parsed.hostname:
    parser.error("需要完整 HTTPS 链接")
path = Path(args.output)
path.parent.mkdir(parents=True, exist_ok=True)
qrcode.make(args.url).save(path)
print(f"二维码已保存：{path}")
