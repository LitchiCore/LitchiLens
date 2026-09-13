"""用真实 CLI 验证索引发布、失败保留、下载文件与配对边界。"""

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from thumbnails import crop_box


class AlbumTest(unittest.TestCase):
    def test_cli_and_failure_retention(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "photos"
            day = source / "2026-8-26"
            day.mkdir(parents=True)
            jpg = day / "DSC_0001-已增强-NR 拷贝.jpg"
            Image.new("RGB", (120, 180), "green").save(jpg)
            raw = day / "DSC_0001.NEF"
            raw.write_bytes(b"test-only-raw-download")
            output = base / "site"
            command = [
                sys.executable,
                str(ROOT / "scripts/build_album.py"),
                "--source",
                str(source),
                "--output",
                str(output),
                "--center-crop",
                "--include-nef",
            ]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            catalog = json.loads((output / "catalog.json").read_text(encoding="utf8"))
            photo = catalog["photos"][0]
            self.assertEqual(photo["date"], "2026-08-26")
            self.assertEqual((output / photo["jpg"]["url"]).read_bytes(), jpg.read_bytes())
            self.assertEqual((output / photo["nef"]["url"]).read_bytes(), raw.read_bytes())
            with Image.open(output / photo["thumb"]) as image:
                self.assertEqual(image.size, (480, 360))
            previous = (output / "catalog.json").read_bytes()
            (day / "broken.jpg").write_bytes(b"broken")
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual((output / "catalog.json").read_bytes(), previous)
            result = subprocess.run(command + ["--skip-invalid"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                len(json.loads((output / "catalog.json").read_text(encoding="utf8"))["photos"]), 1
            )
            self.assertIn("已跳过", (base / "site-report.json").read_text(encoding="utf8"))

    def test_ambiguous_nef_and_source_boundary(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            source = base / "photos"
            day = source / "2026-8-26"
            day.mkdir(parents=True)
            Image.new("RGB", (100, 100)).save(day / "DSC_0001 拷贝.jpg")
            for folder in ["a", "b"]:
                (day / folder).mkdir()
                (day / folder / "DSC_0001.NEF").write_bytes(b"raw")
            output = base / "site"
            command = [
                sys.executable,
                str(ROOT / "scripts/build_album.py"),
                "--source",
                str(source),
                "--output",
                str(output),
                "--center-crop",
                "--include-nef",
            ]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIsNone(
                json.loads((output / "catalog.json").read_text(encoding="utf8"))["photos"][0]["nef"]
            )
            self.assertIn("歧义", (base / "site-report.json").read_text(encoding="utf8"))
            command[command.index("--output") + 1] = str(source / "output")
            self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
            self.assertFalse((source / "output").exists())

    def test_face_crop_geometry(self):
        # 人脸靠近顶部：不能按画面中心裁掉额头。
        box = crop_box((600, 1200), [(250, 20, 100, 120)])
        self.assertLessEqual(box[1], 20)
        self.assertGreaterEqual(box[3], 140)
        # 跨上下边缘的合照无法容纳在横向窗口中，应保留全画面。
        self.assertIsNone(crop_box((600, 1200), [(20, 10, 100, 100), (450, 1050, 100, 100)]))
        self.assertEqual(crop_box((600, 1200), []), (0, 375, 600, 825))

    def test_multi_picture_jpg(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            day = base / "photos" / "2026-8-26"
            day.mkdir(parents=True)
            Image.new("RGB", (80, 100), "blue").save(
                day / "DSC_0010.JPG",
                format="MPO",
                save_all=True,
                append_images=[Image.new("RGB", (80, 100), "red")],
            )
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/build_album.py"),
                    "--source",
                    str(base / "photos"),
                    "--output",
                    str(base / "site"),
                    "--center-crop",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                len(json.loads((base / "site/catalog.json").read_text(encoding="utf8"))["photos"]),
                1,
            )


if __name__ == "__main__":
    unittest.main()
