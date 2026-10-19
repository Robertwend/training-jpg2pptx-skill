#!/usr/bin/env python3
"""僅在實際看過原圖與此頁合併檔預覽後，記錄逐頁驗收。"""
import argparse
from datetime import datetime,timezone
from workflow import manifest_data,read_json,write_json,audit_deck,sha256,cli_error
from validate_batch import validate_batch

def record_reviews(manifest_file,page_ids,notes,status='passed',accepted=()):
    page_ids=list(page_ids)
    if not page_ids or len(page_ids)!=len(set(page_ids)):raise ValueError('請明列已檢視的頁面 id，不能重複。')
    if not str(notes).strip() or status not in ('passed','needs-fix'):raise ValueError('須提供實際檢視說明與有效狀態。')
    validate_batch(manifest_file,False)
    base,manifest=manifest_data(manifest_file);built=read_json(base/'build-report.json');render=read_json(base/'previews/render.json')
    if render['deckSha256']!=built['deck']['sha256']:raise ValueError('預覽不是目前簡報。')
    indexes={p['id']:i for i,p in enumerate(manifest['pages'])}
    if any(page_id not in indexes for page_id in page_ids):raise ValueError('沒有這個頁面 id。')
    audit=audit_deck(built['deck']['path']);pending=[]
    for page_id in page_ids:
        index=indexes[page_id];page=built['pages'][index];image=render['images'][index]
        if image['slide']!=index+1 or sha256(image['path'])!=image['sha256']:raise ValueError('預覽已變更。')
        if image.get('slideFingerprint',audit['slides'][index]['fingerprint'])!=audit['slides'][index]['fingerprint']:raise ValueError('預覽與目前頁面依賴不一致。')
        result={'page':page_id,'status':status,'notes':notes,'reviewedAt':datetime.now(timezone.utc).isoformat(),
                'sourceSha256':page['sourceSha256'],'sceneSha256':page['sceneSha256'],'renderSha256':image['sha256'],
                'slideFingerprint':audit['slides'][index]['fingerprint'],'acceptedAutoDownsizes':list(accepted),'renderer':render['engine']}
        pending.append((base/'reviews'/f'{page_id}.json',result))
    for target,result in pending:write_json(target,result)
    return [p[0] for p in pending]

def record_review(manifest_file,page_id,notes,status='passed',accepted=()):
    return record_reviews(manifest_file,[page_id],notes,status,accepted)[0]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('manifest');group=p.add_mutually_exclusive_group(required=True);group.add_argument('--page');group.add_argument('--pages',nargs='+');p.add_argument('--notes',required=True);p.add_argument('--status',choices=['passed','needs-fix'],default='passed');p.add_argument('--accept-downsize',action='append',default=[]);a=p.parse_args()
    try:
        for target in record_reviews(a.manifest,a.pages or [a.page],a.notes,a.status,a.accept_downsize):print(target)
        return 0
    except Exception as error:return cli_error(error)
if __name__=='__main__':raise SystemExit(main())
