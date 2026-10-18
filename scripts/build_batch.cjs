#!/usr/bin/env node
const fs=require('node:fs'),path=require('node:path'),crypto=require('node:crypto');
const {sha256,loadJson,nativeSize,createDeck,addScene,writeDeck}=require('./scene_builder.cjs');
const digest=value=>crypto.createHash('sha256').update(JSON.stringify(value)).digest('hex');
const writeJson=(file,value)=>{const temp=`${file}.${crypto.randomUUID()}.tmp`;fs.writeFileSync(temp,JSON.stringify(value,null,2)+'\n');fs.renameSync(temp,file);};
async function main(){
  const args=process.argv.slice(2),manifestPath=path.resolve(args[0] || 'batch.json'),manifest=loadJson(manifestPath),base=path.dirname(manifestPath);
  if(manifest.version!==2 || !Array.isArray(manifest.pages) || !manifest.pages.length)throw new Error('需要非空的 version: 2 批次清單。');
  const seen=new Set();
  const pages=manifest.pages.map(p=>{
    if(!/^[A-Za-z0-9][A-Za-z0-9_-]{0,80}$/.test(p.id || '') || seen.has(p.id))throw new Error('批次 page.id 必須唯一且不得含路徑。');seen.add(p.id);
    const source=path.resolve(base,p.source),scenePath=path.resolve(base,p.scene);
    if(!fs.existsSync(source) || sha256(source)!==p.sourceSha256)throw new Error(`${p.id} 來源已變更或遺失，請重新盤點並核對此頁。`);
    if(!fs.existsSync(scenePath))throw new Error(`${p.id} 尚未重建：${scenePath}`);
    const scene=loadJson(scenePath);
    if(scene.source?.sha256!==p.sourceSha256 || path.resolve(path.dirname(scenePath),scene.source?.path || '')!==source)throw new Error(`${p.id} 場景與來源不一致。`);
    if(scene.canvas?.widthPx!==p.widthPx || scene.canvas?.heightPx!==p.heightPx)throw new Error(`${p.id} 場景尺寸與原圖不一致。`);
    const assets=scene.elements?.filter(e=>e.type==='image').map(e=>{const file=path.resolve(path.dirname(scenePath),e.path);return {path:file,sha256:sha256(file)};}) || [];
    return {...p,source,scenePath,scene,assets,sceneSha256:sha256(scenePath)};
  });
  const first=nativeSize(pages[0].scene.canvas),canvas={width:manifest.canvas?.widthIn || first.width,height:manifest.canvas?.heightIn || first.height};
  if(![canvas.width,canvas.height].every(n=>typeof n==='number' && Number.isFinite(n) && n>0))throw new Error('無效批次畫布。');
  if(manifest.canvas?.fit && manifest.canvas.fit!=='contain')throw new Error('批次僅支援 contain，不會拉伸或裁切。');
  const output=path.resolve(base,manifest.output || 'merged.pptx');
  if(!output.toLowerCase().endsWith('.pptx'))throw new Error('輸出檔必須是 .pptx。');
  const reportPath=path.join(base,'build-report.json');
  const statePath=path.join(base,'page-state.json'),state=fs.existsSync(statePath)?loadJson(statePath):{version:2,pages:{}};
  const planSha256=digest({builder:sha256(__filename),sceneBuilder:sha256(path.join(__dirname,'scene_builder.cjs')),canvas,output,title:manifest.title,pages:pages.map(p=>[p.id,p.sourceSha256,p.sceneSha256,p.assets,p.single])});
  const previous=fs.existsSync(reportPath)?loadJson(reportPath):null;
  if(!args.includes('--force') && previous?.planSha256===planSha256 && [previous.deck,...previous.pages.map(p=>p.singleDeck)].every(x=>x && fs.existsSync(x.path) && sha256(x.path)===x.sha256)){
    console.log(`沿用未變更成果：${output}`);return;
  }
  if(fs.existsSync(output) && ![previous?.deck,state.deck].some(x=>x?.path===output && x.sha256===sha256(output)) && !args.includes('--force'))throw new Error('輸出位置已有非本批次或被修改過的檔案，請改用新路徑，或確認後加 --force。');
  const merged=createDeck(canvas,{title:manifest.title || '圖片批次重建簡報',lang:'zh-TW'},pages[0].scene.theme);
  const report={version:2,manifest:manifestPath,planSha256,canvas,pages:[]};
  for(const p of pages){
    const result=addScene(merged,p.scene,path.dirname(p.scenePath),canvas,p.id,true);
    const singleSize=nativeSize(p.scene.canvas);
    const singlePath=path.resolve(base,p.single || `pages/${p.id}.pptx`);
    if(singlePath===output || pages.some(x=>x.scenePath===singlePath || x.source===singlePath) || report.pages.some(x=>x.singleDeck.path===singlePath))throw new Error('單頁輸出路徑重複或與來源／合併檔重疊。');
    const previousSingle=previous?.pages.find(x=>x.id===p.id)?.singleDeck;
    const checkpoint=state.pages[p.id],singlePlan=digest({scene:p.sceneSha256,source:p.sourceSha256,assets:p.assets,singleSize,builder:sha256(path.join(__dirname,'scene_builder.cjs'))});
    if(fs.existsSync(singlePath) && ![previousSingle,checkpoint?.singleDeck].some(x=>x?.path===singlePath && x.sha256===sha256(singlePath)) && !args.includes('--force'))throw new Error(`${p.id} 單頁檔已被修改，請先保留修改或確認後加 --force。`);
    if(args.includes('--force') || checkpoint?.planSha256!==singlePlan || checkpoint?.singleDeck?.path!==singlePath || !fs.existsSync(singlePath) || sha256(singlePath)!==checkpoint.singleDeck.sha256){
      const single=createDeck(singleSize,p.scene.metadata,p.scene.theme);addScene(single,p.scene,path.dirname(p.scenePath),singleSize,p.id,true);await writeDeck(single,singlePath);
    }
    const singleDeck={path:singlePath,sha256:sha256(singlePath)};
    state.pages[p.id]={planSha256:singlePlan,singleDeck};writeJson(statePath,state);
    report.pages.push({id:p.id,source:p.source,sourceSha256:p.sourceSha256,scene:p.scenePath,sceneSha256:p.sceneSha256,assets:p.assets,rasterExceptions:p.scene.content?.rasterExceptions || [],...result,singleDeck});
  }
  await writeDeck(merged,output);report.deck={path:output,sha256:sha256(output),slideCount:pages.length};
  state.deck=report.deck;writeJson(statePath,state);writeJson(reportPath,report);
  console.log(`已建立 ${pages.length} 份單頁檔與合併檔：${output}`);
  console.log('尚未完成視覺驗收：請渲染、逐頁檢視、記錄 review，再執行 validate_batch.py。');
}
if(require.main===module)main().catch(e=>{console.error(e.message);process.exitCode=1;});
