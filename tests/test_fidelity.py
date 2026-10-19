"""驗證原圖素材保留、共用量測與有相依檢查的增量渲染。"""
import copy
import importlib
import json
import os
import subprocess
import sys
import types
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
from PIL import Image, ImageDraw, ImageOps
import test_workflow as fixture

ROOT=fixture.ROOT
sys.path.insert(0,str(ROOT/'scripts'))
from crop_assets import crop_assets, remove_edge_background
from workflow import read_json, write_json, sha256, audit_deck
from record_review import record_reviews


class FidelityTests(unittest.TestCase):
    setUp=fixture.WorkflowTests.setUp
    tearDown=fixture.WorkflowTests.tearDown
    batch=fixture.WorkflowTests.batch

    @classmethod
    def setUpClass(cls):
        fixture.WorkflowTests.setUpClass.__func__(cls)

    def crops(self, source, assets):
        spec=self.directory/'crops.json'
        write_json(spec,{'source':str(source),'outputDir':'素材','assets':assets})
        return spec,read_json(crop_assets(spec))

    def test_lossless_crop_coordinates_provenance_and_overwrite(self):
        source=self.directory/'source.png';image=Image.new('RGB',(80,60));pixels=image.load()
        for x in range(80):
            for y in range(60):pixels[x,y]=(x*3,y*4,(x+y)%255)
        image.save(source)
        asset={'name':'圖示','crop':{'x':10,'y':8,'w':35,'h':30},'role':'complex-icon','containsText':False}
        spec,report=self.crops(source,[asset]);element=report['elements'][0]
        self.assertEqual((element['x'],element['y'],element['w'],element['h']),(10,8,35,30))
        with Image.open(element['path']) as result:
            self.assertEqual(result.tobytes(),image.convert('RGBA').crop((10,8,45,38)).tobytes())
        self.assertEqual(element['sourceCrop']['sourceSha256'],sha256(source))
        self.assertEqual(element['sourceCrop']['assetSha256'],sha256(element['path']))
        before=Path(element['path']).stat().st_mtime_ns;crop_assets(spec)
        self.assertEqual(before,Path(element['path']).stat().st_mtime_ns)
        changed=read_json(spec);changed['assets'][0]['crop']['x']=12;write_json(spec,changed)
        with self.assertRaisesRegex(ValueError,'不同內容'):crop_assets(spec)
        crop_assets(spec,True)
        changed['assets'][0]['crop']['w']=100;write_json(spec,changed)
        with self.assertRaisesRegex(ValueError,'超出'):crop_assets(spec,True)

    def test_edge_key_preserves_enclosed_background_and_highlights(self):
        image=Image.new('RGBA',(31,31),(0,0,0,255))
        ImageDraw.Draw(image).rectangle((5,5,25,25),outline='white',width=3)
        keyed=remove_edge_background(image,{'color':'000000','tolerance':0,'feather':0})
        self.assertEqual(keyed.getpixel((0,0))[3],0)
        self.assertEqual(keyed.getpixel((15,15)),(0,0,0,255))
        self.assertEqual(keyed.getpixel((5,5)),(255,255,255,255))
        with self.assertRaises(ValueError):remove_edge_background(image,{'color':'000000','tolerance':250,'feather':10})

    def test_exif_orientation_and_explicit_text_erasure(self):
        source=self.directory/'rotated.jpg';image=Image.new('RGB',(40,20),'navy');ImageDraw.Draw(image).rectangle((0,0,10,10),fill='white')
        exif=image.getexif();exif[274]=6;image.save(source,exif=exif)
        asset={'name':'圖示','crop':{'x':0,'y':0,'w':20,'h':40},'role':'complex-icon','containsText':False}
        spec,report=self.crops(source,[asset]);self.assertEqual(report['referenceSizePx'],[20,40])
        with Image.open(source) as original,Image.open(report['elements'][0]['path']) as result:
            self.assertEqual(result.tobytes(),ImageOps.exif_transpose(original).convert('RGBA').tobytes())
        data=read_json(spec);data['assets'][0]['eraseRegions']=[{'x':0,'y':0,'w':5,'h':8,'fill':'001827','reason':'已知標籤區域另建原生文字'}];write_json(spec,data)
        result=read_json(crop_assets(spec,True))
        with Image.open(result['elements'][0]['path']) as erased:self.assertEqual(erased.getpixel((2,2)),(0,24,39,255))

    def test_original_crop_is_checked_and_embedded_as_independent_image(self):
        manifest=self.batch(count=1);page=read_json(manifest)['pages'][0];file=self.work/page['scene'];scene=read_json(file)
        _,cropped=self.crops(Path(page['source']),[{'name':'獨立圖示','crop':{'x':700,'y':200,'w':120,'h':120},'role':'complex-icon','containsText':False}])
        scene['elements'][3]=cropped['elements'][0];write_json(file,scene);fixture.node('build_batch.cjs',manifest)
        audit=audit_deck(self.work/'merged.pptx');self.assertEqual(audit['slides'][0]['imageHashes'],[sha256(cropped['elements'][0]['path'])])
        self.assertTrue(any(text['text']=='Training 1' for text in audit['slides'][0]['texts']))
        Image.new('RGBA',(120,120),'red').save(cropped['elements'][0]['path'])
        self.assertIn('裁切來源或素材已變更',fixture.node('build_batch.cjs',manifest,ok=False).stderr)

    def test_prepared_scene_measures_once_for_both_outputs(self):
        manifest=self.batch();fixture.node('build_batch.cjs',manifest)
        built=read_json(self.work/'build-report.json');stats=built['performance']
        self.assertEqual(stats['preparedScenes'],3);self.assertEqual(stats['fontCatalogLoads'],1)
        self.assertGreater(stats['textMeasurements'],0);self.assertGreater(stats['textCacheHits'],0)
        self.assertTrue(all(p['representation']['mode']=='faithful-hybrid' for p in built['pages']))
        self.assertTrue(fixture.validate_batch(manifest,False)['passed'])
        # 字距與框寬仍逐物件檢查，不可被文字寬度快取掩蓋。
        file=self.work/read_json(manifest)['pages'][1]['scene'];scene=read_json(file)
        scene['elements'][1]['w']=30;write_json(file,scene)
        fixture.node('build_batch.cjs',manifest,ok=False)

    def test_independent_original_artwork_can_be_shared_between_pages(self):
        manifest=self.batch();source=self.directory/'common-art.png';Image.new('RGBA',(60,60),'purple').save(source)
        _,cropped=self.crops(source,[{'name':'獨立圖示','crop':{'x':0,'y':0,'w':60,'h':60},'role':'complex-icon','containsText':False}])
        for page in read_json(manifest)['pages']:
            file=self.work/page['scene'];scene=read_json(file);scene['elements'][3]=cropped['elements'][0];write_json(file,scene)
        fixture.node('build_batch.cjs',manifest);audit=audit_deck(self.work/'merged.pptx')
        self.assertEqual([s['imageHashes'] for s in audit['slides']],[[sha256(cropped['elements'][0]['path'])]]*3)
        self.assertTrue(fixture.validate_batch(manifest,False)['passed'])

    def test_reencoded_full_page_crop_cannot_bypass_layer_rebuilding(self):
        manifest=self.batch(count=1);page=read_json(manifest)['pages'][0];file=self.work/page['scene'];scene=read_json(file)
        _,cropped=self.crops(Path(page['source']),[{'name':'獨立圖示','crop':{'x':0,'y':0,'w':page['widthPx'],'h':page['heightPx']},'role':'complex-illustration','containsText':False}])
        scene['elements'][3]=cropped['elements'][0];write_json(file,scene)
        self.assertIn('完整來源頁',fixture.node('build_batch.cjs',manifest,ok=False).stderr)

    def test_simplification_requires_existing_user_request(self):
        manifest=self.batch(count=1);page=read_json(manifest)['pages'][0];file=self.work/page['scene'];scene=read_json(file)
        scene['reconstruction']={'mode':'native-simplified'};write_json(file,scene)
        fixture.node('build_batch.cjs',manifest,ok=False)
        scene['reconstruction']['authorization']='使用者要求以原生幾何簡化圖示';write_json(file,scene)
        fixture.node('build_batch.cjs',manifest)
        self.assertEqual(read_json(self.work/'build-report.json')['pages'][0]['representation']['mode'],'native-simplified')

    def test_prepared_scene_isolated_from_input_and_pptx_mutations(self):
        manifest=self.batch(count=1);file=self.work/read_json(manifest)['pages'][0]['scene']
        code="""
const b=require(process.argv[1]),path=require('node:path');
const s=b.loadJson(process.argv[2]),original=JSON.stringify(s),ctx=b.createBuildContext();
const p=b.prepareScene(s,path.dirname(process.argv[2]),true,ctx),size=b.nativeSize(s.canvas);
const snapshot=JSON.stringify(p.scene),metrics=JSON.stringify(ctx.stats);
const first=b.addPreparedScene(b.createDeck(size),p,size),second=b.addPreparedScene(b.createDeck(size),p,size);
if(original!==JSON.stringify(s)||snapshot!==JSON.stringify(p.scene)||metrics!==JSON.stringify(ctx.stats)||JSON.stringify(first)!==JSON.stringify(second))process.exit(1);
"""
        run=subprocess.run([fixture.NODE,'-e',code,str(ROOT/'scripts/scene_builder.cjs'),str(file)],capture_output=True,text=True,encoding='utf-8')
        self.assertEqual(run.returncode,0,run.stderr)

    def test_incremental_render_cache_and_theme_invalidation(self):
        module=importlib.import_module('render_deck');manifest=self.batch();fixture.node('build_batch.cjs',manifest);calls=[]
        def fake_office(request):
            calls.append(request['slides']);audit=audit_deck(request['input'])
            for number in request['slides']:
                color='#'+audit['slides'][number-1]['fingerprint'][:6]
                Image.new('RGB',(request['width'],request['height']),color).save(Path(request['output'])/f'slide_{number:04d}.png')
        with patch.object(module,'os',types.SimpleNamespace(name='nt',environ=os.environ)),patch.object(module,'run_office',side_effect=fake_office):
            first=module.render_deck(self.work/'merged.pptx',self.work/'previews','powerpoint',600)
            self.assertEqual(first['exportedSlides'],[1,2,3])
            cached=module.render_deck(self.work/'merged.pptx',self.work/'previews','powerpoint',600)
            self.assertEqual(cached['reusedSlides'],[1,2,3]);self.assertEqual(len(calls),1)
            file=self.work/read_json(manifest)['pages'][1]['scene'];scene=read_json(file);scene['background']='083344';write_json(file,scene)
            fixture.node('build_batch.cjs',manifest)
            changed=module.render_deck(self.work/'merged.pptx',self.work/'previews','powerpoint',600)
            self.assertEqual(changed['exportedSlides'],[2]);self.assertEqual(changed['reusedSlides'],[1,3])
            preview=Path(changed['images'][0]['path']);preview.write_bytes(preview.read_bytes()+b'tampered')
            repaired=module.render_deck(self.work/'merged.pptx',self.work/'previews','powerpoint',600)
            self.assertEqual(repaired['exportedSlides'],[1])
            deck=self.work/'merged.pptx';mutated=self.work/'theme-changed.pptx'
            with zipfile.ZipFile(deck) as before,zipfile.ZipFile(mutated,'w') as after:
                for item in before.infolist():
                    data=before.read(item.filename)
                    if item.filename=='ppt/theme/theme1.xml':data=data.replace(b'</a:theme>',b'<!-- changed theme --></a:theme>')
                    after.writestr(item,data)
            result=module.render_deck(mutated,self.work/'previews','powerpoint',600)
            self.assertEqual(result['exportedSlides'],[1,2,3])
            forced=module.render_deck(mutated,self.work/'previews','powerpoint',600,True)
            self.assertEqual(forced['exportedSlides'],[1,2,3])
            resized=module.render_deck(mutated,self.work/'previews','powerpoint',700)
            self.assertEqual(resized['exportedSlides'],[1,2,3])

    def test_explicit_review_group_only_records_selected_pages(self):
        module=importlib.import_module('record_review');render_module=importlib.import_module('render_deck')
        manifest=self.batch();fixture.node('build_batch.cjs',manifest)
        def fake_office(request):
            for number in request['slides']:Image.new('RGB',(600,338),'navy').save(Path(request['output'])/f'slide_{number:04d}.png')
        with patch.object(render_module,'os',types.SimpleNamespace(name='nt',environ=os.environ)),patch.object(render_module,'run_office',side_effect=fake_office):
            render_module.render_deck(self.work/'merged.pptx',self.work/'previews','powerpoint',600)
        ids=[p['id'] for p in read_json(manifest)['pages']]
        with patch.object(module,'validate_batch',wraps=module.validate_batch) as validated:
            paths=record_reviews(manifest,ids[:2],'合成測試驗證明列頁面，不作使用者視覺驗收。')
            self.assertEqual(validated.call_count,1)
        self.assertEqual(len(paths),2);self.assertFalse((self.work/'reviews'/f'{ids[2]}.json').exists())
        with self.assertRaises(ValueError):record_reviews(manifest,[ids[2],'missing'],'測試不存在頁面')
        self.assertFalse((self.work/'reviews'/f'{ids[2]}.json').exists())

    def five_family_batch(self):
        names=['text','flow','table','illustration','cover'];sources=[]
        for name in names:
            source=self.inputs/f'{len(sources)+1}_{name}.png';image=Image.new('RGB',(1200,675),'#001827');draw=ImageDraw.Draw(image)
            if name in ('illustration','cover'):
                for y in range(160,600):draw.line((60,y,1140,y),fill=(y%80,40+(y%100),100+y%150))
                draw.ellipse((350,200,800,590),fill='#33BBDD',outline='white',width=6)
                draw.ellipse((450,270,530,350),fill='white');draw.arc((400,290,730,520),0,180,fill='#001827',width=8)
            draw.text((60,40),name,fill='white');image.save(source);sources.append(source)
        manifest=fixture.prepare(sources,self.work);expected={}
        for page,name in zip(read_json(manifest)['pages'],names):
            elements=[{'type':'text','name':'Title','x':60,'y':40,'w':1080,'h':100,'text':name,'fontSizePt':30,'color':'FFFFFF'}]
            inventory=[{'id':'title','text':name,'elements':['Title']}]
            if name=='flow':
                elements += [{'type':'rect','name':'Start','x':100,'y':220,'w':300,'h':160,'fill':'0077CC'},
                             {'type':'rightArrow','name':'Connection','x':440,'y':260,'w':250,'h':80,'fill':'33BBDD'},
                             {'type':'rect','name':'End','x':750,'y':220,'w':300,'h':160,'fill':'44AA66'}]
            elif name=='table':
                rows=[['Item','Value']]+[[f'Row {n}',str(n*10)] for n in range(1,7)]
                elements.append({'type':'table','name':'Data','x':60,'y':170,'w':1080,'h':420,'rows':rows,'fontSizePt':16,'fontFace':self.font})
                inventory.append({'id':'data','text':'\n'.join('\t'.join(r) for r in rows),'elements':['Data']})
            elif name in ('illustration','cover'):
                spec=self.directory/f'{name}.json';write_json(spec,{'source':page['source'],'outputDir':f'assets-{name}','assets':[{'name':'Original artwork','crop':{'x':60,'y':160,'w':1080,'h':440},'role':'complex-illustration','containsText':False}]})
                element=read_json(crop_assets(spec))['elements'][0];elements.append(element);expected[page['id']]=sha256(element['path'])
            scene={'canvas':{'widthPx':1200,'heightPx':675},'source':{'path':page['source'],'sha256':page['sourceSha256']},'background':'001827',
                   'theme':{'bodyFontFace':self.font},'content':{'texts':inventory},'elements':elements}
            write_json(self.work/page['scene'],scene)
        return manifest,expected

    def test_five_families_preserve_artwork_and_native_content(self):
        manifest,expected=self.five_family_batch();fixture.node('build_batch.cjs',manifest)
        self.assertTrue(fixture.validate_batch(manifest,False)['passed']);audit=audit_deck(self.work/'merged.pptx');built=read_json(self.work/'build-report.json')
        self.assertEqual([s['texts'][0]['text'] for s in audit['slides']],['text','flow','table','illustration','cover'])
        self.assertEqual(audit['slides'][2]['tableCount'],1)
        for p,s in zip(built['pages'],audit['slides']):
            self.assertEqual(s['imageHashes'],[expected[p['id']]] if p['id'] in expected else [])
        self.assertEqual(built['performance']['preparedScenes'],5)

    @unittest.skipUnless(os.name=='nt' and Path(os.environ.get('ProgramFiles','C:/Program Files'),'Microsoft Office/root/Office16/POWERPNT.EXE').exists(),'需要 Windows PowerPoint')
    def test_real_powerpoint_five_families_and_incremental_render(self):
        from render_deck import render_deck
        manifest,_=self.five_family_batch();fixture.node('build_batch.cjs',manifest)
        first=render_deck(self.work/'merged.pptx',self.work/'previews','powerpoint',1000)
        self.assertEqual(first['exportedSlides'],[1,2,3,4,5])
        second=render_deck(self.work/'merged.pptx',self.work/'previews','powerpoint',1000)
        self.assertEqual(second['reusedSlides'],[1,2,3,4,5])
        file=self.work/read_json(manifest)['pages'][0]['scene'];scene=read_json(file);scene['background']='003344';write_json(file,scene)
        fixture.node('build_batch.cjs',manifest)
        changed=render_deck(self.work/'merged.pptx',self.work/'previews','powerpoint',1000)
        self.assertEqual(changed['exportedSlides'],[1]);self.assertEqual(changed['reusedSlides'],[2,3,4,5])
        if os.environ.get('TRAINING_TEST_ARTIFACTS'):
            import shutil
            shutil.copytree(self.directory,Path(os.environ['TRAINING_TEST_ARTIFACTS'])/'five-families',dirs_exist_ok=True)


if __name__=='__main__':unittest.main()
