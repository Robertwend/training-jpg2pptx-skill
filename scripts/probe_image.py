#!/usr/bin/env python3
"""跨平臺圖片盤點；本機 OCR 僅供逐字核對的草稿。"""
import argparse
import json
import shutil
import subprocess
from PIL import Image,ImageOps
from pathlib import Path
from workflow import sha256,cli_error
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('image');p.add_argument('--ocr',action='store_true');p.add_argument('--lang',default='chi_tra+eng');a=p.parse_args()
    try:
        file=Path(a.image).expanduser().resolve()
        with Image.open(file) as raw:
            image=ImageOps.exif_transpose(raw)
            result={'path':str(file),'format':raw.format,'widthPx':image.width,'heightPx':image.height,'exifOrientation':raw.getexif().get(274,1),'sha256':sha256(file)}
        if a.ocr:
            command=shutil.which('tesseract')
            if command:
                run=subprocess.run([command,str(file),'stdout','-l',a.lang,'--psm','11'],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=120)
                result['ocrDraft']=run.stdout if run.returncode==0 else None
                result['ocrWarning']=run.stderr.strip() if run.returncode else 'OCR 草稿須對照原圖核對。'
            else:result['ocrWarning']='未安裝 Tesseract；可繼續離線人工辨識，不需要雲端 token。'
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except Exception as error:return cli_error(error)
if __name__=='__main__':raise SystemExit(main())
