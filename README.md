# LitchiLens

用于活动照片临时分享的中文照片库，自有服务器通过 IPv6 + HTTPS 提供服务，访问者无需登录。

## 照片与版本

首页进入照片库或选择自己的自拍找照片。照片 ID 采用 `日期_DSC编号`，绑定标准转换 JPG、批量调色 JPG、精修 JPG 和 NEF。默认下载优先精修，其次批量调色；可以手动选择其他版本。每页加载 48 张缩略图，支持日期、编号和版本筛选。

只有原片根目录中数字日期文件夹内的照片进入收录范围；回收站不参与。导出的 JPG 按唯一 DSC 编号匹配入选原片，日期始终来自原片目录，忽略导出目录的日期。跨日期编号重复时不猜测配对，写入报告。根目录 `jpg` 中的旧版本标为精修；日期目录中只有 JPG 的照片也可收录。

标准转换使用 rawpy、相机白平衡、全分辨率和 sRGB，不套额外调色风格；与尼康软件或相机 Picture Control 渲染不保证完全一致。损坏的 NEF 跳过并列入 `conversion-errors.json`，不会覆盖或删除原片。

```powershell
python -m pip install -r requirements.txt
npm ci
python scripts/setup_faces.py
python scripts/convert_raw.py --source 'E:\照片\军训' --output 'E:\衍生\标准JPG' --workers 4
python scripts/build_library.py --source 'E:\照片\军训' --exports 'D:\导出JPG' --generated 'E:\衍生\标准JPG' --output 'E:\衍生\网站' --workers 4
node scripts/index_all_faces.mjs 'E:\衍生\网站' private/faces.json 4
```

衍生目录必须与输入目录分离。构建器在同磁盘上尽可能使用只读用途的硬链接，避免重复占用原片空间；不要直接编辑构建目录中的下载文件。新增调色版本应保存回独立导出目录，沿用 DSC 编号，再重新构建。构建失败保留原目录及旧索引，成功后原子替换索引。

## 人脸找照片

使用固定版本 [Human 3.3.6](https://github.com/vladmandic/human) 的 BlazeFace、FaceMesh、FaceRes；模型来源见[上游模型说明](https://github.com/vladmandic/human/wiki/Models)。离线索引与浏览器共享配置；合照分区域检测，一张照片可绑定多张脸。只保存匿名特征到私有目录，不保存姓名、年龄或性别等属性。

自拍只在访问者设备中解码并提取特征；发给服务器的是 1024 维向量，用于即时查询，不保存查询图片或向量。服务器只返回候选照片 ID，完整人物索引不公开。用户必须选择自己的照片，多人图需选择自己。结果不是身份认证或概率：远景小脸、侧脸、遮挡可能漏检，也可能误匹配。需要真实跨照片样本评估，不能以同图查询通过宣称准确率。

## 不满意、下架与管理

勾选照片后可以下载 ZIP，或填写最多 500 字的重调要求。留言只对管理员可见，绑定所选 ID。下架须二次确认，立即从目录和搜索结果中排除该 ID，并拒绝其 JPG、NEF、缩略图和预览链接。原文件保留；已经下载或缓存到设备上的文件不能撤回。

旧的固定 NEF 整包无法逐 ID 撤回，第二版部署会停用旧包入口，磁盘文件保留。批量下载改为依据当前可见 ID 生成流式 ZIP，每次最多 100 张，不在线转换原片。

管理页仅监听服务器 `127.0.0.1:8769`，不经公网 Nginx 暴露。使用 SSH 转发：

```powershell
ssh -N -L 127.0.0.1:8769:127.0.0.1:8769 <服务器SSH别名>
```

打开 `http://127.0.0.1:8769/`，查看缩略图、编号、留言、时间、状态，下载对应 NEF，导出待处理 CSV，并标记“待处理 / 处理中 / 已完成”。标记完成不会自动上传新版本。状态保存在服务器 `/var/lib/litchilens/state.json`，与照片发布目录分离；更新网站不会清空申请或解除下架。

## 部署与并发

沿用第一版的专用证书和维护定时器，第二版由 `deploy/install_library.py` 安装。将完整网站放到服务器 `/srv/litchilens/library-releases/<版本>/`，私有人脸索引另行上传，再执行：

```sh
sudo python3 deploy/install_library.py --site /srv/litchilens/library-releases/<版本> --faces /path/to/private-faces.json
```

安装前备份 Nginx 和服务配置，检查 Nginx 配置，启动回环 API 后 reload，并校验证书链、有效期及地址匹配；失败回滚。首次安装证书仍可参考 [部署说明](deploy/README.md)，旧静态发布器不适用于第二版照片库。

- 大文件全站最多 4 路，每 IP 1 路、每路 1MiB/s，合计约 4.2MB/s。
- 模型全站最多 4 路，每路 256KiB/s，合计约 1MB/s；繁忙时自动重试。
- 按约 7MB/s 上行预算，为缩略图和操作留出约 1.8MB/s；这不是链路级 QoS 保证，其他服务流量仍会影响带宽。
- 搜索最多并发 2 个，每 IP 每分钟 6 次；其他操作独立限流。
- 在线人数按最近 90 秒活跃浏览器会话估算；下载计数跟踪正在传输的任务。状态仅保存在内存中。
- 原图交给 Nginx 传输，隐藏检查由回环 API 处理，禁止直接访问内部文件路径。

页脚可显示自愿赞赏入口。将 `赞赏码.png` 放在本地原片根目录后构建；图片只复制到部署输出，不进入 Git。赞赏不影响下载和重调处理顺序。

## 验证与边界

```powershell
python -m unittest discover -s tests -p 'test_*.py'
npm test
npm run check
```

测试覆盖真实 HTTP 隐藏和 ZIP、持久化、留言、非法请求、缺失资产、目录日期和配对歧义；移动端还需实际浏览器验证。可用 `deploy/library_server.py --site <网站> --state private/test-state.json --faces private/faces.json --port 8767 --admin-port 8770` 配合 `node scripts/preview_library.mjs <网站> 8768 8767` 做本机预览。

照片、赞赏码、人脸向量、真实地址、凭据和运行数据禁止提交。局域网 HTTPS 验证不能替代独立外网验证。约定见 [AGENTS.md](AGENTS.md)。
