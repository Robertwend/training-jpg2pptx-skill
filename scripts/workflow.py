"""批次流程共用：檔案指紋、順序與 OOXML 稽核；不辨識圖片內容。"""
from __future__ import annotations
import hashlib
import io
import json
import os
import posixpath
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

NS = {'p':'http://schemas.openxmlformats.org/presentationml/2006/main',
      'a':'http://schemas.openxmlformats.org/drawingml/2006/main',
      'r':'http://schemas.openxmlformats.org/officeDocument/2006/relationships',
      'rel':'http://schemas.openxmlformats.org/package/2006/relationships',
      'c':'http://schemas.openxmlformats.org/drawingml/2006/chart'}
IMAGE_SUFFIXES = {'.png','.jpg','.jpeg','.webp','.bmp','.tif','.tiff'}
for _stream in (sys.stdout,sys.stderr):
    if hasattr(_stream,'reconfigure'):_stream.reconfigure(encoding='utf-8')
def sha256(file):
    with open(file,'rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()
def read_json(file):
    return json.loads(Path(file).read_text(encoding='utf-8-sig'))
def write_json(file,value):
    file=Path(file);file.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile('w',encoding='utf-8',dir=file.parent,delete=False) as stream:
        json.dump(value,stream,ensure_ascii=False,indent=2);stream.write('\n');temporary=stream.name
    os.replace(temporary,file)
def natural_key(value):
    return [int(part) if part.isdigit() else part.casefold() for part in re.split(r'(\d+)',str(value))]
def resolve(base,value):
    return (Path(base)/value).resolve()
def manifest_data(file):
    file=Path(file).resolve(); data=read_json(file)
    if data.get('version')!=2 or not data.get('pages'):raise ValueError('需要非空的 version: 2 批次清單。')
    ids=[p['id'] for p in data['pages']]
    if len(ids)!=len(set(ids)):raise ValueError('批次頁面 id 重複。')
    if any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,80}',value) for value in ids):raise ValueError('頁面 id 不得含路徑或特殊字元。')
    return file.parent,data
def rels_name(part):
    return posixpath.join(posixpath.dirname(part),'_rels',posixpath.basename(part)+'.rels')
def resolve_part(owner,target):
    target=urllib.parse.unquote(target.split('#',1)[0])
    result=posixpath.normpath(target.lstrip('/') if target.startswith('/') else posixpath.join(posixpath.dirname(owner),target))
    if result.startswith('../'):raise ValueError('套件關聯指向封裝外部。')
    return result
def relationships(archive,part):
    filename=rels_name(part)
    if filename not in archive.namelist():return {}
    return {r.attrib['Id']:{'part':None if r.get('TargetMode')=='External' else resolve_part(part,r.attrib['Target']),
                            'type':r.attrib['Type'],'target':r.attrib['Target'],'external':r.get('TargetMode')=='External'} for r in ET.fromstring(archive.read(filename))}
def text_body(node):
    paragraphs=[]
    for p in node.findall('a:p',NS):
        paragraphs.append(''.join(e.text or '' if e.tag==f"{{{NS['a']}}}t" else '\n' if e.tag==f"{{{NS['a']}}}br" else '' for e in p.iter()))
    return '\n'.join(paragraphs).replace('\r\n','\n').strip()
def chart_payload(archive,part):
    root=ET.fromstring(archive.read(part))
    result={'values':[e.text or '' for e in root.findall('.//c:v',NS)],'labels':[e.text or '' for e in root.findall('.//a:t',NS)],'workbooks':[]}
    for rel in relationships(archive,part).values():
        if rel['type'].endswith('/package') and rel['part']:
            workbook={}
            with zipfile.ZipFile(io.BytesIO(archive.read(rel['part']))) as embedded:
                sheet_ns={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
                for name in sorted(embedded.namelist()):
                    if name.startswith('xl/worksheets/') and name.endswith('.xml'):
                        cells=[]
                        for cell in ET.fromstring(embedded.read(name)).findall('.//s:c',sheet_ns):
                            formula=cell.find('s:f',sheet_ns);value=cell.find('s:v',sheet_ns)
                            cells.append([cell.get('r'),cell.get('t'),formula.text if formula is not None else None,value.text if value is not None else None,
                                          [e.text or '' for e in cell.findall('.//s:t',sheet_ns)]])
                        workbook[name]=cells
                    elif name=='xl/sharedStrings.xml':workbook[name]=[e.text or '' for e in ET.fromstring(embedded.read(name)).findall('.//s:t',sheet_ns)]
            result['workbooks'].append(workbook)
    return result
def audit_deck(file):
    file=Path(file).resolve()
    with zipfile.ZipFile(file) as z:
        if z.testzip():raise ValueError('PPTX 壓縮資料損壞。')
        names=set(z.namelist())
        if len(names)!=len(z.namelist()):raise ValueError('PPTX 有重複封裝項目。')
        for name in names:
            if name.endswith('.xml') or name.endswith('.rels'):ET.fromstring(z.read(name))
            if name.endswith('.rels'):
                owner='' if name=='_rels/.rels' else posixpath.join(posixpath.dirname(posixpath.dirname(name)),posixpath.basename(name)[:-5])
                for rel in ET.fromstring(z.read(name)):
                    if rel.get('TargetMode')=='External' and not rel.attrib['Type'].endswith('/hyperlink'):
                        raise ValueError(f'來源有未嵌入的外連資源，請先嵌入以確保可攜交付：{name}')
                    if rel.get('TargetMode')!='External' and resolve_part(owner,rel.attrib['Target']) not in names:
                        raise ValueError(f'關聯遺失：{name} → {rel.attrib["Target"]}')
            if name.startswith(('ppt/slides/','ppt/slideLayouts/','ppt/slideMasters/')) and name.endswith('.xml'):
                for e in ET.fromstring(z.read(name)).iter():
                    if e.tag in (f"{{{NS['a']}}}normAutofit",f"{{{NS['a']}}}spAutoFit"):
                        raise ValueError(f'延遲自動適配標記：{name}')
        pres=ET.fromstring(z.read('ppt/presentation.xml'));size=pres.find('p:sldSz',NS)
        pr=relationships(z,'ppt/presentation.xml');slides=[]
        for slide_id in pres.findall('p:sldIdLst/p:sldId',NS):
            part=pr[slide_id.attrib[f"{{{NS['r']}}}id"]]['part'];root=ET.fromstring(z.read(part));rels=relationships(z,part)
            summary={'shapeCount':0,'imageCount':0,'tableCount':0,'chartCount':0,'texts':[],'imageHashes':[],'notes':[],'chartData':[],
                     'hyperlinks':[rel['target'] for rel in rels.values() if rel['type'].endswith('/hyperlink')]}
            for e in root.iter():
                if e.tag not in [f"{{{NS['p']}}}{tag}" for tag in ('sp','pic','graphicFrame','cxnSp')]:continue
                summary['shapeCount']+=1
                nv=e.find('.//p:cNvPr',NS);name=nv.get('name','') if nv is not None else ''
                table=e.find('.//a:tbl',NS)
                if table is not None:
                    summary['tableCount']+=1
                    text='\n'.join('\t'.join(text_body(cell.find('a:txBody',NS)) for cell in row.findall('a:tc',NS)) for row in table.findall('a:tr',NS))
                else:
                    tx=e.find('p:txBody',NS);text=text_body(tx) if tx is not None else ''
                if text:summary['texts'].append({'name':name,'text':text})
                if e.tag==f"{{{NS['p']}}}pic":summary['imageCount']+=1
                if e.find('.//c:chart',NS) is not None:summary['chartCount']+=1
            for blip in root.findall('.//a:blip',NS):
                rel=rels.get(blip.get(f"{{{NS['r']}}}embed"))
                if rel and rel['part']:summary['imageHashes'].append(hashlib.sha256(z.read(rel['part'])).hexdigest())
            for rel in rels.values():
                if rel['type'].endswith('/chart') and rel['part']:summary['chartData'].append(chart_payload(z,rel['part']))
                if rel['type'].endswith('/notesSlide') and rel['part']:
                    notes=ET.fromstring(z.read(rel['part']))
                    for shape in notes.findall('.//p:sp',NS):
                        ph=shape.find('.//p:ph',NS)
                        if ph is not None and ph.get('type') in ('sldNum','hdr','ftr','dt'):continue
                        tx=shape.find('p:txBody',NS)
                        if tx is not None and text_body(tx):summary['notes'].append(text_body(tx))
            payload=z.read(part)+b''.join(z.read(rel['part']) for rel in rels.values() if rel['part'] and not rel['type'].endswith(('/slideLayout','/notesSlide')))
            summary['fingerprint']=hashlib.sha256(payload).hexdigest();slides.append(summary)
        if not slides:raise ValueError('簡報沒有投影片。')
    return {'path':str(file),'sha256':sha256(file),'slideCount':len(slides),'sizeEmu':[int(size.get('cx')),int(size.get('cy'))],'slides':slides}
def run_office(request,timeout=240):
    if os.name!='nt':raise RuntimeError('此動作需要 Windows 與 Microsoft PowerPoint；場景資料的直接合併仍可跨平臺使用。')
    shell=shutil.which('pwsh') or shutil.which('powershell')
    if not shell:raise RuntimeError('找不到 PowerShell。')
    with tempfile.TemporaryDirectory(prefix='training-office-') as directory:
        request_path=Path(directory)/'request.json';write_json(request_path,request)
        result=subprocess.run([shell,'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(Path(__file__).with_name('office_bridge.ps1')),'-RequestPath',str(request_path)],capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout)
        if result.returncode:raise RuntimeError(f'PowerPoint 操作失敗：{result.stderr[-2000:]} {result.stdout[-1000:]}')
def cli_error(error):
    print(f'錯誤：{error}',file=sys.stderr);return 1
