#!/usr/bin/env python3
"""盤點來源與續作清單，不會假裝已完成圖片理解或重建。"""
import argparse
from pathlib import Path
from PIL import Image,ImageOps
from workflow import IMAGE_SUFFIXES,sha256,read_json,write_json,natural_key,cli_error

def prepare(inputs,work,output=None,recursive=False):
    work=Path(work).expanduser().resolve();work.mkdir(parents=True,exist_ok=True)
    manifest_path=work/'batch.json';old=read_json(manifest_path) if manifest_path.exists() else {'version':2,'pages':[]}
    if old.get('version')!=2:raise ValueError('現有清單版本不同，請使用新的工作目錄。')
    old_pages={str(Path(p['source']).resolve()):p for p in old['pages']};files=[];seen=set()
    for value in inputs:
        value=Path(value).expanduser().resolve()
        if not value.exists():raise ValueError(f'來源不存在：{value}')
        if value.is_file() and value.suffix.lower() not in IMAGE_SUFFIXES:raise ValueError(f'不支援的圖片：{value}')
        candidates=sorted((value.rglob('*') if recursive else value.iterdir()),key=lambda p:natural_key(p.relative_to(value))) if value.is_dir() else [value]
        for file in candidates:
            if not file.is_file() or file.suffix.lower() not in IMAGE_SUFFIXES:continue
            if value.is_dir() and work!=value and work in file.parents:continue
            if file not in seen:files.append(file);seen.add(file)
    if not files:raise ValueError('沒有找到支援的圖片；接受 PNG、JPG、JPEG、WEBP、BMP、TIFF。')
    next_id=max([int(p['id'].split('_')[-1]) for p in old['pages']]+[0])+1;pages=[]
    for file in files:
        previous=old_pages.get(str(file));page_id=previous['id'] if previous else f'page_{next_id:04d}'
        if not previous:next_id+=1
        with Image.open(file) as raw:
            image=ImageOps.exif_transpose(raw);width,height=image.size
            reference=str(file)
            if raw.getexif().get(274,1)!=1:
                normalized=work/'sources'/f'{page_id}.png';normalized.parent.mkdir(exist_ok=True);image.save(normalized);reference=str(normalized)
        pages.append({'id':page_id,'source':str(file),'reference':reference,'sourceSha256':sha256(file),'widthPx':width,'heightPx':height,
                      'scene':previous.get('scene') if previous else f'scenes/{page_id}.json','single':f'pages/{page_id}.pptx'})
    first=pages[0];width=13.333333333 if first['widthPx']>=first['heightPx'] else 7.5*first['widthPx']/first['heightPx']
    result={'version':2,'title':old.get('title','圖片批次重建簡報'),'canvas':old.get('canvas',{'widthIn':width,'heightIn':width*first['heightPx']/first['widthPx'],'fit':'contain'}),
            'output':str(Path(output).expanduser().resolve()) if output else old.get('output','merged.pptx'),'pages':pages}
    for directory in ('scenes','assets','pages','previews','reviews'):(work/directory).mkdir(exist_ok=True)
    write_json(manifest_path,result);return manifest_path
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('inputs',nargs='+');p.add_argument('--work',required=True);p.add_argument('--output');p.add_argument('--recursive',action='store_true');a=p.parse_args()
    try:print(prepare(a.inputs,a.work,a.output,a.recursive));return 0
    except Exception as error:return cli_error(error)
if __name__=='__main__':raise SystemExit(main())
