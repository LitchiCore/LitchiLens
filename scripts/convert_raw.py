"""只转换日期目录内入选 NEF；全分辨率 JPG 输出到独立目录，可断点续跑。"""

import os

os.environ.setdefault("OMP_NUM_THREADS", "2")
import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import date
import json
from pathlib import Path
import re
import time


def inventory(source):
    result = []
    for directory in sorted(source.iterdir()):
        if not directory.is_dir() or not re.fullmatch(r"\d{4}-\d{1,2}-\d{1,2}", directory.name):
            continue
        day = date(*map(int, directory.name.split("-"))).isoformat()
        for p in sorted(directory.rglob("*")):
            if p.is_file() and p.suffix.lower() == ".nef":
                if p.is_symlink() or not p.resolve().is_relative_to(source):
                    raise ValueError(f"不支持链接原片：{p}")
                result.append((day, p))
    keys = set()
    for day, p in result:
        key = (day, p.stem.upper())
        if key in keys:
            raise ValueError(f"同一天原片编号重复，需要先消除歧义：{key}")
        keys.add(key)
    return result


def convert(job):
    import rawpy
    from PIL import Image, ImageCms

    day, path, output = job
    p, root = Path(path), Path(output)
    stat = p.stat()
    key = {
        "source": str(p),
        "bytes": stat.st_size,
        "mtime_ns": stat.st_mtime_ns,
        "pipeline": "rawpy-camera-wb-srgb-ahd-q94-v1",
    }
    dest = root / day / (p.stem.upper() + ".jpg")
    marker = dest.with_suffix(".json")
    if dest.is_file() and marker.is_file():
        previous = json.loads(marker.read_text(encoding="utf-8"))
        if previous.get("input") == key and previous.get("jpg_bytes") == dest.stat().st_size:
            return {"day": day, "name": p.name, "cached": True}
    dest.parent.mkdir(parents=True, exist_ok=True)
    with rawpy.imread(str(p)) as raw:
        pixels = raw.postprocess(
            use_camera_wb=True,
            output_color=rawpy.ColorSpace.sRGB,
            output_bps=8,
            demosaic_algorithm=rawpy.DemosaicAlgorithm.AHD,
        )
    image = Image.fromarray(pixels)
    profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    temp = dest.with_suffix(".jpg.tmp")
    image.save(temp, "JPEG", quality=94, subsampling=0, icc_profile=profile)
    with Image.open(temp) as check:
        check.verify()
    after = p.stat()
    if (after.st_size, after.st_mtime_ns) != (stat.st_size, stat.st_mtime_ns):
        raise RuntimeError(f"转换期间原片改变：{p}")
    os.replace(temp, dest)
    record = {
        "input": key,
        "jpg_bytes": dest.stat().st_size,
        "width": image.width,
        "height": image.height,
    }
    marker.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")
    return {"day": day, "name": p.name, "cached": False, "size": image.size}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--exports", help="已有批量调色 JPG；匹配成功的编号不重复转片")
    args = parser.parse_args()
    source, output = Path(args.source).resolve(strict=True), Path(args.output).resolve()
    if source.is_relative_to(output) or output.is_relative_to(source):
        raise ValueError("衍生输出目录必须与原片目录分离")
    items = inventory(source)
    if args.exports:
        from photo_sources import collect

        records, _ = collect(source, Path(args.exports))
        needed = {record["raw"] for record in records if not record["versions"]}
        items = [(day, p) for day, p in items if p in needed]
    if args.limit:
        items = items[: args.limit]
    output.mkdir(parents=True, exist_ok=True)
    lock = output / ".convert.lock"
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    os.close(fd)
    start = time.monotonic()
    try:
        print(f"入选 NEF：{len(items)}；工作进程：{args.workers}", flush=True)
        failures = []
        with ProcessPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(convert, (day, str(p), str(output))) for day, p in items]
            inputs = dict(zip(futures, items))
            for n, future in enumerate(as_completed(futures), 1):
                try:
                    result = future.result()
                except Exception as exc:
                    day, path = inputs[future]
                    failures.append({"date": day, "path": str(path), "error": str(exc)})
                    print(f"转换失败：{path.name}：{exc}", flush=True)
                    result = {"name": path.name}
                if n % 25 == 0 or n == len(items):
                    print(
                        f"已转换 {n}/{len(items)}；耗时 {time.monotonic() - start:.0f} 秒；{result['name']}",
                        flush=True,
                    )
        (output / "conversion-errors.json").write_text(
            json.dumps(failures, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"转换完成；失败 {len(failures)} 张（见 conversion-errors.json）", flush=True)
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
