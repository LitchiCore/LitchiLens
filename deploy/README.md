# 自有 Linux 服务器部署

以下路径、网卡和端口均为示例，按自己的环境替换。先在本机完成构建，不在线转换照片。公网通过 Nginx 提供服务，Python API 与管理入口只监听 `127.0.0.1`。

## 首次准备

需要 Python 3.12+、Nginx、iproute2（含 `tc`）、支持 IP 地址证书的 Certbot，以及默认网卡上唯一的稳定公网 IPv6。Nginx 的公网 TCP 80 必须把 `/.well-known/acme-challenge/` 映射到 `/var/lib/letsencrypt`，路由器需允许相册 HTTPS 端口入站。证书参数以所安装 Certbot 的帮助为准，本项目使用 `--ip-address` 与短期证书配置。

先按 [README](../README.md) 构建第二版照片库，使用 `index_all_faces.mjs` 生成私人 `faces.json`。将部署脚本、完整网站和人脸索引分别上传到服务器暂存目录；不要上传整个 `private/`、个人日志或无关文件。

第一次安装使用 `install.py` 初始化专用证书、配置和维护定时器。这一步只用空目录构建占位站点，避免短暂公开未经下架控制的原片：

```sh
mkdir -p /tmp/litchilens-empty
python3 scripts/build_album.py --source /tmp/litchilens-empty --output /tmp/litchilens-bootstrap --center-crop
sudo python3 deploy/install.py --site /tmp/litchilens-bootstrap --port 8444
```

构建需要相应 Python 依赖，也可在本机构建空站点后上传。占位页只供初始化，第二版安装完成前不分发链接。首次安装中断时，查明原因后可对同一端口加 `--resume`；它不用于常规更新。

## 共享总带宽

用 `ip -6 route show default` 确认出口网卡。以下配置将相册端口限制为总共 48Mbit/s（约 6MB/s），其他端口走独立队列；HTB 控制总量，fq_codel 按 TCP 流公平排队。

```sh
sudo install -d /usr/local/lib/litchilens
sudo install -m 644 deploy/bandwidth.py /usr/local/lib/litchilens/bandwidth.py
sudo install -m 644 deploy/litchilens-bandwidth.service /etc/systemd/system/litchilens-bandwidth.service
sudoedit /etc/litchilens/bandwidth.json
```

写入配置，并把 `eth0` 改为真实出口网卡，端口须与上一步一致：

```json
{ "interface": "eth0", "port": 8444, "mbit": 48 }
```

```sh
sudo chmod 600 /etc/litchilens/bandwidth.json
sudo systemctl daemon-reload
sudo systemctl enable --now litchilens-bandwidth.service
sudo systemctl status litchilens-bandwidth.service
```

脚本只接管默认 fq_codel 或自身队列，遇到其他流控配置会拒绝覆盖。停止服务会恢复默认 fq_codel。流控故障应先修复，不要绕过第二版安装器的服务检查。

## 发布第二版

将网站放在 `/srv/litchilens/library-releases/<版本>/`，私有特征文件必须位于网站目录外。先校验资产，再安装：

```sh
sudo python3 deploy/verify_library.py /srv/litchilens/library-releases/<版本>
sudo python3 deploy/install_library.py --site /srv/litchilens/library-releases/<版本> --faces /path/to/private/faces.json
```

安装器备份配置与服务，启动 API、检查 Nginx，再 reload 并严格校验 HTTPS；失败时恢复旧站点。重调与下架状态保存在 `/var/lib/litchilens/state.json`，管理页通过 README 中的 SSH 转发访问。

更新仍使用新版本目录和 `install_library.py`。不要使用旧 `publish.py`，它不了解第二版可见性控制；不要直接修改硬链接下载文件。没有人脸索引时，本机开发服务可省略 `--faces`；当前生产安装器要求真实索引，不能用伪造向量代替。

## 验证与维护

```sh
sudo nginx -t
sudo systemctl status litchilens-library.service litchilens-bandwidth.service
sudo systemctl status litchilens-maintain.timer
sudo systemctl start litchilens-maintain.service
sudo journalctl -u litchilens-maintain.service -n 30
sudo tc -s class show dev eth0
```

通过真正的分享 URL 检查证书链、有效期、IP 匹配、浏览、直接下载、Range 续传和超过 10 个文件的 ZIP；不能用 `-k` 跳过 TLS 校验。并发测试同时观察浏览响应与出口流量，按连接公平分配不代表不同网络的用户速度完全相同。还需从手机移动网络检查 IPv6 可达性，本机或同一局域网测试不能代替独立外网测试。

大文件最多 128 路，其中 ZIP 最多 16 路；超出返回 429，其他页面仍可访问。这是资源保护上限，不代表保证 128 路都能获得高速。下载、预览与模型共用额度。IP 变化后需重新分发链接；维护失败记录在 systemd 日志中。

## 到期关闭

移除本项目 `/etc/nginx/sites-enabled/litchilens` 符号链接，执行 `nginx -t` 后 reload，再停用 `litchilens-library.service`、`litchilens-bandwidth.service` 和 `litchilens-maintain.timer`。只清理本项目目录、端口规则与专用证书，不停止其他站点共用的 Nginx。先保留必要的重调和下架状态备份，原片留在本地。

第一版历史行为见 [旧版参考](LEGACY.md)。
