#!/usr/bin/env node
const fs=require('node:fs'),path=require('node:path');
const {loadJson,nativeSize,createDeck,addScene,writeDeck}=require('./scene_builder.cjs');
async function main(){
  const args=process.argv.slice(2),force=args.includes('--force'),pos=args.filter(x=>x!=='--force');
  if(!pos[0])throw new Error('用法：node build_from_spec.cjs scene.json [output.pptx] [--force]');
  const specPath=path.resolve(pos[0]),scene=loadJson(specPath),base=path.dirname(specPath);
  const output=path.resolve(pos[1] || path.resolve(base,scene.output || 'editable-output.pptx'));
  if(!output.toLowerCase().endsWith('.pptx'))throw new Error('輸出檔必須是 .pptx。');
  if(fs.existsSync(output) && !force)throw new Error('輸出已存在；請改用新檔名，或確認後加 --force。');
  const canvas=nativeSize(scene.canvas),pptx=createDeck(canvas,scene.metadata,scene.theme);
  const result=addScene(pptx,scene,base,canvas,'page_0001',!!scene.source);
  await writeDeck(pptx,output);
  fs.writeFileSync(output.replace(/\.pptx$/i,'.text-safety.json'),JSON.stringify(result,null,2)+'\n');
  console.log(output);
}
if(require.main===module)main().catch(e=>{console.error(e.message);process.exitCode=1;});
