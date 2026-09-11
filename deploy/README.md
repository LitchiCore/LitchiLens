# 自有服务器部署

项目部署在自有 Linux 服务器，不需要第三方网站托管。

## 首次安装

需要 Python 3、Nginx、支持 IP 证书的 Certbot，以及默认网卡上唯一的稳定公网 IPv6。Nginx 应已将公网 TCP 80 的 `/.well-known/acme-challenge/` 映射到 `/var/lib/letsencrypt`。路由器还需允许网站端口入站。

先完成本地构建，将 `output/site` 与 `deploy` 中的 Python 脚本复制到服务器的独立暂存目录，再运行（以下路径为示例）：

```bash
sudo python3 /tmp/litchilens/deploy/install.py --site /tmp/litchilens/site --port 8444
```

安装器申请专用 IP 证书，生成相册路径，创建 `/srv/litchilens` 发布目录和独立 Nginx 站点。端口首页自动跳转到相册，因此路径不承担访问限制作用。通过配置测试、reload 后严格校验 TLS 和 HTTP 200，再启用每小时维护任务。若安装了 UFW，仅增加指定端口规则，不改变 UFW 启用状态。

首次安装中断且目录已创建时，查明原因后可对同一端口增加 `--resume` 继续。它不用于常规更新。Nginx 检查失败时撤下新站点，并检查、加载原配置。

## 更新照片或页面

本地重新构建，将完整输出同步到服务器暂存目录后运行：

```bash
sudo python3 /tmp/litchilens/deploy/publish.py --site /tmp/litchilens/site
```

只复制索引引用的照片和固定页面资产。复制完成后原子切换 `current` 符号链接，再验证 HTTPS；失败则切回原版本。旧版本保留在 `releases` 中，需人工管理磁盘容量。不要直接把原照片目录设为网站根目录。

## 证书与维护

```bash
sudo systemctl start litchilens-maintain.service
sudo systemctl status litchilens-maintain.timer
sudo journalctl -u litchilens-maintain.service -n 30
sudo certbot renew --cert-name litchilens-ipv6 --dry-run
```

维护脚本位于 `/usr/local/sbin/litchilens-maintain`，检测公网 IPv6、申请或续期证书、检查并 reload Nginx，再校验证书链、地址匹配与相册 HTTP 200。配置保存在只有 root 可读的 `/etc/litchilens/site.json`。

IP 变化后需要重新发送链接、二维码。没有外部通知服务，维护失败记录在 systemd 日志中。

## 分发限制

- 每个 IP 最多同时下载 2 个文件，本站最多同时下载 12 个文件。
- 每个下载请求限速 512 KiB/s；它不是整个家庭网络的总带宽上限。
- 支持单范围请求与断点续传，超过并发限制返回 429。
- 内容寻址的图片缓存 30 天，页面和索引要求重新验证。
- 禁止目录列表和隐藏路径，添加禁止搜索引擎索引的响应头。

## 到期关闭

移除本项目的 `/etc/nginx/sites-enabled/litchilens` 符号链接，执行 `nginx -t` 后 reload，并停用 `litchilens-maintain.timer`。只清理本项目目录、端口规则和专用证书，不停止其他站点共用的 Nginx。原片保留在本地照片目录。

上线前检查页面、索引、静态文件、附件下载与 Range 响应，并复查原有站点。本机或同一局域网验证不能代替独立外网测试，还需用手机流量等网络实测。
