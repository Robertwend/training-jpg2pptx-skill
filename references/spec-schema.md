# 場景規格

每張圖片一份 JSON，所有 `x/y/w/h` 均為校正方向後的來源像素。元素陣列順序就是圖層順序。單頁與批次共用建置器，只有批次要求完整來源指紋與文字清單。

```json
{
  "canvas": {"widthPx": 1600, "heightPx": 900},
  "source": {"path": "../來源.png", "sha256": "來源 SHA-256"},
  "background": "001827",
  "metadata": {"title": "單頁名稱", "lang": "zh-TW"},
  "theme": {"bodyFontFace": "Microsoft JhengHei", "headFontFace": "Microsoft JhengHei"},
  "content": {
    "texts": [{"id": "title", "text": "可編輯標題", "elements": ["標題"]}]
  },
  "elements": [{
    "type": "text", "name": "標題", "x": 100, "y": 80, "w": 1300, "h": 120,
    "text": "可編輯標題", "fontSizePt": 40, "color": "FFFFFF", "bold": true
  }]
}
```

`source.path`、圖片素材等相對路徑均以場景檔所在目錄解析。批次的來源路徑和雜湊必須對應 `batch.json`，不能把上一頁的場景複製後忘了修改。單頁純範例可省略 `source`，但實際轉換仍應記錄來源。

`canvas.slideWidthIn/slideHeightIn` 為選用英吋尺寸，若指定必須與原圖比例一致。合併時的留邊由批次共同畫布處理，不改變來源像素座標。

## 原生文字與富文字

文字的 `fontSizePt`、`margin`、`lineSpacingPt`、`charSpacing` 使用點數，不是像素。`fontFace` 可逐個物件覆寫。字型須存在於本機量測環境，選替代字型時記錄實際選擇。

```json
{
  "type": "text", "name": "百分比", "x": 100, "y": 250, "w": 400, "h": 110,
  "text": "28%", "fontFace": "Arial", "fontSizePt": 42,
  "align": "center", "valign": "mid", "margin": 0, "bold": true,
  "allowAutoDownsize": false
}
```

多色文字使用 `runs` 取代 `text`；每段可指定 `color`、`bold`、`italic`、`fontFace`、`fontSizePt`。`breakLine: true` 在該段後換行，亦可直接在文字內寫 `\n`。量測會採用各段實際字型及字級。

```json
"runs": [
  {"text": "原生", "color": "FFFFFF", "bold": true},
  {"text": "文字", "color": "00DFFF", "fontSizePt": 42}
]
```

預設 `safetyFactor: 0.98`、`lineHeight: 1.15`，可在 `textSafety` 或個別元素調整。`margin` 可為一個點數或 `[上,右,下,左]`。超框預設失敗，`allowAutoDownsize: true` 須逐物件明確開啟，並在視覺驗收接受。最低字級 `minFontSizePt` 預設 6。`wrap: true` 不接受；來源換行必須明確。

## 圖形、線條與圖片

原生圖形的 `type` 使用已安裝 PptxGenJS 的 `ShapeType` 名稱，例如 `rect`、`roundRect`、`ellipse`、`chevron`、`triangle`、`parallelogram`。形狀支援 `fill`、`line`、`shadow`、`rotate`、`flipH/flipV`。線段用 `type: "line"`，水平／垂直線的 `w` 或 `h` 可為 0。

色碼為六位十六進位、不帶 `#`；填色透明度為 `fill.transparency`，陰影透明度為 `shadow.opacity`。陰影 `offset` 不得為負。每個物件獨立建立樣式，避免函式原地修改共用設定。

```json
{
  "type": "image", "name": "獨立圖示", "path": "../assets/icon.png",
  "x": 100, "y": 420, "w": 180, "h": 180,
  "role": "complex-icon", "containsText": false,
  "altText": "從原圖裁切並去背的圖示"
}
```

圖片 `role` 支援 `photo`、`texture`、`complex-icon`、`complex-illustration`、`logo`。可辨識文字先移除後原生重建；只有使用者已接受的具體例外可在 `content.rasterExceptions` 記錄：

```json
"rasterExceptions": [{
  "element": "品牌標誌", "reason": "標誌內的商標字樣保留原始造型",
  "authorization": "使用者明確要求品牌標誌以圖片保留"
}]
```

物件超出畫布預設失敗。刻意出血的背景裝飾可設定 `allowOverflow: true` 與具體 `overflowReason`；文字不得用這個設定掩蓋溢位。物件旋轉與圖片裁切、透明邊緣仍要實際渲染檢視。

## 原生表格

```json
{
  "type": "table", "name": "資料表", "x": 100, "y": 400, "w": 1200, "h": 240,
  "rows": [["項目", "數值"], ["完成", "28%"]],
  "columnWidthsPx": [800, 400], "rowHeightsPx": [120, 120],
  "fontSizePt": 20, "fontFace": "Microsoft JhengHei",
  "fill": "FFFFFF", "color": "001827", "border": {"pt": 1, "color": "00AACC"}
}
```

儲存格可為字串或 `{"text":"內容","options":{"bold":true}}`。列欄數須一致，原生表格不自動分頁；文字清單將欄位用 `\t`、列用 `\n` 串起，對應該表格 `name`。儲存格換行、列高與長文字必須逐格檢查。

儲存格 `options.valign` 請使用 `"top"`、`"middle"` 或 `"bottom"`；表格 XML 的垂直置中值為 `middle`，不要直接沿用一般文字方塊常見的 `mid`。

## 內容清單

`content.texts` 的每項有唯一 `id`、原圖完整 `text` 及對應 `elements` 名稱。多個文字物件預設用 `\n` 串接，可用 `join` 指定拼接方式。驗收會直接對照 PPTX 內的原生文字，不能將圖片物件列為可編輯文字。

純照片／無可辨識文字可使用 `content: {"texts": [], "noRecognizableText": true}`，這是檢視後的判斷，不能為了通過檢查而跳過原圖文字。

## 批次清單

`prepare_batch.py` 產生的 `batch.json` 範例：

```json
{
  "version": 2,
  "canvas": {"widthIn": 13.333333333, "heightIn": 7.5, "fit": "contain"},
  "output": "merged.pptx",
  "pages": [{
    "id": "page_0001", "source": "/absolute/source.png", "reference": "/absolute/source.png",
    "sourceSha256": "來源 SHA-256", "widthPx": 1600, "heightPx": 900,
    "scene": "scenes/page_0001.json", "single": "pages/page_0001.pptx"
  }]
}
```

使用者頁序變更時調整 `pages` 陣列；頁面 id 是穩定識別，不要求 id 數字與目前頁碼相同。建置報告是工具產物，不要手改成通過；視覺驗收紀錄只能在實際檢視對應頁面後建立。
