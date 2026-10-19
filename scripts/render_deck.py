#!/usr/bin/env python3
"""產生固定順序的逐頁預覽與綁定簡報指紋的渲染紀錄。"""
import argparse
import os
import shutil
import subprocess
import tempfile
from time import perf_counter
from pathlib import Path
from workflow import audit_deck,sha256,read_json,write_json,run_office,cli_error

def render_deck(deck,out,engine='auto',width=1680,force=False):
    started=perf_counter()
    if engine not in ('auto','powerpoint','libreoffice'):raise ValueError('無效渲染器。')
    if type(width) is not int or width<100:raise ValueError('預覽寬度必須至少 100 像素。')
    if engine=='powerpoint' and os.name!='nt':raise RuntimeError('PowerPoint 渲染需要 Windows。')
    deck=Path(deck).resolve();out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
    audit=audit_deck(deck);height=round(width*audit['sizeEmu'][1]/audit['sizeEmu'][0]);actual_engine=None;warnings=[]
    audit_ms=round((perf_counter()-started)*1000)
    signature={'script':sha256(__file__),'officeBridge':sha256(Path(__file__).with_name('office_bridge.ps1')),'width':width,'height':height}
    previous={}
    if not force and (out/'render.json').is_file():
        try:previous=read_json(out/'render.json')
        except (ValueError,OSError):warnings.append('舊渲染紀錄無法讀取，將重新渲染。')
    expected_engine='PowerPoint' if engine=='powerpoint' or engine=='auto' and os.name=='nt' else 'LibreOffice'
    reusable={}
    if previous.get('signature')==signature and previous.get('engine')==expected_engine:
        for image in previous.get('images',[]):
            file=Path(image.get('path',''))
            if image.get('slideFingerprint') and file.is_file() and sha256(file)==image.get('sha256'):
                reusable[image['slideFingerprint']]=image
    reused=[];changed=[];exported=[]
    with tempfile.TemporaryDirectory(prefix='render-',dir=out.parent) as temporary:
        temp=Path(temporary)
        # 先將可復用頁全部暫存，避免換頁序時覆寫尚未複製的預覽。
        for number,slide in enumerate(audit['slides'],1):
            cached=reusable.get(slide['fingerprint'])
            if cached:shutil.copyfile(cached['path'],temp/f'slide_{number:04d}.png');reused.append(number)
            else:changed.append(number)
        # 使用獨立副本，避免 COM 開啟到使用者已開啟的同一份簡報。
        office_input=temp/'render-input.pptx'
        if changed:shutil.copyfile(deck,office_input)
        else:actual_engine=previous['engine']
        if changed and engine in ('auto','powerpoint') and os.name=='nt':
            try:
                run_office({'mode':'render','input':str(office_input),'output':str(temp),'width':width,'height':height,'slides':changed})
                actual_engine='PowerPoint';exported=list(changed)
            except Exception as error:
                if engine=='powerpoint':raise
                warnings.append(str(error))
        if actual_engine is None:
            # 更換渲染器時整批重作，避免同一份紀錄混用不同渲染器的預覽。
            if previous.get('engine')!='LibreOffice':changed=list(range(1,audit['slideCount']+1));reused=[]
            office=shutil.which('soffice') or shutil.which('libreoffice')
            if not office and os.name=='nt':
                candidate=Path(os.environ.get('ProgramFiles','C:/Program Files'))/'LibreOffice/program/soffice.exe'
                if candidate.exists():office=str(candidate)
            if not office:raise RuntimeError('找不到 PowerPoint 或 LibreOffice，無法宣稱已完成視覺驗收。')
            profile=(temp/'lo-profile').as_uri()
            result=subprocess.run([office,f'-env:UserInstallation={profile}','--headless','--convert-to','pdf','--outdir',str(temp),str(office_input)],capture_output=True,timeout=180)
            pdf=temp/'render-input.pdf'
            if result.returncode or not pdf.exists():raise RuntimeError('LibreOffice 轉 PDF 失敗。')
            import fitz
            with fitz.open(pdf) as document:
                if len(document)!=audit['slideCount']:raise RuntimeError('PDF 頁數與簡報不同。')
                for number,page in enumerate(document,1):
                    if number in changed:page.get_pixmap(matrix=fitz.Matrix(width/page.rect.width,width/page.rect.width),alpha=False).save(temp/f'slide_{number:04d}.png')
            actual_engine='LibreOffice';exported=list(changed)
        images=[]
        for number in range(1,audit['slideCount']+1):
            source=temp/f'slide_{number:04d}.png'
            if not source.is_file():raise RuntimeError(f'缺少第 {number} 頁渲染。')
            target=out/source.name;shutil.copyfile(source,target)
            images.append({'slide':number,'path':str(target),'sha256':sha256(target),'slideFingerprint':audit['slides'][number-1]['fingerprint']})
    report={'version':2,'deck':str(deck),'deckSha256':sha256(deck),'engine':actual_engine,'width':width,'height':height,'images':images,'warnings':warnings,
            'signature':signature,'reusedSlides':reused,'exportedSlides':exported,'performance':{'auditMs':audit_ms,'totalMs':round((perf_counter()-started)*1000)}}
    write_json(out/'render.json',report);return report
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('deck');p.add_argument('--out',required=True);p.add_argument('--engine',choices=['auto','powerpoint','libreoffice'],default='auto');p.add_argument('--width',type=int,default=1680);p.add_argument('--force',action='store_true');a=p.parse_args()
    try:
        if a.width<100:raise ValueError('預覽寬度必須至少 100 像素。')
        result=render_deck(a.deck,a.out,a.engine,a.width,a.force);print(f"預覽 {len(result['images'])} 頁（{result['engine']}；新渲染 {len(result['exportedSlides'])}，復用 {len(result['reusedSlides'])}）");return 0
    except Exception as error:return cli_error(error)
if __name__=='__main__':raise SystemExit(main())
