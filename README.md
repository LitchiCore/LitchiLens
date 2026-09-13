# LitchiLens

用于活动照片临时分享的中文照片库，自有服务器通过 IPv6 + HTTPS 提供服务，访问者无需登录。

## 快速体验

需要 Python 3.12+、Node.js 24 和 npm。网站前端是原生 JavaScript，后端使用 Python 标准库；不需要账号系统或数据库。

```sh
git clone https://github.com/LitchiCore/LitchiLens.git
cd LitchiLens
python -m pip install -r requirements.txt
npm ci
python scripts/create_demo.py
```

演示脚本只绘制 3 张色卡，再通过真实构建器生成 `output/demo/site`。不包含真人、NEF 或人物特征；未配置赞赏码时不显示赞赏入口。目录已存在会拒绝覆盖，可用 `--output` 指定新目录。

在一个终端启动 API：

```sh
python deploy/library_server.py --site output/demo/site --state output/demo/state.json --port 8767 --admin-port 8770
```

另一个终端启动本机网页：

```sh
node scripts/preview_library.mjs output/demo/site 8768 8767
```

浏览器打开 `http://127.0.0.1:8768/`；演示管理页为 `http://127.0.0.1:8770/`。预览服务仅监听本机，不能直接用作公网服务器。自拍检索需要另行生成私人索引；演示不会伪造检索结果。

## 目录

| 目录       | 用途                                        |
| ---------- | ------------------------------------------- |
| `web/`     | 手机优先的照片库、下载、自拍检索界面        |
| `scripts/` | 离线转换、构建、索引和本机演示              |
| `deploy/`  | Linux API、管理员入口、HTTPS 维护与共享限速 |
| `tests/`   | 合成图片、真实 HTTP 与文件边界测试          |
| `models/`  | 模型来源、校验值和许可证，不含权重          |

`build_album.py`、`deploy/install.py`、`deploy/publish.py` 和 `web/packages*` 保留用于旧版兼容与首次证书初始化。新照片库使用 `build_library.py` 和 `install_library.py`，不要用旧发布器更新第二版站点。

## 照片与版本

首页进入照片库或选择自己的自拍找照片。照片 ID 采用 `日期_DSC编号`，绑定标准转换 JPG、批量调色 JPG、精调 JPG 和 NEF。默认下载优先精调，其次批量调色；可以手动选择其他版本。每页加载 48 张缩略图，支持日期、编号和版本筛选。

只有原片根目录中数字日期文件夹内的照片进入收录范围；回收站不参与。导出的 JPG 按唯一 DSC 编号匹配入选原片，日期始终来自原片目录，忽略导出目录的日期。跨日期编号重复时不猜测配对，写入报告。根目录 `jpg` 中的旧版本标为精调；日期目录中只有 JPG 的照片也可收录。

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

勾选照片后，1～10 个可用文件直接下载，超过 10 个才打 ZIP；支持一键连续下载，也保留逐文件链接，供阻止连续下载的手机浏览器使用。也可以填写最多 500 字的重调要求。留言只对管理员可见，绑定所选 ID。下架须二次确认，立即从目录和搜索结果中排除该 ID，并拒绝其 JPG、NEF、缩略图和预览链接。原文件保留；已经下载或缓存到设备上的文件不能撤回。

旧的固定 NEF 整包无法逐 ID 撤回，第二版部署会停用旧包入口，磁盘文件保留。大批量下载依据当前可见 ID 生成流式 ZIP，每次最多 100 张，不在线转换原片；缺失版本或已下架的照片不计入 10 个文件的打包门槛。

管理页仅监听服务器 `127.0.0.1:8769`，不经公网 Nginx 暴露。使用 SSH 转发：

```powershell
ssh -N -L 127.0.0.1:8769:127.0.0.1:8769 <服务器SSH别名>
```

打开 `http://127.0.0.1:8769/`，查看缩略图、编号、留言、时间、状态，下载对应 NEF，导出待处理 CSV，并标记“待处理 / 处理中 / 已完成”。标记完成不会自动上传新版本。状态保存在服务器 `/var/lib/litchilens/state.json`，与照片发布目录分离；更新网站不会清空申请或解除下架。

## 部署与并发

生产环境需要自有 Linux 服务器、公网 IPv6、Nginx 和有效 HTTPS 证书。完整的首次安装、共享限速、更新和关闭步骤见 [部署说明](deploy/README.md)。不要把原片目录直接作为网站根目录。

- 网站端口共享 48Mbit/s（约 6MB/s）出口，取消逐连接固定限速。空闲连接可以使用全部额度；HTB 控制总量，fq_codel 按 TCP 流公平分配并照顾短请求，实际份额受客户端网络影响，不是严格按人数均分。
- 大文件全站最多 128 路，其中流式 ZIP 最多 16 路，为 API 留出工作线程；取消每 IP 只能一路的限制。模型最多 4 路，不再设单连接速率。
- 下载、预览和模型共同使用网站额度；按约 7MB/s 上行留约 1MB/s 链路余量。其他端口不受此队列限额约束，其他服务大量上传仍会影响网站速度。
- 搜索最多并发 2 个，每 IP 每分钟 6 次；其他操作独立限流。
- 在线人数按最近 90 秒活跃浏览器会话估算；下载计数跟踪正在传输的任务。在线与下载状态仅保存在内存中，匿名浏览器标识保存在访问者设备中以避免刷新重复计数。没有历史独立访客或逐照片下载排行。
- 原图交给 Nginx 传输，隐藏检查由回环 API 处理，禁止直接访问内部文件路径。

页头和页脚可显示自愿赞赏入口。将 `赞赏码.png` 放在本地原片根目录后构建；图片只复制到部署输出，不进入 Git。赞赏不影响下载和重调处理顺序。

## 验证与边界

```powershell
python -m unittest discover -s tests -p 'test_*.py'
npm test
npm run check
```

测试覆盖真实 HTTP 隐藏和 ZIP、持久化、留言、非法请求、缺失资产、目录日期和配对歧义；移动端还需实际浏览器验证。可用 `deploy/library_server.py --site <网站> --state private/test-state.json --faces private/faces.json --port 8767 --admin-port 8770` 配合 `node scripts/preview_library.mjs <网站> 8768 8767` 做本机预览。

照片、赞赏码、人脸向量、真实地址、凭据和运行数据禁止提交。局域网 HTTPS 验证不能替代独立外网验证。约定见 [AGENTS.md](AGENTS.md)。

## 开发与许可证

```sh
python -m pip install -r requirements-dev.txt
python -m ruff check scripts deploy tests
python -m ruff format --check scripts deploy tests
npm run format:check
```

修改后可用 `python -m ruff format scripts deploy tests` 和 `npm run format` 统一格式。CI 使用合成图片构建演示，并验证真实浏览器下载。也可在本机生成上述演示后执行 `npx playwright install chromium`、`npm run smoke`；指定 Python 路径时设置 `PYTHON` 环境变量。

原创代码采用 [MIT](LICENSE)。第三方库与模型遵循各自许可，见 [第三方说明](THIRD_PARTY.md)。`package.json` 中保留 `private: true` 仅用于防止误发 npm 包，不影响 GitHub 开源。

这是面向受邀活动参与者的临时分享工具：公开访问者能够提交重调申请，也能在二次确认后下架照片，不适合直接当作不受信任人群使用的开放图库。照片所有者需自行确定分享范围；人脸检索只提供相似候选，不提供身份确认。
