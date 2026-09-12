"""入选日期目录是日期与收录范围的唯一依据。"""
from collections import defaultdict
from pathlib import Path
from convert_raw import inventory
from build_album import camera_key

def collect(source, exports=None, generated=None):
    raws = inventory(source)
    by_key = defaultdict(list)
    records = {}
    for day, raw in raws:
        key = camera_key(raw)
        identity = f'{day}_{key.upper()}'
        records[identity] = {'id': identity, 'name': key.upper(), 'date': day, 'raw': raw, 'versions': []}
        by_key[key].append(identity)
    unmatched, ambiguous = [], []
    roots = [(source / 'jpg', '精修', 0)]
    if exports:
        roots.append((exports, '批量调色', 1))
    if generated:
        roots.append((generated, '标准转换', 2))
    # 日期目录自带的 JPG 作为相机 JPG，不误标成精修。
    roots.extend((directory, '相机 JPG', 3) for directory in source.iterdir()
                 if directory.is_dir() and directory.name[:4].isdigit())
    for root, label, priority in roots:
        if not root.exists():
            continue
        for p in sorted(root.rglob('*')):
            if not p.is_file() or p.suffix.lower() not in ('.jpg', '.jpeg'):
                continue
            candidates = by_key.get(camera_key(p), [])
            if not candidates and label == '相机 JPG':
                from build_album import folder_date
                day = folder_date(p.relative_to(source))
                key = camera_key(p)
                identity = f'{day}_{key.upper()}'
                records[identity] = {'id': identity, 'name': key.upper(), 'date': day, 'raw': None, 'versions': []}
                by_key[key].append(identity)
                candidates = [identity]
            if len(candidates) != 1:
                (ambiguous if candidates else unmatched).append(str(p))
                continue
            records[candidates[0]]['versions'].append({'path': p, 'label': label, 'priority': priority})
    for record in records.values():
        record['versions'].sort(key=lambda v: (v['priority'], -v['path'].stat().st_mtime_ns, str(v['path'])))
    return list(records.values()), {'unmatched_jpg': unmatched, 'ambiguous_jpg': ambiguous}
