#!/usr/bin/env python3
"""僅在實際看過原圖與此頁合併檔預覽後，記錄逐頁驗收。"""
import argparse
from datetime import datetime,timezone
from workflow import manifest_data,read_json,write_json,audit_deck,sha256,cli_error
from validate_batch import validate_batch

def record_review(manifest_file,page_id,notes,status='passed',accepted=()):
    validate_batch(manifest_file,False)
    base,manifest=manifest_data(manifest_file);built=read_json(base/'build-report.json');render=read_json(base/'previews/render.json')
    if render['deckSha256']!=built['deck']['sha256']:raise ValueError('預覽不是目前簡報。')
    index=next((i for i,p in enumerate(manifest['pages']) if p['id']==page_id),None)
    if index is None:raise ValueError('沒有這個頁面 id。')
    page=built['pages'][index];image=render['images'][index];audit=audit_deck(built['deck']['path'])
    if image['slide']!=index+1 or sha256(image['path'])!=image['sha256']:raise ValueError('預覽已變更。')
    result={'page':page_id,'status':status,'notes':notes,'reviewedAt':datetime.now(timezone.utc).isoformat(),
            'sourceSha256':page['sourceSha256'],'sceneSha256':page['sceneSha256'],'renderSha256':image['sha256'],
            'slideFingerprint':audit['slides'][index]['fingerprint'],'acceptedAutoDownsizes':list(accepted),'renderer':render['engine']}
    target=base/'reviews'/f'{page_id}.json';write_json(target,result);return target
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('manifest');p.add_argument('--page',required=True);p.add_argument('--notes',required=True);p.add_argument('--status',choices=['passed','needs-fix'],default='passed');p.add_argument('--accept-downsize',action='append',default=[]);a=p.parse_args()
    try:print(record_review(a.manifest,a.page,a.notes,a.status,a.accept_downsize));return 0
    except Exception as error:return cli_error(error)
if __name__=='__main__':raise SystemExit(main())
