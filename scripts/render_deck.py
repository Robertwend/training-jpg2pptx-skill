#!/usr/bin/env python3
"""產生固定順序的逐頁預覽與綁定簡報指紋的渲染紀錄。"""
import argparse
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from workflow import audit_deck,sha256,write_json,run_office,cli_error

def render_deck(deck,out,engine='auto',width=1680):
    deck=Path(deck).resolve();out=Path(out).resolve();out.mkdir(parents=True,exist_ok=True)
    audit=audit_deck(deck);height=round(width*audit['sizeEmu'][1]/audit['sizeEmu'][0]);actual_engine=None;warnings=[]
    with tempfile.TemporaryDirectory(prefix='render-',dir=out.parent) as temporary:
        temp=Path(temporary)
        # 使用獨立副本，避免 COM 開啟到使用者已開啟的同一份簡報。
        office_input=temp/'render-input.pptx';shutil.copyfile(deck,office_input)
        if engine in ('auto','powerpoint') and os.name=='nt':
            try:
                run_office({'mode':'render','input':str(office_input),'output':str(temp),'width':width,'height':height})
                actual_engine='PowerPoint'
            except Exception as error:
                if engine=='powerpoint':raise
                warnings.append(str(error))
        elif engine=='powerpoint':raise RuntimeError('PowerPoint 渲染需要 Windows。')
        if actual_engine is None:
            office=shutil.which('soffice') or shutil.which('libreoffice')
            if not office and os.name=='nt':
                candidate=Path(os.environ.get('ProgramFiles','C:/Program Files'))/'LibreOffice/program/soffice.exe'
                if candidate.exists():office=str(candidate)
            if not office:raise RuntimeError('找不到 PowerPoint 或 LibreOffice，無法宣稱已完成視覺驗收。')
            profile=(temp/'lo-profile').as_uri()
            result=subprocess.run([office,f'-env:UserInstallation={profile}','--headless','--convert-to','pdf','--outdir',str(temp),str(deck)],capture_output=True,timeout=180)
            pdf=temp/(deck.stem+'.pdf')
            if result.returncode or not pdf.exists():raise RuntimeError('LibreOffice 轉 PDF 失敗。')
            import fitz
            with fitz.open(pdf) as document:
                if len(document)!=audit['slideCount']:raise RuntimeError('PDF 頁數與簡報不同。')
                for number,page in enumerate(document,1):
                    page.get_pixmap(matrix=fitz.Matrix(width/page.rect.width,width/page.rect.width),alpha=False).save(temp/f'slide_{number:04d}.png')
            actual_engine='LibreOffice'
        images=[]
        for number in range(1,audit['slideCount']+1):
            source=temp/f'slide_{number:04d}.png'
            if not source.is_file():raise RuntimeError(f'缺少第 {number} 頁渲染。')
            target=out/source.name;shutil.copyfile(source,target)
            images.append({'slide':number,'path':str(target),'sha256':sha256(target)})
    report={'version':2,'deck':str(deck),'deckSha256':sha256(deck),'engine':actual_engine,'width':width,'height':height,'images':images,'warnings':warnings}
    write_json(out/'render.json',report);return report
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('deck');p.add_argument('--out',required=True);p.add_argument('--engine',choices=['auto','powerpoint','libreoffice'],default='auto');p.add_argument('--width',type=int,default=1680);a=p.parse_args()
    try:
        if a.width<100:raise ValueError('預覽寬度必須至少 100 像素。')
        result=render_deck(a.deck,a.out,a.engine,a.width);print(f"已渲染 {len(result['images'])} 頁（{result['engine']}）");return 0
    except Exception as error:return cli_error(error)
if __name__=='__main__':raise SystemExit(main())
