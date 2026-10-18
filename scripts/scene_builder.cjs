const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { runtimeModule } = require('./runtime.cjs');
const PptxGenJS = runtimeModule('pptxgenjs');
const { createCanvas, GlobalFonts } = runtimeModule('@napi-rs/canvas');
const clone = value => value == null ? value : JSON.parse(JSON.stringify(value));
const sha256 = file => crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
const loadJson = file => JSON.parse(fs.readFileSync(file, 'utf8').replace(/^\uFEFF/, ''));
function positive(value, label, zero = false) {
  if (typeof value !== 'number' || !Number.isFinite(value) || (zero ? value < 0 : value <= 0)) throw new Error(`${label} 必須是${zero ? '非負' : '正'}有限數值。`);
  return value;
}
function cleanHex(value) {
  const hex = String(value).replace(/^#/, '').toUpperCase();
  if (!/^[0-9A-F]{6}$/.test(hex)) throw new Error(`無效色碼：${value}`);
  return hex;
}
function fill(value) {
  if (value == null) return undefined;
  const out = typeof value === 'string' ? { color: value } : clone(value);
  if (out.color) out.color = cleanHex(out.color);
  return out;
}
function line(value) { return value ? fill(value) : { color: 'FFFFFF', transparency: 100, width: 0 }; }
function shadow(value) {
  if (!value) return undefined;
  const out = { type: 'outer', ...clone(value) };
  if (out.color) out.color = cleanHex(out.color);
  if ((out.offset ?? 0) < 0) throw new Error('陰影 offset 不得小於 0。');
  return out;
}
function nativeSize(canvas) {
  positive(canvas?.widthPx, 'canvas.widthPx'); positive(canvas?.heightPx, 'canvas.heightPx');
  const width = canvas.slideWidthIn ?? (canvas.widthPx >= canvas.heightPx ? 13.333333333 : 7.5 * canvas.widthPx / canvas.heightPx);
  const height = canvas.slideHeightIn ?? width * canvas.heightPx / canvas.widthPx;
  positive(width, '投影片寬'); positive(height, '投影片高');
  if (Math.abs(width / height - canvas.widthPx / canvas.heightPx) > 0.001) throw new Error('場景畫布與原圖比例不同；批次請用 contain 留邊，勿拉伸場景。');
  return { width, height };
}
const runsFor = element => element.runs || [{ text: String(element.text ?? '') }];
function plainText(element) {
  if (element.type === 'table') return element.rows.map(row => row.map(cell => String(typeof cell === 'object' ? cell.text ?? '' : cell)).join('\t')).join('\n');
  return runsFor(element).map(run => String(run.text ?? '') + (run.breakLine || run.options?.breakLine ? '\n' : '')).join('').replace(/\n$/, '');
}
const normalizedText = text => String(text).replace(/\r\n?/g, '\n').trim();
function validateScene(scene, base, strict = false) {
  nativeSize(scene.canvas);
  if(scene.source){const source=path.resolve(base,scene.source.path || '');if(!fs.existsSync(source) || sha256(source)!==scene.source.sha256)throw new Error('場景來源指紋已變更。');}
  if (!Array.isArray(scene.elements) || !scene.elements.length) throw new Error('場景沒有 elements；圖片清單不等於已完成轉換。');
  const names = new Set();
  for (const [index, e] of scene.elements.entries()) {
    e.name ||= `${e.type}-${index + 1}`;
    if (names.has(e.name)) throw new Error(`重複物件名稱：${e.name}`);
    names.add(e.name);
    for (const key of ['x','y','w','h']) if (typeof e[key] !== 'number' || !Number.isFinite(e[key])) throw new Error(`${e.name}.${key} 必須是有限數值。`);
    positive(e.w, `${e.name}.w`, e.type === 'line'); positive(e.h, `${e.name}.h`, e.type === 'line');
    const outside = e.x < 0 || e.y < 0 || e.x + e.w > scene.canvas.widthPx + .01 || e.y + e.h > scene.canvas.heightPx + .01;
    if (outside && !(e.allowOverflow && e.overflowReason)) throw new Error(`${e.name} 超出來源畫布；刻意出血須記錄 allowOverflow 與 overflowReason。`);
    if (e.type === 'image') {
      const image = path.resolve(base, e.path || '');
      if (!fs.existsSync(image) || !fs.statSync(image).isFile()) throw new Error(`找不到素材：${image}`);
      if (strict && (!['photo','texture','complex-icon','complex-illustration','logo'].includes(e.role) || typeof e.containsText !== 'boolean')) throw new Error(`${e.name} 必須記錄 role 與 containsText。`);
      const authorized=scene.content?.rasterExceptions?.some(x => x.element === e.name && x.reason && x.authorization);
      if (strict && e.containsText && !authorized) throw new Error(`${e.name} 仍含可辨識文字；請移除點陣文字並重建，或記錄使用者已授權的具體例外。`);
      if (strict && scene.source && sha256(image) === scene.source.sha256 && !scene.content?.noRecognizableText && !authorized) throw new Error(`${e.name} 使用整張來源圖；請先拆解圖層。`);
    }
  }
  if (!strict) return;
  const inventory = scene.content?.texts, covered = new Set(), ids = new Set();
  if (!Array.isArray(inventory) || (!inventory.length && !scene.content?.noRecognizableText && !scene.content?.rasterExceptions?.length)) throw new Error('批次場景須提供 content.texts；純照片須明示 noRecognizableText。');
  if(scene.content?.noRecognizableText && (inventory.length || scene.elements.some(e=>['text','table'].includes(e.type) && plainText(e).trim())))throw new Error('noRecognizableText 與實際文字清單矛盾。');
  for(const exception of scene.content?.rasterExceptions || [])if(!exception.reason || !exception.authorization || !scene.elements.some(e=>e.name===exception.element && e.type==='image' && e.containsText))throw new Error('點陣文字例外必須對應含文字圖片、原因及既有授權。');
  for (const item of inventory) {
    if (!item.id || ids.has(item.id) || !Array.isArray(item.elements) || !item.elements.length) throw new Error('文字清單須有唯一 id 與 elements。');
    ids.add(item.id);
    const elements = item.elements.map(name => scene.elements.find(e => e.name === name));
    if (elements.some(e => !e || !['text','table'].includes(e.type))) throw new Error(`${item.id} 沒有對應原生文字／表格。`);
    if (normalizedText(elements.map(plainText).join(item.join ?? '\n')) !== normalizedText(item.text)) throw new Error(`${item.id} 的清單文字與重建物件不一致。`);
    for (const e of elements) covered.add(e.name);
  }
  for (const e of scene.elements) if (['text','table'].includes(e.type) && plainText(e).trim() && !covered.has(e.name)) throw new Error(`${e.name} 未列入文字清單。`);
}
function textPreflight(e, scene, face, requestedPt) {
  const available = new Set(GlobalFonts.families.map(x => x.family.toLowerCase()));
  const pxPerPt = scene.canvas.widthPx / nativeSize(scene.canvas).width / 72;
  const ctx = createCanvas(16,16).getContext('2d');
  const margin = e.margin == null ? [0,0,0,0] : Array.isArray(e.margin) ? e.margin : Array(4).fill(e.margin);
  if (margin.length !== 4 || margin.some(x => typeof x !== 'number' || x < 0)) throw new Error(`${e.name} margin 須為點數或 [上,右,下,左]。`);
  const boxW = e.w - (margin[1] + margin[3]) * pxPerPt, boxH = e.h - (margin[0] + margin[2]) * pxPerPt;
  if (boxW <= 0 || boxH <= 0) throw new Error(`${e.name} 內距大於文字框。`);
  const widths = [0], heights = [0],counts=[0]; let n = 0;
  for (const run of runsFor(e)) {
    const font = run.fontFace || face, size = positive(run.fontSizePt ?? requestedPt, '富文字字級');
    if (!available.has(font.toLowerCase())) throw new Error(`量測環境沒有字型 ${font}；請選用並記錄實際可用的替代字型。`);
    ctx.font = `${(run.italic ?? e.italic) ? 'italic' : 'normal'} ${(run.bold ?? e.bold) ? '700' : '400'} ${size * pxPerPt}px "${font}"`;
    const parts = String(run.text ?? '').split('\n');
    for (const [i, part] of parts.entries()) {
      widths[n] += ctx.measureText(part).width;counts[n]+=[...part].length;
      heights[n] = Math.max(heights[n], size * pxPerPt * (e.lineHeight ?? scene.textSafety?.lineHeight ?? 1.15));
      if (i < parts.length - 1) { n++; widths.push(0); heights.push(0);counts.push(0); }
    }
    if (run.breakLine || run.options?.breakLine) { n++; widths.push(0); heights.push(0);counts.push(0); }
  }
  if (!widths.at(-1) && widths.length > 1 && !heights.at(-1)) { widths.pop(); heights.pop(); }
  let height = heights.reduce((a,b) => a+b, 0);
  if (e.lineSpacingPt && heights.length > 1) height = heights[0] + (heights.length - 1) * e.lineSpacingPt * pxPerPt;
  const widthRatio = Math.max(...widths.map((width,index)=>width+Math.max(0,counts[index]-1)*(e.charSpacing || 0)*pxPerPt)) / boxW, heightRatio = height / boxH;
  const factor = e.safetyFactor ?? scene.textSafety?.safetyFactor ?? .98;
  if (typeof factor !== 'number' || factor <= 0 || factor > 1) throw new Error('safetyFactor 須介於 0 與 1。');
  let chosenPt = requestedPt;
  if (Math.max(widthRatio,heightRatio) > factor) {
    if (e.allowAutoDownsize !== true) throw new Error(`${e.name} 文字預檢超框（寬 ${widthRatio.toFixed(2)}、高 ${heightRatio.toFixed(2)}）；請修正框、字型或字級，不會自動縮小。`);
    chosenPt = requestedPt * factor / Math.max(widthRatio,heightRatio);
    if (chosenPt < (e.minFontSizePt ?? scene.textSafety?.minFontSizePt ?? 6)) throw new Error(`${e.name} 無法在允許字級內容納文字。`);
  }
  return { name:e.name,requestedPt,chosenPt,lineCount:widths.length,widthRatio,heightRatio,autoDownsized:chosenPt < requestedPt-.01,fontFace:face,measured:true };
}
function createDeck(canvas, metadata = {}, theme = {}) {
  const pptx = new PptxGenJS();
  pptx.defineLayout({name:'TRAINING_CANVAS',width:canvas.width,height:canvas.height}); pptx.layout='TRAINING_CANVAS';
  pptx.author=metadata.author || 'Training JPG2PPTX'; pptx.title=metadata.title || '圖片重建可編輯簡報'; pptx.subject=metadata.subject || '圖片圖層重建';
  pptx.lang=metadata.lang || 'zh-TW'; pptx.theme={headFontFace:theme.headFontFace || 'Arial',bodyFontFace:theme.bodyFontFace || 'Arial',lang:pptx.lang};
  return pptx;
}
function addScene(pptx, scene, base, target, pageId='page_0001', strict=false) {
  validateScene(scene,base,strict);
  const native=nativeSize(scene.canvas), scale=Math.min(target.width/native.width,target.height/native.height);
  const left=(target.width-native.width*scale)/2, top=(target.height-native.height*scale)/2;
  const ux=value=>value/scene.canvas.widthPx*native.width*scale, uy=value=>value/scene.canvas.heightPx*native.height*scale;
  const slide=pptx.addSlide(),textSafety=[]; slide.background={color:cleanHex(scene.background || 'FFFFFF')};
  for(const e of scene.elements){
    const common={x:left+ux(e.x),y:top+uy(e.y),w:ux(e.w),h:uy(e.h),rotate:e.rotate || 0,objectName:e.name};
    if(e.type==='text'){
      const face=e.fontFace || scene.theme?.bodyFontFace || 'Arial', requested=positive(e.fontSizePt ?? 18,'字級');
      const pre=textPreflight(e,scene,face,requested); textSafety.push({pageId,...pre}); const runScale=pre.chosenPt/requested;
      if(e.wrap===true)throw new Error(`${e.name} 請用明確換行取代自動 wrap。`);
      const options={...common,fontFace:face,fontSize:pre.chosenPt*scale,color:cleanHex(e.color || '000000'),bold:!!e.bold,italic:!!e.italic,
        align:e.align || 'left',valign:e.valign || 'top',margin:Array.isArray(e.margin)?e.margin.map(x=>x*scale):(e.margin || 0)*scale,
        fit:'none',wrap:false,breakLine:false,isTextBox:true,charSpacing:(e.charSpacing || 0)*scale,
        lineSpacingMultiple:e.lineSpacingPt?undefined:e.lineHeight ?? scene.textSafety?.lineHeight ?? 1.15,
        lineSpacing:e.lineSpacingPt?e.lineSpacingPt*runScale*scale:undefined,shadow:shadow(e.shadow)};
      const runs=runsFor(e).map(r=>({text:String(r.text ?? ''),options:{...(r.color?{color:cleanHex(r.color)}:{}),...(r.bold!=null?{bold:!!r.bold}:{}),
        ...(r.italic!=null?{italic:!!r.italic}:{}),...(r.fontFace?{fontFace:r.fontFace}:{}),...(r.fontSizePt?{fontSize:r.fontSizePt*runScale*scale}:{}),
        ...((r.breakLine || r.options?.breakLine)?{breakLine:true}:{})}}));
      slide.addText(e.runs?runs:String(e.text ?? ''),options);
    }else if(e.type==='image'){
      slide.addImage({...common,path:path.resolve(base,e.path),transparency:e.transparency || 0,altText:e.altText || e.name});
    }else if(e.type==='line'){
      slide.addShape(pptx.ShapeType.line,{...common,line:line(e.line || {color:e.color || '000000',width:e.widthPt || 1})});
    }else if(e.type==='table'){
      if(!Array.isArray(e.rows) || !e.rows.length || !e.rows[0].length || e.rows.some(r=>r.length!==e.rows[0].length))throw new Error(`${e.name} 表格欄數不一致。`);
      const cols=e.columnWidthsPx || Array(e.rows[0].length).fill(e.w/e.rows[0].length),heights=e.rowHeightsPx || Array(e.rows.length).fill(e.h/e.rows.length);
      if(cols.length!==e.rows[0].length || heights.length!==e.rows.length || Math.abs(cols.reduce((a,b)=>a+b,0)-e.w)>.01 || Math.abs(heights.reduce((a,b)=>a+b,0)-e.h)>.01)throw new Error(`${e.name} 表格列高／欄寬與邊界不一致。`);
      const rows=e.rows.map((row,r)=>row.map((c,col)=>{
        const text=String(typeof c==='object'?c.text ?? '':c),opts=typeof c==='object'?clone(c.options || {}):{};
        const face=opts.fontFace || e.fontFace || scene.theme?.bodyFontFace || 'Arial';
        const pre=textPreflight({name:`${e.name}[${r+1},${col+1}]`,text,w:cols[col],h:heights[r],bold:!!opts.bold,margin:opts.margin || 0},scene,face,opts.fontSize || e.fontSizePt || 14);
        textSafety.push({pageId,...pre});return {text,options:{...opts,fontFace:face,fontSize:pre.chosenPt*scale}};
      }));
      slide.addTable(rows,{...common,autoPage:false,margin:0,fontFace:e.fontFace || scene.theme?.bodyFontFace || 'Arial',fontSize:(e.fontSizePt || 14)*scale,
        color:cleanHex(e.color || '000000'),fill:fill(e.fill || 'FFFFFF'),border:clone(e.border || {pt:.6,color:'8098AA'}),
        colW:cols.map(ux),rowH:heights.map(uy)});
    }else{
      const shape=pptx.ShapeType[e.shape || e.type]; if(!shape)throw new Error(`不支援的原生圖形：${e.type}`);
      slide.addShape(shape,{...common,fill:fill(e.fill || e.color || 'FFFFFF'),line:line(e.line),shadow:shadow(e.shadow),
        ...(e.flipH!=null?{flipH:!!e.flipH}:{}),...(e.flipV!=null?{flipV:!!e.flipV}:{})});
    }
  }
  slide.addNotes([scene.notes || '',`來源頁面：${pageId}`,scene.source?`來源 SHA-256：${scene.source.sha256}`:''].filter(Boolean).join('\n'));
  return {pageId,textSafety,viewport:{xIn:left,yIn:top,widthIn:native.width*scale,heightIn:native.height*scale,scale},letterboxed:Math.abs(left)>.00001 || Math.abs(top)>.00001};
}
async function writeDeck(pptx,output){
  fs.mkdirSync(path.dirname(output),{recursive:true}); const temp=`${output}.${crypto.randomUUID()}.tmp.pptx`;
  try{await pptx.writeFile({fileName:temp,compression:true});fs.renameSync(temp,output);}finally{if(fs.existsSync(temp))fs.unlinkSync(temp);}
}
module.exports={sha256,loadJson,nativeSize,createDeck,addScene,writeDeck,plainText,validateScene};
