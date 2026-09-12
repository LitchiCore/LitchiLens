"""将入选原片和多份 JPG 合并为稳定照片 ID，输出独立可发布目录。"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
from concurrent.futures import ProcessPoolExecutor, as_completed
from PIL import Image, ImageOps
from photo_sources import collect
from thumbnails import FaceDetector, make_thumbnail
from build_album import atomic_bytes, save_jpeg

ROOT = Path(__file__).resolve().parents[1]

def asset(source, output, folder, suffix):
    before = source.stat()
    with source.open('rb') as handle:
        digest = hashlib.file_digest(handle, 'sha256').hexdigest()
    target = f'{folder}/{digest}{suffix}'
    dest = output / target
    if not dest.exists():
        temp = dest.with_suffix(dest.suffix + '.tmp')
        temp.unlink(missing_ok=True)
        try:
            os.link(source, temp)
        except OSError:
            shutil.copyfile(source, temp)
        os.replace(temp, dest)
    after = source.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError(f'构建时输入发生变化：{source}')
    return {'url': target, 'bytes': before.st_size, 'sha256': digest}

_detector = None

def build_photo(record, output, center):
    global _detector
    if not center and _detector is None:
        _detector = FaceDetector()
    raw, versions = record.pop('raw'), record.pop('versions')
    if not versions:
        return None, {'id': record['id'], 'raw': str(raw), 'reason': '没有可用 JPG，暂不发布'}
    published, seen = [], set()
    for version in versions:
        p = version['path']
        file = asset(p, output, 'downloads', '.jpg')
        if file['sha256'] in seen:
            continue
        seen.add(file['sha256'])
        identity = file['sha256']
        thumb_path, preview_path = f'media/{identity}-0.jpg', f'media/{identity}-1.jpg'
        with Image.open(p) as opened:
            if opened.format not in ('JPEG', 'MPO'):
                raise ValueError(f'无效 JPG：{p}')
            image = ImageOps.exif_transpose(opened).convert('RGB')
            width, height = image.size
            if not (output / thumb_path).exists():
                thumb, _ = make_thumbnail(image, None if center else _detector)
                save_jpeg(thumb, output / thumb_path, 82)
            if not (output / preview_path).exists():
                image.thumbnail((1920,1920), Image.Resampling.LANCZOS)
                save_jpeg(image, output / preview_path, 85)
        published.append({'id': identity, 'label': version['label'], 'jpg': file,
                          'thumb': thumb_path, 'preview': preview_path, 'width': width, 'height': height})
    record['versions'] = published
    for key in ('thumb','preview','jpg','width','height'):
        record[key] = published[0][key]
    record['nef'] = asset(raw, output, 'downloads', '.nef') if raw else None
    if raw:
        record['nef']['name'] = raw.name
    return record, None

def build(source, exports, generated, output, center=False, workers=4):
    source = source.resolve(strict=True)
    output = output.resolve()
    for input_root in (source, exports.resolve(), generated.resolve()):
        if input_root.is_relative_to(output) or output.is_relative_to(input_root):
            raise ValueError('输出目录与输入目录必须分离')
    output.mkdir(parents=True, exist_ok=True)
    marker = output / '.litchilens-library'
    if any(output.iterdir()) and not marker.exists():
        raise ValueError('输出目录包含其他文件')
    marker.touch()
    lock = output / '.build.lock'
    fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY); os.close(fd)
    try:
        for folder in ('media', 'downloads'):
            (output / folder).mkdir(exist_ok=True)
        records, warnings = collect(source, exports, generated)
        photos, missing = [], []
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(build_photo, record, output, center) for record in records]
            for n, future in enumerate(as_completed(futures),1):
                photo, warning = future.result()
                if photo: photos.append(photo)
                if warning: missing.append(warning)
                if n % 50 == 0 or n == len(records):
                    print(f'已构建 {n}/{len(records)} 个 ID', flush=True)
        photos.sort(key=lambda p:p['id'])
        for path in (ROOT / 'web').rglob('*'):
            if path.is_file():
                target = output / path.relative_to(ROOT / 'web')
                target.parent.mkdir(parents=True, exist_ok=True)
                atomic_bytes(target, path.read_bytes())
        vendor = output / 'vendor'
        vendor.mkdir(exist_ok=True)
        npm = ROOT / 'node_modules' / '@vladmandic' / 'human'
        shutil.copyfile(npm / 'dist' / 'human.esm.js', vendor / 'human.esm.js')
        shutil.copyfile(npm / 'LICENSE', vendor / 'HUMAN-LICENSE.txt')
        models = vendor / 'models'; models.mkdir(exist_ok=True)
        for name in ('blazeface', 'facemesh', 'faceres'):
            for suffix in ('.json','.bin'):
                shutil.copyfile(npm / 'models' / (name+suffix), models / (name+suffix))
        sponsor = source / '赞赏码.png'
        if sponsor.is_file():
            shutil.copyfile(sponsor, output / 'sponsor.png')
        catalog = {'version': 2, 'title': '军训影集', 'updated': datetime.now(timezone.utc).isoformat(),
                   'dates': sorted({p['date'] for p in photos}), 'photos': photos}
        atomic_bytes(output / 'catalog.json', json.dumps(catalog, ensure_ascii=False, separators=(',',':')).encode())
        report = dict(warnings, missing_jpg=missing, ids=len(photos), versions=sum(len(p['versions']) for p in photos))
        atomic_bytes(output.parent / (output.name+'-report.json'), json.dumps(report, ensure_ascii=False, indent=2).encode())
        print(f'构建完成：{len(photos)} 个 ID，{report["versions"]} 个 JPG 版本；缺少 JPG：{len(missing)}', flush=True)
        return catalog
    finally:
        lock.unlink(missing_ok=True)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('source','exports','generated','output'):
        parser.add_argument('--'+name, required=True, type=Path)
    parser.add_argument('--center-crop', action='store_true')
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    build(args.source,args.exports,args.generated,args.output,args.center_crop,args.workers)
