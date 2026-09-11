# 荔枝镜头 · LitchiLens

用于活动照片临时分享的中文相册。手机浏览、免登录、JPG 优先、NEF 可选，自有服务器通过 IPv6 与独立 HTTPS 端口分发。

## 已实现

- 按日期浏览、按文件名搜索，每批加载 48 张缩略图。
- 大图查看、键盘切换、高清 JPG 下载及可选 NEF 下载。
- 离线人脸检测决定缩略图取景；合照无法兼顾所有检测到的人脸时保留完整画面，没有检测结果时居中取景。
- 480 × 360 缩略图、最长边 1920 像素的预览图，原片只读。
- 普通 JPEG 与包含 MPO 多图结构的 JPG 导入，处理 EXIF 方向。
- JPG/NEF 配对、歧义报告、无效文件检查，失败保留旧索引。
- 等待照片页面、Nginx 部署、下载限速和并发限制、IPv6 证书维护。

人脸检测只用于构图，不提取身份特征、不保存人脸框。“找同一个人的其他照片”和批量 ZIP 下载尚未实现。

## 准备环境

本地构建需要 Python 3.12 或更高版本。网站访问本身不运行 Python、模型或数据库。

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python scripts/setup_faces.py
```

Linux 对应使用 `.venv/bin/python`。模型来自 [OpenCV Zoo](https://github.com/opencv/opencv_zoo/tree/47534e27c9851bb1128ccc0102f1145e27f23f98/models/face_detection_yunet)，下载后进行固定 SHA-256 校验；来源和许可见 [models](models/README.md)。

## 整理照片

```text
军训/
  2026-8-26/
    DSC_3901.NEF
    DSC_3901.jpg
  2026-8-27/
    任意子目录/
      DSC_4001.NEF
      DSC_4001-已增强-NR 拷贝.jpg
```

日期来自目录名，不依赖文件修改时间。日期目录下可以有多层子目录，扩展名大小写均支持。新增日期或补入 JPG 后重新构建即可。

配对优先同目录同名；否则按同日期内唯一相机编号（例如 `DSC_3901`）匹配，兼容上述导出后缀。存在多个候选时不猜测，只发布 JPG 并写入本地报告。导出 JPG 时保留原始编号，可以提高配对可靠性。

## 构建与预览

以下路径为示例。输出目录必须与照片目录分离。

```powershell
# 照片还没准备好：只生成等待页面，不复制照片。
.venv\Scripts\python scripts/build_album.py --source 'E:\照片\军训' --output output/site --inventory-only

# JPG 准备好：生成相册与人脸取景缩略图。
.venv\Scripts\python scripts/build_album.py --source 'E:\照片\军训' --output output/site

# 可选：复制已配对的 NEF，开启原片下载。需要预留原片空间。
.venv\Scripts\python scripts/build_album.py --source 'E:\照片\军训' --output output/site --include-nef

.venv\Scripts\python -m http.server 8765 --bind 127.0.0.1 --directory output/site
```

打开本机 `http://127.0.0.1:8765/`。输出目录旁的 `site-report.json` 记录数量、取景方式和配对问题，报告不属于发布内容。

默认遇到损坏或内容不符的 JPG 时停止，保留旧索引。确实希望跳过时才增加 `--skip-invalid`，所有跳过项写入报告。`--center-crop` 可明确停用人脸检测。

缩略图、预览图去掉 EXIF；下载 JPG/NEF 保持原文件字节，包括原有元数据。正式分享前应检查 GPS 等信息。人脸检测可能漏掉侧脸、遮挡和远景小脸，不能保证每张都选中最佳构图。

## 部署与分享

见 [自有服务器部署说明](deploy/README.md)。无需域名，直接打开 `https://[公网IPv6]:端口/` 会自动跳转到相册，原来的完整分享路径仍有效。

- 访问者的网络必须支持 IPv6。
- 分享路径不是身份认证，拿到链接的人都能访问和转发。
- IPv6 变化后自动维护匹配证书，但旧链接、二维码仍需替换。
- 维护任务失败记录到 systemd 日志，不代表已经通知管理员。

生成分享二维码：

```powershell
.venv\Scripts\python scripts/make_qr.py 'https://[你的公网IPv6]:8444/你的分享路径/'
```

照片、人物索引、模型、日志、真实链接、服务器配置和凭据不进入 Git。

## 验证

```powershell
python -m unittest discover -s tests -v
node --test tests/catalog.test.js
node --check web/app.js
node --check web/catalog.js
```

测试覆盖真实 CLI 输入、配对歧义、MPO 格式、无效输入、索引保留、源目录边界、人脸取景几何、筛选与资源路径约束。它们不代替真实照片抽查、移动端浏览和独立外网测试。

语言与协作要求见 [开发约定](AGENTS.md)。
