"""将日期目录中的 JPG 构建为静态相册。源目录只读，发布索引最后原子替换。"""

import argparse
from collections import defaultdict, Counter
from datetime import date, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
from PIL import Image, ImageOps
from thumbnails import FaceDetector, make_thumbnail

ROOT = Path(__file__).resolve().parents[1]
WEB_FILES = (
    "index.html",
    "style.css",
    "app.js",
    "catalog.js",
    "icon.svg",
    "packages.html",
    "packages.js",
    "packages-data.js",
    "packages.css",
)
PIPELINE = "thumb-yunet-v1"


def folder_date(path):
    for part in reversed(path.parts[:-1]):
        if re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", part):
            try:
                return date(*map(int, part.split("-"))).isoformat()
            except ValueError as exc:
                raise ValueError(f"日期目录无效：{part}") from exc
    raise ValueError(f"照片不在日期目录中：{path}")


def camera_key(path):
    # 支持 Lightroom 常见导出后缀；仅使用完整的相机编号，不做模糊数字匹配。
    match = re.match(r"^(DSC_\d+)(?:$|[-_ ])", path.stem, re.I)
    return match.group(1).casefold() if match else path.stem.casefold()


def pair_nef(jpg, day, raw_index):
    candidates = raw_index.get((day, camera_key(jpg)), [])
    exact = [
        p for p in candidates if p.parent == jpg.parent and p.stem.casefold() == jpg.stem.casefold()
    ]
    if len(exact) == 1:
        return exact[0], None
    if len(candidates) == 1:
        return candidates[0], None
    return None, ("NEF 配对存在歧义，未提供原片下载" if candidates else "没有匹配的 NEF")


def atomic_bytes(path, content):
    temp = path.with_name(path.name + ".tmp")
    temp.write_bytes(content)
    os.replace(temp, path)


def atomic_copy(source, destination):
    if destination.is_file() and destination.stat().st_size == source.stat().st_size:
        return
    temp = destination.with_name(destination.name + ".tmp")
    shutil.copyfile(source, temp)
    os.replace(temp, destination)


def save_jpeg(image, path, quality):
    temp = path.with_name(path.name + ".tmp")
    # 显式去掉 EXIF；预览不携带 GPS、相机序列号或人物信息。
    image.save(temp, "JPEG", quality=quality, optimize=True, progressive=True, exif=b"")
    os.replace(temp, path)


def build(args):
    source = Path(args.source).resolve(strict=True)
    output = Path(args.output).resolve()
    if not source.is_dir():
        raise ValueError("源路径必须是照片目录。")
    if source.is_relative_to(output) or output.is_relative_to(source):
        raise ValueError("输出目录必须与照片目录分离，不能互相包含。")
    if output.exists() and any(output.iterdir()) and not (output / ".litchilens-output").is_file():
        raise ValueError("输出目录已有其他文件，请选择新的目录。")
    # 同一输出目录只允许一个构建进程。
    output.mkdir(parents=True, exist_ok=True)
    lock = output / ".build.lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError as exc:
        raise ValueError(
            "此输出目录正在构建；若上次中断，请确认无构建进程后移除 .build.lock。"
        ) from exc
    os.close(fd)
    try:
        (output / ".litchilens-output").touch()
        return build_locked(args, source, output)
    finally:
        lock.unlink(missing_ok=True)


def build_locked(args, source, output):
    images, raw_index, dates = [], defaultdict(list), set()
    # 不跟随目录符号链接，也拒绝文件链接指向源目录之外。
    for directory, dirs, files in os.walk(source, followlinks=False):
        dirs[:] = sorted(d for d in dirs if not (Path(directory) / d).is_symlink())
        for name in sorted(files):
            path = Path(directory) / name
            suffix = path.suffix.lower()
            if suffix not in (".jpg", ".jpeg", ".nef"):
                continue
            if path.is_symlink() or not path.resolve().is_relative_to(source):
                raise ValueError(f"不支持链接照片：{path.relative_to(source)}")
            day = folder_date(path.relative_to(source))
            dates.add(day)
            if suffix == ".nef":
                raw_index[day, camera_key(path)].append(path)
            else:
                images.append((day, path))
    detector = (
        FaceDetector() if images and not args.inventory_only and not args.center_crop else None
    )
    for name in ("media", "downloads"):
        (output / name).mkdir(exist_ok=True)
    photos, warnings, modes = [], [], Counter()
    for number, (day, path) in enumerate(sorted(images), 1):
        if args.inventory_only:
            break
        before = path.stat()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        relative = path.relative_to(source).as_posix()
        identity = hashlib.sha256(
            (relative + digest + PIPELINE + str(args.center_crop)).encode()
        ).hexdigest()[:24]
        thumb_path = f"media/{identity}-0.jpg"
        preview_path = f"media/{identity}-1.jpg"
        try:
            with Image.open(path) as opened:
                if opened.format not in ("JPEG", "MPO"):
                    raise ValueError("文件内容不是 JPEG")
                # 某些 JPG 含 MPF 多图结构；取主画面生成普通 JPEG 预览。
                opened.seek(0)
                image = ImageOps.exif_transpose(opened).convert("RGB")
                width, height = image.size
                if not (output / thumb_path).is_file():
                    thumb, mode = make_thumbnail(image, detector)
                    save_jpeg(thumb, output / thumb_path, 82)
                    modes[mode] += 1
                else:
                    modes["复用缩略图"] += 1
                if not (output / preview_path).is_file():
                    preview = image.copy()
                    preview.thumbnail((1920, 1920), Image.Resampling.LANCZOS)
                    save_jpeg(preview, output / preview_path, 85)
        except Exception as exc:
            if args.skip_invalid:
                warnings.append({"photo": relative, "reason": f"已跳过无效 JPG：{exc}"})
                continue
            raise ValueError(f"照片处理失败：{relative}：{exc}") from exc
        jpg_url = f"downloads/{identity}.jpg"
        atomic_copy(path, output / jpg_url)
        if (path.stat().st_size, path.stat().st_mtime_ns) != (before.st_size, before.st_mtime_ns):
            raise ValueError(f"构建期间照片发生变化，请重试：{relative}")
        raw, warning = pair_nef(path, day, raw_index)
        if warning:
            warnings.append({"photo": relative, "reason": warning})
        record = {
            "id": identity,
            "name": path.name,
            "date": day,
            "width": width,
            "height": height,
            "thumb": thumb_path,
            "preview": preview_path,
            "jpg": {"url": jpg_url, "bytes": before.st_size},
            "nef": None,
        }
        if raw and args.include_nef:
            raw_stat = raw.stat()
            raw_tag = hashlib.sha256(
                f"{raw.relative_to(source)}:{raw_stat.st_size}:{raw_stat.st_mtime_ns}".encode()
            ).hexdigest()[:16]
            raw_url = f"downloads/{identity}-{raw_tag}.nef"
            atomic_copy(raw, output / raw_url)
            if (raw.stat().st_size, raw.stat().st_mtime_ns) != (
                raw_stat.st_size,
                raw_stat.st_mtime_ns,
            ):
                raise ValueError(f"构建期间 NEF 发生变化：{raw.name}")
            record["nef"] = {"url": raw_url, "bytes": raw_stat.st_size, "name": raw.name}
        photos.append(record)
        if number % 10 == 0 or number == len(images):
            print(f"已处理 {number}/{len(images)} 张 JPG", flush=True)
    for name in WEB_FILES:
        atomic_bytes(output / name, (ROOT / "web" / name).read_bytes())
    atomic_bytes(output / "robots.txt", b"User-agent: *\nDisallow: /\n")
    catalog = {
        "version": 1,
        "title": args.title,
        "updated": datetime.now(timezone.utc).isoformat(),
        "dates": sorted(dates),
        "photos": photos,
    }
    report = {
        "jpg_found": len(images),
        "nef_found": sum(map(len, raw_index.values())),
        "published": len(photos),
        "thumbnail_modes": dict(modes),
        "warnings": warnings,
        "inventory_only": args.inventory_only,
    }
    report_path = output.parent / f"{output.name}-report.json"
    atomic_bytes(report_path, json.dumps(report, ensure_ascii=False, indent=2).encode())
    # 只有所有照片成功处理后才替换索引；失败不会发布半成品相册。
    atomic_bytes(
        output / "catalog.json",
        json.dumps(catalog, ensure_ascii=False, separators=(",", ":")).encode(),
    )
    print(json.dumps({k: v for k, v in report.items() if k != "warnings"}, ensure_ascii=False))
    print(f"配对提示 {len(warnings)} 条，详见 {report_path}")
    return catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, help="照片根目录，包含日期子目录")
    parser.add_argument("--output", required=True, help="独立输出目录")
    parser.add_argument("--title", default="军训影集", help="相册标题")
    parser.add_argument(
        "--inventory-only", action="store_true", help="只生成等待照片页面，不发布任何照片"
    )
    parser.add_argument(
        "--include-nef", action="store_true", help="复制配对成功的 NEF，开启原片下载"
    )
    parser.add_argument("--center-crop", action="store_true", help="停用人脸检测，统一居中裁剪")
    parser.add_argument(
        "--skip-invalid", action="store_true", help="显式跳过损坏或扩展名不符的 JPG，并记录报告"
    )
    args = parser.parse_args()
    try:
        build(args)
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"构建失败：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
