"""以合成原圖驗證可觀察行為；不將測試紀錄用於使用者簡報驗收。"""
import copy
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
from PIL import Image,ImageDraw,ImageChops,ImageStat

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from workflow import audit_deck,read_json,write_json,sha256,NS
from prepare_batch import prepare
from validate_batch import validate_batch
from render_deck import render_deck
from record_review import record_review
from merge_pptx import merge_decks

NODE=os.environ.get('TRAINING_NODE') or shutil.which('node') or str(Path.home()/'.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')
def node(script,*args,ok=True):
    run=subprocess.run([NODE,str(ROOT/'scripts'/script),*map(str,args)],capture_output=True,text=True,encoding='utf-8',errors='replace')
    if ok and run.returncode:raise AssertionError(run.stderr+run.stdout)
    if not ok and run.returncode==0:raise AssertionError('應拒絕此輸入，但指令成功。')
    return run
def background_fixture(source,output,picture):
    with zipfile.ZipFile(source) as before,zipfile.ZipFile(output,'w') as after:
        for item in before.infolist():
            data=before.read(item.filename)
            if item.filename=='ppt/slides/slide1.xml':
                root=ET.fromstring(data);common=root.find('p:cSld',NS);old=common.find('p:bg',NS)
                if old is not None:common.remove(old)
                bg=ET.Element(f"{{{NS['p']}}}bg");pr=ET.SubElement(bg,f"{{{NS['p']}}}bgPr")
                if picture:
                    image=root.find('.//a:blip',NS);fill=ET.SubElement(pr,f"{{{NS['a']}}}blipFill")
                    ET.SubElement(fill,f"{{{NS['a']}}}blip",dict(image.attrib));stretch=ET.SubElement(fill,f"{{{NS['a']}}}stretch");ET.SubElement(stretch,f"{{{NS['a']}}}fillRect")
                else:
                    fill=ET.SubElement(pr,f"{{{NS['a']}}}gradFill");stops=ET.SubElement(fill,f"{{{NS['a']}}}gsLst")
                    for pos,color in [('0','CC3300'),('100000','0033CC')]:
                        stop=ET.SubElement(stops,f"{{{NS['a']}}}gs",{'pos':pos});ET.SubElement(stop,f"{{{NS['a']}}}srgbClr",{'val':color})
                    ET.SubElement(fill,f"{{{NS['a']}}}lin",{'ang':'5400000','scaled':'1'})
                common.insert(0,bg);data=ET.tostring(root,encoding='utf-8',xml_declaration=True)
            after.writestr(item,data)

class WorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        probe=subprocess.run([NODE,'-e',"const{runtimeModule}=require('./runtime.cjs');console.log(JSON.stringify(runtimeModule('@napi-rs/canvas').GlobalFonts.families.map(x=>x.family)))"],cwd=ROOT/'scripts',capture_output=True,text=True,encoding='utf-8')
        if probe.returncode:raise RuntimeError(probe.stderr)
        fonts=json.loads(probe.stdout);cls.font=next((name for name in ['Arial','DejaVu Sans','Liberation Sans'] if name in fonts),fonts[0])
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory(prefix='training-test-');self.directory=Path(self.temporary.name)
        self.inputs=self.directory/'原始圖片';self.inputs.mkdir();self.work=self.directory/'工作目錄'
    def tearDown(self):self.temporary.cleanup()
    def batch(self,mixed=False,count=3):
        for i,name in enumerate(['slide_10.png','slide_2.png','slide_1.png'][:count],1):
            size=(675,1200) if mixed and i==1 else (1200,675)
            image=Image.new('RGB',size,'#001827');draw=ImageDraw.Draw(image)
            draw.rounded_rectangle((30,20,size[0]-30,size[1]-20),radius=20,outline='#00D6ED',width=3)
            draw.text((50,40),f'Source {i}',fill='white');draw.text((50,140),'28%',fill='#00D6ED')
            image.save(self.inputs/name)
        manifest=prepare([self.inputs],self.work)
        data=read_json(manifest)
        for number,page in enumerate(data['pages'],1):
            asset=self.work/'assets'/f"{page['id']}.png";Image.new('RGB',(80,80),(number*60,80,180)).save(asset)
            width,height=page['widthPx'],page['heightPx'];title=f'Training {number}'
            elements=[
              {'type':'roundRect','name':'面板','x':30,'y':20,'w':width-60,'h':height-40,'fill':'001827','line':{'color':'00D6ED','width':2}},
              {'type':'text','name':'標題','x':50,'y':35,'w':width-100,'h':100,'text':title,'fontSizePt':24,'bold':True,'color':'FFFFFF'},
              {'type':'text','name':'百分比','x':50,'y':145,'w':250,'h':115,'fontSizePt':30,'runs':[{'text':'28','bold':True,'color':'00D6ED'},{'text':'%','fontSizePt':36,'color':'A7EE6A'}]},
              {'type':'image','name':'獨立圖示','path':str(asset),'x':width-150,'y':145,'w':100,'h':100,'role':'complex-icon','containsText':False},
              {'type':'table','name':'原生資料表','x':50,'y':300,'w':width-100,'h':180,'rows':[['Item','Value'],[title,'28%']],
               'columnWidthsPx':[(width-100)*.65,(width-100)*.35],'rowHeightsPx':[90,90],'fontSizePt':14,'fontFace':self.font,'fill':'FFFFFF'}]
            scene={'canvas':{'widthPx':width,'heightPx':height},'source':{'path':page['source'],'sha256':page['sourceSha256']},'background':'001827',
                   'theme':{'bodyFontFace':self.font,'headFontFace':self.font},'content':{'texts':[{'id':'title','text':title,'elements':['標題']},
                   {'id':'metric','text':'28%','elements':['百分比']},{'id':'table','text':f'Item\tValue\n{title}\t28%','elements':['原生資料表']}]},'elements':elements,'notes':f'備註 {number}'}
            write_json(self.work/page['scene'],scene)
        return manifest
    def test_natural_order_and_explicit_order(self):
        manifest=self.batch();names=[Path(p['source']).name for p in read_json(manifest)['pages']]
        self.assertEqual(names,['slide_1.png','slide_2.png','slide_10.png'])
        other=prepare([self.inputs/'slide_10.png',self.inputs/'slide_1.png',self.inputs/'slide_10.png'],self.directory/'explicit')
        self.assertEqual([Path(p['source']).name for p in read_json(other)['pages']],['slide_10.png','slide_1.png'])
    def test_batch_keeps_native_content_and_distinct_images(self):
        manifest=self.batch();node('build_batch.cjs',manifest);result=validate_batch(manifest,False)
        self.assertEqual(result['slideCount'],3)
        audit=audit_deck(self.work/'merged.pptx')
        self.assertEqual([s['tableCount'] for s in audit['slides']],[1,1,1])
        self.assertEqual([s['imageCount'] for s in audit['slides']],[1,1,1])
        self.assertEqual(len({s['imageHashes'][0] for s in audit['slides']}),3)
        self.assertEqual([s['texts'][0]['text'] for s in audit['slides']],['Training 1','Training 2','Training 3'])
    def test_resume_reuses_only_unchanged_files(self):
        manifest=self.batch();ids=[p['id'] for p in read_json(manifest)['pages']]
        node('build_batch.cjs',manifest);before=sha256(self.work/'merged.pptx')
        self.assertIn('沿用',node('build_batch.cjs',manifest).stdout);self.assertEqual(before,sha256(self.work/'merged.pptx'))
        prepare([self.inputs],self.work);self.assertEqual(ids,[p['id'] for p in read_json(manifest)['pages']])
        asset=self.work/'assets'/f'{ids[0]}.png';Image.new('RGB',(80,80),'red').save(asset)
        with self.assertRaises(ValueError):validate_batch(manifest,False)
        node('build_batch.cjs',manifest);self.assertNotEqual(before,sha256(self.work/'merged.pptx'))
    def test_changed_source_requires_reconstruction(self):
        manifest=self.batch();node('build_batch.cjs',manifest)
        file=self.inputs/'slide_2.png';Image.new('RGB',(1200,675),'red').save(file)
        node('build_batch.cjs',manifest,ok=False)
        prepare([self.inputs],self.work);node('build_batch.cjs',manifest,ok=False)
    def test_resume_from_page_checkpoints(self):
        manifest=self.batch();node('build_batch.cjs',manifest);built=read_json(self.work/'build-report.json')
        before=[(Path(p['singleDeck']['path']).stat().st_mtime_ns,p['singleDeck']['sha256']) for p in built['pages']]
        (self.work/'build-report.json').unlink();(self.work/'merged.pptx').unlink()
        node('build_batch.cjs',manifest)
        after=[(Path(p['singleDeck']['path']).stat().st_mtime_ns,sha256(p['singleDeck']['path'])) for p in built['pages']]
        self.assertEqual(before,after);validate_batch(manifest,False)
    def test_existing_merge_rejects_mixed_sizes(self):
        manifest=self.batch(mixed=True);node('build_batch.cjs',manifest);built=read_json(self.work/'build-report.json')
        with self.assertRaisesRegex(ValueError,'尺寸不同'):merge_decks([p['singleDeck']['path'] for p in built['pages']],self.directory/'mixed.pptx')
    def test_missing_scene_and_wrong_inventory_rejected(self):
        manifest=self.batch();page=read_json(manifest)['pages'][1];file=self.work/page['scene'];scene=read_json(file)
        file.unlink();node('build_batch.cjs',manifest,ok=False)
        scene['content']['texts'][0]['text']='wrong';write_json(file,scene);node('build_batch.cjs',manifest,ok=False)
    def test_large_raster_with_recognizable_text_rejected(self):
        manifest=self.batch(count=1);page=read_json(manifest)['pages'][0];file=self.work/page['scene'];scene=read_json(file)
        scene['elements'][3]['path']=page['source'];write_json(file,scene);node('build_batch.cjs',manifest,ok=False)
        scene['elements'][3]['path']=str(self.work/'assets'/f"{page['id']}.png");scene['elements'][3]['containsText']=True
        write_json(file,scene);node('build_batch.cjs',manifest,ok=False)
    def test_mixed_ratios_contain_without_stretch(self):
        manifest=self.batch(mixed=True);node('build_batch.cjs',manifest);result=validate_batch(manifest,False)
        self.assertEqual(len(result['letterboxedPages']),1)
        built=read_json(self.work/'build-report.json');page=built['pages'][-1];view=page['viewport']
        self.assertAlmostEqual(view['widthIn']/view['heightIn'],675/1200,places=6)
        single=audit_deck(page['singleDeck']['path']);self.assertAlmostEqual(single['sizeEmu'][0]/single['sizeEmu'][1],675/1200,places=5)
    def test_fixed_font_and_rich_text_overflow(self):
        scene={'canvas':{'widthPx':1200,'heightPx':675},'theme':{'bodyFontFace':self.font},'elements':[{'type':'text','name':'百分比','x':10,'y':10,'w':100,'h':80,'fontSizePt':90,
              'runs':[{'text':'28','fontSizePt':90},{'text':'%','fontSizePt':100}]}]}
        file=self.directory/'scene.json';output=self.directory/'single.pptx';write_json(file,scene);node('build_from_spec.cjs',file,output,ok=False)
        scene['elements'][0]['allowAutoDownsize']=True;write_json(file,scene);node('build_from_spec.cjs',file,output)
        self.assertTrue(read_json(output.with_suffix('.text-safety.json'))['textSafety'][0]['autoDownsized']);audit_deck(output)
    def test_spacing_between_rich_text_runs_is_measured(self):
        scene={'canvas':{'widthPx':1200,'heightPx':675},'theme':{'bodyFontFace':self.font},'elements':[{'type':'text','name':'多色字距','x':10,'y':10,'w':300,'h':100,
               'fontSizePt':20,'charSpacing':80,'runs':[{'text':c,'color':'00AABB'} for c in 'TRAIN']}]}
        file=self.directory/'spacing.json';write_json(file,scene);node('build_from_spec.cjs',file,self.directory/'spacing.pptx',ok=False)
    def test_explicitly_authorized_logo_exception_is_disclosed(self):
        manifest=self.batch(count=1);page=read_json(manifest)['pages'][0];file=self.work/page['scene'];scene=read_json(file)
        scene['elements']=[{'type':'image','name':'品牌標誌','path':page['source'],'x':0,'y':0,'w':page['widthPx'],'h':page['heightPx'],'role':'logo','containsText':True}]
        scene['content']={'texts':[],'rasterExceptions':[{'element':'品牌標誌','reason':'合成案例測試商標內文字保留','authorization':'合成案例明確授權保留整張標誌'}]}
        write_json(file,scene);node('build_batch.cjs',manifest);result=validate_batch(manifest,False);self.assertEqual(len(result['rasterExceptions']),1)
    def test_missing_review_and_tampered_single_rejected(self):
        manifest=self.batch();node('build_batch.cjs',manifest)
        with self.assertRaises((ValueError,FileNotFoundError)):validate_batch(manifest)
        page=read_json(self.work/'build-report.json')['pages'][0];single=Path(page['singleDeck']['path']);single.write_bytes(single.read_bytes()+b'edited')
        with self.assertRaises(ValueError):validate_batch(manifest,False)
        node('build_batch.cjs',manifest,ok=False)
    def test_autofit_check_is_namespace_aware(self):
        manifest=self.batch(count=1);node('build_batch.cjs',manifest);source=self.work/'merged.pptx';broken=self.directory/'broken.pptx'
        with zipfile.ZipFile(source) as before,zipfile.ZipFile(broken,'w') as after:
            for item in before.infolist():
                data=before.read(item.filename)
                if item.filename=='ppt/slides/slide1.xml':
                    data=data.replace(b'<a:noAutofit/>',b'<q:normAutofit xmlns:q="http://schemas.openxmlformats.org/drawingml/2006/main"/>',1)
                    if b'q:normAutofit' not in data:data=data.replace(b'</a:bodyPr>',b'<q:normAutofit xmlns:q="http://schemas.openxmlformats.org/drawingml/2006/main"/></a:bodyPr>',1)
                after.writestr(item,data)
        with self.assertRaises(ValueError):audit_deck(broken)
    def test_traditional_text_and_explicit_line_breaks(self):
        scene={'canvas':{'widthPx':1200,'heightPx':675},'theme':{'bodyFontFace':self.font},'elements':[{'type':'text','name':'繁體中文','x':40,'y':40,'w':1100,'h':250,'fontSizePt':28,'text':'培訓委員會\n單張與批次圖片整併'}]}
        file=self.directory/'traditional.json';output=self.directory/'traditional.pptx';write_json(file,scene);node('build_from_spec.cjs',file,output)
        self.assertEqual(audit_deck(output)['slides'][0]['texts'][0]['text'],scene['elements'][0]['text'])
    def test_missing_input_and_output_overwrite_rejected(self):
        with self.assertRaises(ValueError):prepare([self.inputs/'missing.png'],self.work)
        manifest=self.batch();node('build_batch.cjs',manifest)
        with self.assertRaises(ValueError):merge_decks([self.work/'merged.pptx'],self.work/'merged.pptx',True)
    @unittest.skipUnless(os.name=='nt' and Path(os.environ.get('ProgramFiles','C:/Program Files'),'Microsoft Office/root/Office16/POWERPNT.EXE').exists(),'需要 Windows PowerPoint，其他環境明確略過原生整合測試')
    def test_powerpoint_merge_render_and_final_reviews(self):
        manifest=self.batch();node('build_batch.cjs',manifest);built=read_json(self.work/'build-report.json')
        render_deck(self.work/'merged.pptx',self.work/'previews','powerpoint',1200)
        for page in built['pages']:record_review(manifest,page['id'],'合成測試案例的驗收紀錄，非使用者簡報。')
        self.assertTrue(validate_batch(manifest)['passed'])
        output=self.directory/'native-merged.pptx';merge=merge_decks([p['singleDeck']['path'] for p in built['pages']],output)
        self.assertEqual(merge['slideCount'],3);render_deck(output,self.directory/'native-previews','powerpoint',1200)
        original=audit_deck(self.work/'merged.pptx');merged=audit_deck(output)
        self.assertEqual([s['imageHashes'] for s in original['slides']],[s['imageHashes'] for s in merged['slides']])
        for number in range(1,4):
            first=Image.open(self.work/'previews'/f'slide_{number:04d}.png').convert('RGB')
            second=Image.open(self.directory/'native-previews'/f'slide_{number:04d}.png').convert('RGB')
            self.assertLess(max(ImageStat.Stat(ImageChops.difference(first,second)).rms),1.5,'原生合併後外觀改變')
        chart=self.directory/'chart.pptx'
        script=self.directory/'chart.cjs'
        script.write_text("const{runtimeModule}=require("+json.dumps(str(ROOT/'scripts/runtime.cjs'))+");const G=runtimeModule('pptxgenjs');const p=new G();p.layout='LAYOUT_WIDE';const s=p.addSlide();s.addChart(p.ChartType.bar,[{name:'Example',labels:['A','B'],values:[10,20]}],{x:1,y:1,w:10,h:5,showTitle:true,title:'Native chart',catAxisLabelFontFace:'Arial',valAxisLabelFontFace:'Arial'});s.addNotes('Chart notes');p.writeFile({fileName:"+json.dumps(str(chart))+"});",encoding='utf-8')
        run=subprocess.run([NODE,str(script)],capture_output=True,text=True,encoding='utf-8');self.assertEqual(run.returncode,0,run.stderr)
        # 使尺寸與來源一致（LAYOUT_WIDE 為 13.333333 × 7.5）。
        source_size=audit_deck(built['pages'][0]['singleDeck']['path'])['sizeEmu'];chart_size=audit_deck(chart)['sizeEmu']
        self.assertEqual(source_size,chart_size)
        chart_merged=self.directory/'chart-merged.pptx';merge_decks([built['pages'][0]['singleDeck']['path'],chart],chart_merged)
        audit=audit_deck(chart_merged);self.assertEqual([s['chartCount'] for s in audit['slides']],[0,1]);self.assertTrue(audit['slides'][1]['chartData'][0]['workbooks'])
        render_deck(chart_merged,self.directory/'chart-previews','powerpoint',1200)
        picture=self.directory/'picture-background.pptx';gradient=self.directory/'gradient-background.pptx'
        background_fixture(built['pages'][1]['singleDeck']['path'],picture,True);background_fixture(built['pages'][2]['singleDeck']['path'],gradient,False)
        backgrounds=self.directory/'backgrounds-merged.pptx';merge_decks([built['pages'][0]['singleDeck']['path'],picture,gradient],backgrounds)
        render_deck(backgrounds,self.directory/'background-previews','powerpoint',1200)
        for number,source in [(2,picture),(3,gradient)]:
            source_dir=self.directory/f'background-source-{number}';render_deck(source,source_dir,'powerpoint',1200)
            first=Image.open(source_dir/'slide_0001.png').convert('RGB');second=Image.open(self.directory/'background-previews'/f'slide_{number:04d}.png').convert('RGB')
            self.assertLess(max(ImageStat.Stat(ImageChops.difference(first,second)).rms),1.5,'圖片／漸層背景在整併後改變')
        preview=Path(read_json(self.work/'previews/render.json')['images'][0]['path']);preview.write_bytes(preview.read_bytes()+b'changed')
        with self.assertRaises(ValueError):validate_batch(manifest)
        artifacts=os.environ.get('TRAINING_TEST_ARTIFACTS')
        if artifacts:
            target=Path(artifacts);target.mkdir(parents=True,exist_ok=True)
            shutil.copytree(self.directory,target/'integration',dirs_exist_ok=True)

if __name__=='__main__':unittest.main()
