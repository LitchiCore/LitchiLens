"""离线缩略图取景：保留检测到的人脸，原片保持只读。"""
from PIL import Image, ImageOps
from setup_faces import verify_model


class FaceDetector:
    def __init__(self):
        import cv2
        cv2.setNumThreads(2)
        self.cv2 = cv2
        self.detector = cv2.FaceDetectorYN.create(str(verify_model()), '', (320, 320), 0.8, 0.3, 5000)

    def detect(self, image):
        import numpy as np
        # 限制推理尺寸；只在离线导入时计算，不增加网站访问时的负载。
        sample = image.copy()
        sample.thumbnail((1280, 1280), Image.Resampling.LANCZOS)
        frame = self.cv2.cvtColor(np.array(sample.convert('RGB')), self.cv2.COLOR_RGB2BGR)
        self.detector.setInputSize(sample.size)
        _, faces = self.detector.detect(frame)
        if faces is None:
            return []
        sx, sy = image.width / sample.width, image.height / sample.height
        return [(float(x) * sx, float(y) * sy, float(w) * sx, float(h) * sy) for x, y, w, h, *_ in faces]


def crop_box(size, faces, ratio=4 / 3):
    """返回最大面积的 4:3 取景框；无法容纳人脸及边距时返回 None。"""
    width, height = size
    crop_w, crop_h = (height * ratio, height) if width / height > ratio else (width, width / ratio)
    if not faces:
        left, top = (width - crop_w) / 2, (height - crop_h) / 2
    else:
        # 给头顶和侧面留余地，避免紧贴人脸边界裁剪。
        x1 = max(0, min(x - w * 0.25 for x, y, w, h in faces))
        y1 = max(0, min(y - h * 0.5 for x, y, w, h in faces))
        x2 = min(width, max(x + w * 1.25 for x, y, w, h in faces))
        y2 = min(height, max(y + h * 1.25 for x, y, w, h in faces))
        if x2 - x1 > crop_w or y2 - y1 > crop_h:
            return None
        left = min(max((x1 + x2 - crop_w) / 2, 0, x2 - crop_w), width - crop_w, x1)
        top = min(max((y1 + y2 - crop_h) / 2, 0, y2 - crop_h), height - crop_h, y1)
    return tuple(round(v) for v in (left, top, left + crop_w, top + crop_h))


def make_thumbnail(image, detector):
    faces = detector.detect(image) if detector else []
    box = crop_box(image.size, faces)
    if box is None:
        thumb = ImageOps.pad(image, (480, 360), color='#18231c', method=Image.Resampling.LANCZOS)
        return thumb, '完整画面'
    return image.crop(box).resize((480, 360), Image.Resampling.LANCZOS), ('人脸取景' if faces else '居中取景')
