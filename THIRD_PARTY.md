# 第三方依赖与模型

本项目原创代码采用 [MIT 许可证](LICENSE)。第三方软件、预训练模型和用户照片不由本项目重新授权；安装、分发模型时应保留其许可证与来源说明。

| 组件                  | 用途                         | 上游说明                                                                                                                    |
| --------------------- | ---------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| Human 3.3.6           | 浏览器本地人脸特征、离线索引 | [代码与 MIT 许可证](https://github.com/vladmandic/human)、[模型来源与署名](https://github.com/vladmandic/human/wiki/Models) |
| OpenCV Zoo YuNet      | 缩略图人脸取景               | [固定模型与校验值](models/README.md)、[模型 MIT 许可证](models/LICENSE.yunet)                                               |
| TensorFlow.js         | Human 的推理运行时           | [上游仓库](https://github.com/tensorflow/tfjs)                                                                              |
| rawpy / LibRaw        | NEF 离线转 JPG               | [rawpy](https://github.com/letmaik/rawpy)、[LibRaw](https://www.libraw.org/)                                                |
| Pillow、OpenCV、NumPy | 图片处理                     | 版本范围见 `requirements.txt`                                                                                               |
| sharp                 | 离线索引解码、缩放           | 版本与传递依赖见 `package-lock.json`                                                                                        |
| qrcode                | 本地生成分享二维码           | 版本范围见 `requirements.txt`                                                                                               |

仓库不包含模型权重。YuNet 由脚本从固定上游版本下载并校验 SHA-256；Human 的所需模型随 npm 依赖安装，在构建时复制到网站输出。Human 模型的原始出处和限制以对应上游模型说明为准，不应把本项目的 MIT 许可证理解成对全部模型、训练数据或照片的授权。

构建产物包含 Human 的原始许可证。开源仓库不包含用户照片、人脸特征、赞赏码、线上目录或运行状态。
