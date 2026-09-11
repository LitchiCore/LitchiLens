# 人脸检测模型

使用 OpenCV Zoo 的 YuNet，仅输出人脸位置，用于缩略图取景。不提取身份特征、不关联姓名，也不保存人脸框。

运行 `python scripts/setup_faces.py` 下载模型；下载内容必须匹配脚本中固定的 SHA-256。模型文件被 Git 忽略，不进入网站发布目录。

- 来源：[OpenCV Zoo / YuNet](https://github.com/opencv/opencv_zoo/tree/47534e27c9851bb1128ccc0102f1145e27f23f98/models/face_detection_yunet)
- 模型：`face_detection_yunet_2026may.onnx`
- 许可：[MIT](LICENSE.yunet)
- 检测不到人脸时使用居中取景；检测可能漏掉远景、侧脸或遮挡人脸。
