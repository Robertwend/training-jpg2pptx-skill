"""補回 PowerPoint InsertFromFile 遺漏的明確背景；僅移植背景與其完整資源關聯。"""
import copy
import os
import posixpath
import tempfile
from lxml import etree as ET
import zipfile
from pathlib import Path
from workflow import NS,relationships,rels_name

CT='http://schemas.openxmlformats.org/package/2006/content-types'
for prefix,uri in NS.items():
    if prefix not in ('rel',):ET.register_namespace(prefix,uri)
def slide_parts(archive):
    root=ET.fromstring(archive.read('ppt/presentation.xml'));rels=relationships(archive,'ppt/presentation.xml')
    return [rels[item.get(f"{{{NS['r']}}}id")]['part'] for item in root.findall('p:sldIdLst/p:sldId',NS)]
def restore_backgrounds(sources,merged):
    merged=Path(merged)
    with zipfile.ZipFile(merged) as archive:parts={name:archive.read(name) for name in archive.namelist()}
    content_types=ET.fromstring(parts['[Content_Types].xml']);counter=0;target_index=0
    with zipfile.ZipFile(merged) as archive:target_slides=slide_parts(archive)
    for source_path in sources:
        with zipfile.ZipFile(source_path) as source:
            source_types=ET.fromstring(source.read('[Content_Types].xml'))
            overrides={item.get('PartName').lstrip('/'):item.get('ContentType') for item in source_types if item.tag.endswith('Override')}
            defaults={item.get('Extension').lower():item.get('ContentType') for item in source_types if item.tag.endswith('Default')}
            cache={}
            def clone_part(original):
                nonlocal counter
                if original in cache:return cache[original]
                counter+=1;folder=posixpath.dirname(original);name=posixpath.basename(original)
                destination=posixpath.join(folder,f'training-bg-{counter}-{name}')
                while destination in parts:
                    counter+=1;destination=posixpath.join(folder,f'training-bg-{counter}-{name}')
                cache[original]=destination;parts[destination]=source.read(original)
                mime=overrides.get(original) or defaults.get(original.rsplit('.',1)[-1].lower())
                if not mime:raise ValueError(f'背景資源缺少內容類型：{original}')
                ET.SubElement(content_types,f'{{{CT}}}Override',{'PartName':'/'+destination,'ContentType':mime})
                if rels_name(original) in source.namelist():
                    rel_root=ET.fromstring(source.read(rels_name(original)))
                    mapping=relationships(source,original)
                    for rel in rel_root:
                        item=mapping[rel.get('Id')]
                        if item['external']:raise ValueError('背景資源含未嵌入的外連內容。')
                        rel.set('Target',posixpath.relpath(clone_part(item['part']),posixpath.dirname(destination)))
                    parts[rels_name(destination)]=ET.tostring(rel_root,encoding='utf-8',xml_declaration=True)
                return destination
            for original_slide in slide_parts(source):
                target=target_slides[target_index];target_index+=1
                original_root=ET.fromstring(source.read(original_slide));original_bg=original_root.find('p:cSld/p:bg',NS)
                # 繼承母片背景的來源由 COM 複製的 Design／CustomLayout 處理。
                if original_bg is None:continue
                root=ET.fromstring(parts[target]);common=root.find('p:cSld',NS);existing=common.find('p:bg',NS)
                if existing is not None:common.remove(existing)
                bg=copy.deepcopy(original_bg);source_rels=relationships(source,original_slide)
                rel_file=rels_name(target)
                rel_root=ET.fromstring(parts[rel_file]) if rel_file in parts else ET.Element(f"{{{NS['rel']}}}Relationships")
                used={rel.get('Id') for rel in rel_root};assigned={}
                for element in bg.iter():
                    for key,value in list(element.attrib.items()):
                        if not key.startswith('{'+NS['r']+'}'):continue
                        if value not in assigned:
                            item=source_rels[value]
                            if item['external']:raise ValueError('背景圖片必須嵌入。')
                            resource=clone_part(item['part']);number=1
                            while f'trainingBg{number}' in used:number+=1
                            new_id=f'trainingBg{number}';used.add(new_id);assigned[value]=new_id
                            ET.SubElement(rel_root,f"{{{NS['rel']}}}Relationship",{'Id':new_id,'Type':item['type'],'Target':posixpath.relpath(resource,posixpath.dirname(target))})
                        element.set(key,assigned[value])
                common.insert(0,bg);parts[target]=ET.tostring(root,encoding='utf-8',xml_declaration=True)
                parts[rel_file]=ET.tostring(rel_root,encoding='utf-8',xml_declaration=True)
    if target_index!=len(target_slides):raise ValueError('背景頁面對應數量錯誤。')
    parts['[Content_Types].xml']=ET.tostring(content_types,encoding='utf-8',xml_declaration=True)
    descriptor,temp=tempfile.mkstemp(suffix='.pptx',dir=merged.parent);os.close(descriptor)
    try:
        with zipfile.ZipFile(temp,'w',zipfile.ZIP_DEFLATED) as archive:
            for name,data in parts.items():archive.writestr(name,data)
        os.replace(temp,merged)
    finally:
        if os.path.exists(temp):os.unlink(temp)
