"""仅绑定回环地址的管理工作台，必须通过 SSH 转发访问，不交给公网 Nginx。"""

import csv
import io
import json
import mimetypes
from pathlib import Path
import shutil
from http.server import BaseHTTPRequestHandler


def admin_handler(library):
    class Admin(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, body, content_type="application/json; charset=utf-8"):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode()
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def allowed_host(self):
            host = self.headers.get("Host", "").split(":")[0]
            return host in ("127.0.0.1", "localhost")

        def do_GET(self):
            if not self.allowed_host():
                return self.reply(403, {"error": "仅允许本机 SSH 转发入口"})
            route = self.path.split("?", 1)[0]
            with library.lock:
                if route == "/":
                    return self.reply(
                        200,
                        Path(__file__).with_name("admin.html").read_bytes(),
                        "text/html; charset=utf-8",
                    )
                if route == "/requests":
                    ids = {i for r in library.state["requests"] for i in r["ids"]}
                    photos = {
                        i: dict(library.photos[i], hidden=not library.visible(i))
                        for i in ids
                        if i in library.photos
                    }
                    return self.reply(
                        200, {"requests": library.state["requests"], "photos": photos}
                    )
                if route == "/requests.csv":
                    output = io.StringIO()
                    writer = csv.writer(output)
                    writer.writerow(
                        [
                            "申请编号",
                            "照片ID",
                            "相机编号",
                            "日期",
                            "调色要求",
                            "状态",
                            "提交时间",
                            "是否已下架",
                        ]
                    )
                    for r in library.state["requests"]:
                        if r["status"] == "已完成":
                            continue
                        for identity in r["ids"]:
                            p = library.photos.get(identity, {})
                            # 防止用户文本被电子表格当成公式执行。
                            values = [
                                r["id"],
                                identity,
                                p.get("name", ""),
                                p.get("date", ""),
                                r["reason"],
                                r["status"],
                                r["created"],
                                "是" if not library.visible(identity) else "否",
                            ]
                            writer.writerow(
                                ["'" + v if v and v[0] in "=+-@\t\r\n" else v for v in values]
                            )
                    return self.reply(
                        200, output.getvalue().encode("utf-8-sig"), "text/csv; charset=utf-8"
                    )
                if route.startswith("/asset/"):
                    asset = route[len("/asset/") :]
                    if asset not in library.assets:
                        return self.reply(404, {"error": "文件不存在"})
                    file = library.site / asset
                else:
                    return self.reply(404, {"error": "页面不存在"})
            self.send_response(200)
            self.send_header(
                "Content-Type", mimetypes.guess_type(file.name)[0] or "application/octet-stream"
            )
            self.send_header("Content-Length", str(file.stat().st_size))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                with file.open("rb") as handle:
                    shutil.copyfileobj(handle, self.wfile, 1024 * 1024)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def do_POST(self):
            if (
                not self.allowed_host()
                or self.headers.get("X-LitchiLens") != "1"
                or self.headers.get("Origin")
                not in (None, "http://" + self.headers.get("Host", ""))
            ):
                return self.reply(403, {"error": "请从本机管理页操作"})
            try:
                size = int(self.headers.get("Content-Length", 0))
                if not 0 < size <= 4096:
                    raise ValueError()
                if self.path != "/update" or self.headers.get("Content-Type") != "application/json":
                    raise ValueError()
                data = json.loads(self.rfile.read(size))
                if data.get("status") not in ("待处理", "处理中", "已完成"):
                    raise ValueError()
                with library.lock:
                    request = next(
                        (r for r in library.state["requests"] if r["id"] == data.get("request_id")),
                        None,
                    )
                    if request is None:
                        raise ValueError()
                    old = request["status"]
                    request["status"] = data["status"]
                    try:
                        library.persist()
                    except OSError:
                        request["status"] = old
                        raise
                return self.reply(200, {"ok": True})
            except (ValueError, TypeError, AttributeError):
                return self.reply(400, {"error": "请求无效"})
            except OSError:
                return self.reply(503, {"error": "保存失败"})

    return Admin
