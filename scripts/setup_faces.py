"""下载并校验官方 YuNet 模型，不下载照片、不访问识别云服务。"""

import hashlib
from pathlib import Path
import urllib.request

REVISION = "47534e27c9851bb1128ccc0102f1145e27f23f98"
MODEL_NAME = "face_detection_yunet_2026may.onnx"
MODEL_SHA256 = "ebafce4e3c118d6554634be5c27ab333b4c047a9a8c3faf1d7cf93101c22f0f0"
MODEL_PATH = Path(__file__).resolve().parents[1] / "models" / MODEL_NAME
URL = f"https://media.githubusercontent.com/media/opencv/opencv_zoo/{REVISION}/models/face_detection_yunet/{MODEL_NAME}"


def verify_model(path=MODEL_PATH):
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != MODEL_SHA256:
        raise RuntimeError("人脸检测模型不存在或校验失败，请先执行 python scripts/setup_faces.py")
    return path


def main():
    if MODEL_PATH.is_file():
        verify_model()
        print("人脸检测模型已就绪，SHA-256 校验通过。")
        return
    with urllib.request.urlopen(URL, timeout=60) as response:
        data = response.read(1024 * 1024)
    if hashlib.sha256(data).hexdigest() != MODEL_SHA256:
        raise RuntimeError("模型下载校验失败，未保存文件。")
    MODEL_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp = MODEL_PATH.with_suffix(".tmp")
    temp.write_bytes(data)
    temp.replace(MODEL_PATH)
    print("已下载官方 YuNet 模型（约 230 KB），SHA-256 校验通过。")


if __name__ == "__main__":
    main()
