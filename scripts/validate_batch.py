#!/usr/bin/env python3
"""核對頁序、來源、內容、原生物件與逐頁視覺驗收證據。"""
import argparse
from pathlib import Path
from workflow import manifest_data,read_json,resolve,sha256,audit_deck,write_json,cli_error
from merge_pptx import semantic_slide

def validate_batch(manifest_file,final=True):
    base,manifest=manifest_data(manifest_file);report=read_json(base/'build-report.json')
    if [p['id'] for p in manifest['pages']]!=[p['id'] for p in report['pages']]:raise ValueError('頁面順序或清單已變更，請重新建置。')
    deck=report['deck'];path=Path(deck['path'])
    if path!=resolve(base,manifest.get('output','merged.pptx')) or sha256(path)!=deck['sha256']:raise ValueError('合併檔與建置報告不一致。')
    audit=audit_deck(path)
    if audit['slideCount']!=len(manifest['pages']):raise ValueError('漏頁或多頁。')
    expected_size=[round(report['canvas']['width']*914400),round(report['canvas']['height']*914400)]
    if any(abs(a-b)>1 for a,b in zip(audit['sizeEmu'],expected_size)):raise ValueError('投影片畫布變更。')
    if final and not (base/'previews/render.json').is_file():raise ValueError('尚未渲染目前合併檔。')
    render=read_json(base/'previews/render.json') if final else None
    if final and (render['deckSha256']!=deck['sha256'] or len(render['images'])!=audit['slideCount']):raise ValueError('預覽不是目前合併檔，請重新渲染。')
    if final and render.get('engine') not in ('PowerPoint','LibreOffice'):raise ValueError('尚未使用實際簡報渲染器產生預覽。')
    for index,(page,built,slide) in enumerate(zip(manifest['pages'],report['pages'],audit['slides'])):
        scene_path=resolve(base,page['scene']);source=resolve(base,page['source']);scene=read_json(scene_path)
        if sha256(source)!=page['sourceSha256'] or page['sourceSha256']!=built['sourceSha256']:raise ValueError(f"{page['id']} 來源已變更。")
        if sha256(scene_path)!=built['sceneSha256'] or scene.get('source',{}).get('sha256')!=page['sourceSha256']:raise ValueError(f"{page['id']} 場景已變更或與來源不符。")
        if any(sha256(asset['path'])!=asset['sha256'] for asset in built.get('assets',[])):raise ValueError(f"{page['id']} 圖片素材已變更。")
        single=built['singleDeck']
        if sha256(single['path'])!=single['sha256']:raise ValueError(f"{page['id']} 單頁檔已被修改。")
        single_audit=audit_deck(single['path'])
        if single_audit['slideCount']!=1 or semantic_slide(single_audit['slides'][0])!=semantic_slide(slide):raise ValueError(f"{page['id']} 合併後原生內容改變。")
        if single_audit['slides'][0]['imageHashes']!=slide['imageHashes']:raise ValueError(f"{page['id']} 合併後圖片對應錯誤。")
        native={text['name']:text['text'] for text in slide['texts']}
        for item in scene.get('content',{}).get('texts',[]):
            actual=item.get('join','\n').join(native.get(name,'') for name in item['elements']).strip()
            if actual!=item['text'].replace('\r\n','\n').strip():raise ValueError(f"{page['id']}：{item['id']} 原生文字遺失、重複或不一致。")
        if not final:continue
        image=render['images'][index]
        if image['slide']!=index+1 or sha256(image['path'])!=image['sha256']:raise ValueError(f"{page['id']} 預覽內容／順序不一致。")
        if image.get('slideFingerprint',slide['fingerprint'])!=slide['fingerprint']:raise ValueError(f"{page['id']} 預覽與版式／母片／素材不一致。")
        review_path=base/'reviews'/f"{page['id']}.json"
        if not review_path.is_file():raise ValueError(f"{page['id']} 尚未完成逐頁視覺驗收。")
        review=read_json(review_path)
        expected={'sourceSha256':page['sourceSha256'],'sceneSha256':built['sceneSha256'],'renderSha256':image['sha256'],'slideFingerprint':slide['fingerprint']}
        if review.get('status')!='passed' or any(review.get(key)!=value for key,value in expected.items()):raise ValueError(f"{page['id']} 尚未通過目前版本的逐頁視覺驗收。")
        downsized=[item['name'] for item in built['textSafety'] if item['autoDownsized']]
        if any(name not in review.get('acceptedAutoDownsizes',[]) for name in downsized):raise ValueError(f"{page['id']} 自動縮小字級尚未核對接受。")
    return {'passed':True,'stage':'final' if final else 'structural-only','slideCount':audit['slideCount'],'deck':deck,
            'renderer':render['engine'] if final else None,'letterboxedPages':[p['id'] for p in report['pages'] if p['letterboxed']],
            'rasterExceptions':[{'page':p['id'],**item} for p in report['pages'] for item in p.get('rasterExceptions',[])],
            'claim':'內容清單與逐頁驗收紀錄已核對；程式不能自行判斷原圖所有文字是否已正確辨識。'}
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('manifest');p.add_argument('--structural-only',action='store_true');a=p.parse_args()
    try:
        result=validate_batch(a.manifest,not a.structural_only);base,_=manifest_data(a.manifest);write_json(base/'validation.json',result)
        print(f"通過：{result['stage']}，{result['slideCount']} 頁");return 0
    except Exception as error:return cli_error(error)
if __name__=='__main__':raise SystemExit(main())
