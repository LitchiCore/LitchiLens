"""生成不含真人和原片的色卡示例，通过真实构建器创建可运行照片库。"""

import argparse
from pathlib import Path
from PIL import Image, ImageDraw
from build_library import build


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("output/demo"))
    args = parser.parse_args()
    root = args.output.resolve()
    if root.exists():
        parser.error("演示目录已存在，请用 --output 指定一个新目录，避免覆盖文件")
    source, exports, generated = root / "source", root / "exports", root / "generated"
    for directory in (source, exports, generated):
        directory.mkdir(parents=True)
    for number, color in enumerate(("#729b78", "#88a9bb", "#c79e71"), 1):
        day = source / ("2026-01-01" if number < 3 else "2026-01-02")
        day.mkdir(exist_ok=True)
        image = Image.new("RGB", (1200, 900), color)
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((100, 100, 1100, 800), 48, outline="white", width=8)
        draw.text((180, 400), f"LitchiLens Demo {number:02d}", fill="white", font_size=64)
        image.save(day / f"DSC_{number:04d}.jpg", quality=90)
    build(source, exports, generated, root / "site", center=True, workers=1)
    print(f"演示已生成：{root / 'site'}；这些图片均为程序绘制的色卡。")


if __name__ == "__main__":
    main()
