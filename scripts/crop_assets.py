#!/usr/bin/env python3
"""依明確座標無損裁切素材，記錄來源與配置；不自動辨識文字或物件。"""
import argparse
import hashlib
import io
import math
import tempfile
from collections import deque
from pathlib import Path
from PIL import Image, ImageDraw, ImageOps
from workflow import read_json, write_json, sha256, cli_error

ROLES = {'photo', 'texture', 'complex-icon', 'complex-illustration', 'logo'}


def box(value, width, height, label):
    if not isinstance(value, dict):
        raise ValueError(f'{label} 必須包含 x/y/w/h。')
    numbers = [value.get(k) for k in ('x', 'y', 'w', 'h')]
    if any(type(n) is not int for n in numbers):
        raise ValueError(f'{label} 的座標必須為整數像素。')
    x, y, w, h = numbers
    if x < 0 or y < 0 or w <= 0 or h <= 0 or x+w > width or y+h > height:
        raise ValueError(f'{label} 超出來源或沒有面積；不會自動截斷。')
    return x, y, w, h


def rgb(value):
    if not isinstance(value, str) or len(value) != 6:
        raise ValueError('填色須為六位十六進位色碼。')
    try:
        return tuple(int(value[i:i+2], 16) for i in (0, 2, 4))
    except ValueError as error:
        raise ValueError('填色須為六位十六進位色碼。') from error


def remove_edge_background(image, options):
    """僅移除與邊界相連的近色背景，保留圖示內部同色區域。"""
    color = rgb(options.get('color'))
    tolerance, feather = options.get('tolerance', 10), options.get('feather', 0)
    if any(type(n) not in (int, float) or not math.isfinite(n) or n < 0 for n in (tolerance, feather)) or tolerance+feather > 255:
        raise ValueError('背景容差與羽化須為非負數，總和不得超過 255。')
    result = image.copy(); width, height = result.size; pixels = result.load()
    visited = bytearray(width*height); queue = deque()

    def visit(x, y):
        index = y*width+x
        if visited[index]:
            return
        visited[index] = 1
        pixel = pixels[x, y]
        distance = max(abs(pixel[i]-color[i]) for i in range(3))
        if distance <= tolerance+feather:
            alpha = 0 if distance <= tolerance or feather == 0 else round(255*(distance-tolerance)/feather)
            pixels[x, y] = pixel[:3]+(min(pixel[3], alpha),)
            queue.append((x, y))

    for x in range(width):
        visit(x, 0); visit(x, height-1)
    for y in range(height):
        visit(0, y); visit(width-1, y)
    while queue:
        x, y = queue.popleft()
        for nx, ny in ((x-1, y), (x+1, y), (x, y-1), (x, y+1)):
            if 0 <= nx < width and 0 <= ny < height:
                visit(nx, ny)
    return result


def crop_assets(spec_file, force=False):
    spec_file = Path(spec_file).resolve(); spec = read_json(spec_file)
    source = (spec_file.parent/spec['source']).resolve()
    output = (spec_file.parent/spec.get('outputDir', 'assets')).resolve()
    if not isinstance(spec.get('assets'), list) or not spec['assets']:
        raise ValueError('assets 須為非空清單。')
    with Image.open(source) as opened:
        reference = ImageOps.exif_transpose(opened).convert('RGBA')
    width, height = reference.size; source_hash = sha256(source)
    planned = []; names = set(); filenames = set()
    for number, asset in enumerate(spec['assets'], 1):
        name = asset.get('name'); filename = asset.get('filename', f'asset_{number:04d}.png')
        if not isinstance(name, str) or not name.strip() or name in names:
            raise ValueError('素材名稱須非空且唯一。')
        names.add(name)
        if not isinstance(filename, str) or filename in ('', '.', '..') or '/' in filename or '\\' in filename or ':' in filename or not filename.lower().endswith('.png'):
            raise ValueError('filename 須為單一 PNG 檔名，不得含路徑。')
        if filename.casefold() in filenames:
            raise ValueError('素材檔名重複。')
        filenames.add(filename.casefold())
        if asset.get('role') not in ROLES or type(asset.get('containsText')) is not bool:
            raise ValueError(f'{name} 須指定 role 與經人工判讀的 containsText。')
        x, y, w, h = box(asset.get('crop'), width, height, name)
        image = reference.crop((x, y, x+w, y+h))
        for region in asset.get('eraseRegions', []):
            if not region.get('reason', '').strip():
                raise ValueError('移除文字／底色區域須記錄 reason。')
            rx, ry, rw, rh = box(region, w, h, f'{name} 的清除區域')
            color = (0, 0, 0, 0) if region.get('fill') == 'transparent' else rgb(region.get('fill'))+(255,)
            ImageDraw.Draw(image).rectangle((rx, ry, rx+rw-1, ry+rh-1), fill=color)
        if asset.get('backgroundKey'):
            image = remove_edge_background(image, asset['backgroundKey'])
        buffer = io.BytesIO(); image.save(buffer, format='PNG'); data = buffer.getvalue()
        target = output/filename; asset_hash = hashlib.sha256(data).hexdigest()
        if target == source:
            raise ValueError('素材輸出不得覆寫原圖。')
        if target.exists() and sha256(target) != asset_hash and not force:
            raise ValueError(f'素材已有不同內容：{target}；改名或明確加 --force。')
        element = {'type': 'image', 'name': name, 'path': str(target), 'x': x, 'y': y, 'w': w, 'h': h,
                   'role': asset['role'], 'containsText': asset['containsText'], 'altText': asset.get('altText', name),
                   'sourceCrop': {'sourcePath': str(source), 'sourceSha256': source_hash, 'assetSha256': asset_hash,
                                  'referenceWidthPx': width, 'referenceHeightPx': height, 'x': x, 'y': y, 'w': w, 'h': h}}
        planned.append((target, data, element, asset))
    report_path = output/'crop-report.json'
    if report_path.exists() and not force:
        previous = read_json(report_path)
        if previous.get('sourceSha256') != source_hash or previous.get('spec') != str(spec_file):
            raise ValueError('此素材目錄屬於其他來源／規格；請選新目錄或明確加 --force。')
    output.mkdir(parents=True, exist_ok=True)
    for target, data, _, _ in planned:
        if not target.exists() or sha256(target) != hashlib.sha256(data).hexdigest():
            with tempfile.NamedTemporaryFile(dir=output, suffix='.tmp.png', delete=False) as stream:
                stream.write(data); temporary=Path(stream.name)
            try:temporary.replace(target)
            finally:
                if temporary.exists():temporary.unlink()
    report = {'version': 1, 'spec': str(spec_file), 'specSha256': sha256(spec_file), 'source': str(source),
              'sourceSha256': source_hash, 'referenceSizePx': [width, height], 'elements': [p[2] for p in planned],
              'operations': [{'name': p[2]['name'], 'backgroundKey': p[3].get('backgroundKey'), 'eraseRegions': p[3].get('eraseRegions', [])} for p in planned],
              'textJudgment': 'containsText 由原圖判讀填入；裁切工具不自行辨識或驗收文字。'}
    write_json(report_path, report)
    return report_path


def main():
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('spec'); parser.add_argument('--force', action='store_true')
    args = parser.parse_args()
    try:
        print(crop_assets(args.spec, args.force)); return 0
    except Exception as error:
        return cli_error(error)


if __name__ == '__main__':
    raise SystemExit(main())
