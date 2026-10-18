# 批次、續作與整併

## 1. 建立固定來源清單

```text
python scripts/prepare_batch.py "來源資料夾" --work "工作目錄"
```

亦可明列數張圖片，依傳入順序處理。資料夾依自然排序；預設不遞迴，只有明確需要時加 `--recursive`。來源內容相同而檔名不同仍保留，避免誤刪使用者刻意重複的頁面。相同路徑重複傳入只盤點一次。

`batch.json` 的 `pages` 陣列是唯一頁序依據，檔名缺號不補頁。每頁有穩定 id、來源路徑、SHA-256、尺寸、場景位置及單頁輸出路徑。重新盤點沿用相同來源的 id 與場景位置，不覆蓋已完成的場景。來源變更後，舊場景的來源指紋會不符，必須重新核對才能建置。

工作目錄應放在來源資料夾外；來源內的素材／預覽容易被誤當新頁，除非使用明列檔案。EXIF 方向不同時，盤點會另存校正方向的 `reference` 圖，分析座標以它為準，原始來源指紋仍保留。

## 2. 逐一完成場景

按 `pages` 順序檢視每張原圖，將完整文字清單與物件規格存到各自 `scene` 路徑。這一步是助理的視覺重建工作，不能以空白 JSON、OCR 摘要、同一份模板或一張大裁切取代。

場景需有 `source.path`、`source.sha256`、與原圖一致的 `canvas`、`content.texts` 及 `elements`。相對素材路徑以場景 JSON 所在目錄為準，不能以整批工作目錄猜測。範例見 [場景規格](spec-schema.md)。

可先用 `build_from_spec.cjs` 渲染當頁草稿，確認文字、拆圖和結構後再處理下一頁。保持來源風格，共用色票與圖示函式可以提升一致性，但每頁仍須完整保留自己的內容與配置。工作中斷時先讀清單、場景和紀錄，從未完成或失效的頁面續作。

## 3. 建立單頁與完整簡報

```text
node scripts/build_batch.cjs "工作目錄/batch.json"
python scripts/validate_batch.py "工作目錄/batch.json" --structural-only
```

從所有場景直接建立新的 PptxGenJS 簡報，逐頁加入原生物件；同時產生原圖比例的單頁檔。這能避免先轉成圖片，或拼貼 OOXML 導致媒體、字型、備註及關聯失效。

合併檔使用 `canvas.widthIn`、`heightIn` 的共同畫布，預設第一頁比例；每頁均等比 contain。混合比例留邊頁會列入驗證報告，不會拉伸或裁切。若使用者要求各頁都維持不同原生畫布尺寸，只能分檔交付，因為同一 PPTX 只有一組投影片尺寸。

來源、場景、素材、頁序、建置器版本及輸出檔指紋完全未變時，可沿用建置成果；`--force` 可重新建置。素材修改會自動使舊成果失效。若現有輸出屬於其他任務或被人修改，工具會停止，避免無意覆寫。

## 4. 驗收合併後的每一頁

```text
python scripts/render_deck.py "工作目錄/merged.pptx" --out "工作目錄/previews"
```

逐一用圖像工具對照原圖與 `slide_0001.png` 等預覽，不只看縮圖總覽。重點檢查所有文字、表格、圖示、點陣文字是否清除、顏色、間距、遮擋、留邊、頁序及內容完整性。修正場景後重建並重新渲染。

每頁實際檢視通過後才記錄：

```text
python scripts/record_review.py "工作目錄/batch.json" --page page_0001 --notes "已比對原圖，文字、標籤、圖層與版面均完成核對"
```

沒有「整批自動通過」指令。發現問題使用 `--status needs-fix`；修正後再對新版預覽記錄通過。如果個別物件曾明確允許縮小字級，核對後用 `--accept-downsize "物件名稱"` 接受該項，不要預先全數接受。

紀錄綁定來源、場景、該頁輸出內容與預覽指紋。舊簡報的預覽無法驗收新簡報；來源、場景、文字或預覽被改動後不會沿用失效的通過紀錄。未改頁若重新渲染後完全一致，可保留相符紀錄。

## 5. 最終交付檢查

```text
python scripts/validate_batch.py "工作目錄/batch.json"
```

檢查頁數與頁序、來源及場景指紋、每頁單頁檔、合併前後原生文字／表格／圖片／備註，以及目前版本的逐頁驗收。任何頁面未完成即失敗，不將部分成果標示為整批完成。

依使用者要求將已驗收的合併檔複製到最終位置；以 SHA-256 確認交付檔與驗收檔一致。中間素材、報告及單頁檔留在工作目錄，除非使用者也要求這些檔案。

## 既有 PPTX 原生整併

```text
python scripts/merge_pptx.py "01.pptx" "02.pptx" --output "合併.pptx"
python scripts/render_deck.py "合併.pptx" --out "合併預覽"
```

明列檔案依傳入順序；傳資料夾則自然排序，排除本次輸出。Windows PowerPoint 的 `Slides.InsertFromFile` 匯入原生物件，複製來源 Design／CustomLayout，再補回 PowerPoint 會遺漏的明確背景。背景修復只移植背景節點與完整遞迴資源關聯，重新命名資源及關聯並更新內容類型，不拼貼整頁 XML。檢查前後頁數、文字、表格、圖表及嵌入活頁簿、圖片、超連結與備註，保留來源檔。不同比例／尺寸的既有簡報會先停止；若有場景，改從場景用 contain 重建。

相關 Office 介面：[Designs.Clone](https://learn.microsoft.com/en-us/office/vba/api/powerpoint.designs.clone)、[Slides.InsertFromFile](https://learn.microsoft.com/en-us/office/vba/api/powerpoint.slides.insertfromfile)、[Slide.Background](https://learn.microsoft.com/en-us/office/vba/api/powerpoint.slide.background)。

工具以獨立工作副本開啟來源，不會關閉原本開啟的其他簡報；來源有外連媒體或外連活頁簿時，須先嵌入才能作為可攜成品處理。沒有 PowerPoint 時，場景直接合併仍可用；既有任意 PPTX 不會以簡易 XML 拼接或點陣化替代。原生匯入後仍須逐頁看渲染結果，原生物件數和 XML 關聯正常不代表字型與外觀一定正確。
