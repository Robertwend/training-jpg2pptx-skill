#!/usr/bin/env python3
"""使用 PowerPoint 原生匯入既有簡報，保留文字、圖形、表格、圖表與備註。"""
import argparse
import os
import shutil
import tempfile
from pathlib import Path
from workflow import audit_deck,natural_key,run_office,write_json,sha256,cli_error
from restore_backgrounds import restore_backgrounds

def semantic_slide(slide):
    return {key:slide[key] for key in ('shapeCount','imageCount','tableCount','chartCount','chartData','hyperlinks','notes')} | {'texts':[item['text'] for item in slide['texts']]}
def merge_decks(inputs,output,force=False):
    output=Path(output).resolve();files=[];seen=set()
    for item in inputs:
        item=Path(item).resolve()
        if item==output:raise ValueError('輸出不得覆寫明列的來源檔。')
        candidates=sorted(item.glob('*.pptx'),key=natural_key) if item.is_dir() else [item]
        for file in candidates:
            if file==output:continue
            if not file.is_file() or file.suffix.lower()!='.pptx':raise ValueError(f'來源不是 PPTX：{file}')
            if file not in seen:files.append(file);seen.add(file)
    if not files:raise ValueError('沒有可合併的 PPTX。')
    if output in seen:raise ValueError('輸出不得覆寫來源。')
    if output.exists() and not force:raise ValueError('輸出已存在；請換檔名，或確認後加 --force。')
    if output.suffix.lower()!='.pptx':raise ValueError('輸出須為 .pptx。')
    audits=[audit_deck(file) for file in files];size=audits[0]['sizeEmu']
    if any(a['sizeEmu']!=size for a in audits):raise ValueError('既有簡報畫布尺寸不同；請從場景用 contain 重建合併，避免默默縮放原生物件。')
    expected=[slide for audit in audits for slide in audit['slides']]
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='merge-',dir=output.parent) as directory:
        staged=Path(directory)/'merged.pptx'
        copies=[]
        for number,audit in enumerate(audits,1):
            copy=Path(directory)/f'source_{number:04d}.pptx';shutil.copyfile(audit['path'],copy)
            copies.append({'path':str(copy),'slideCount':audit['slideCount']})
        run_office({'mode':'merge','sources':copies,'sizeEmu':size,'output':str(staged)})
        restore_backgrounds(files,staged)
        actual=audit_deck(staged)
        if actual['slideCount']!=len(expected):raise ValueError('合併後頁數錯誤。')
        warnings=[]
        for number,(before,after) in enumerate(zip(expected,actual['slides']),1):
            if semantic_slide(before)!=semantic_slide(after):raise ValueError(f'第 {number} 頁原生內容／備註發生變化，不交付此合併檔。')
            if before['imageHashes']!=after['imageHashes']:warnings.append(f'第 {number} 頁圖片可能被 PowerPoint 重新編碼，請渲染對照。')
        for a in audits:
            if sha256(a['path'])!=a['sha256']:raise ValueError('合併期間來源檔被修改。')
        os.replace(staged,output)
    report={'output':str(output),'sha256':sha256(output),'slideCount':len(expected),'sources':[{'path':a['path'],'sha256':a['sha256'],'slideCount':a['slideCount']} for a in audits],'warnings':warnings,'visualReviewRequired':True}
    write_json(output.with_suffix('.merge-report.json'),report);return report
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('inputs',nargs='+');p.add_argument('--output',required=True);p.add_argument('--force',action='store_true');a=p.parse_args()
    try:r=merge_decks(a.inputs,a.output,a.force);print(f"已原生合併 {r['slideCount']} 頁；請再逐頁渲染檢視。");return 0
    except Exception as error:return cli_error(error)
if __name__=='__main__':raise SystemExit(main())
