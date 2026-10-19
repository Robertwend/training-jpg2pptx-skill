# training-jpg2pptx-skill

將單張或批次圖片逐頁重建為可編輯 PowerPoint，並保留原生文字、圖形、線條、表格與獨立圖片物件。支援自然排序、來源指紋、續作、逐頁驗收，以及合併成完整 PPTX。

預設採用 CarbonJ 的保真混合方式：複雜圖示、插畫、照片與光影從原圖裁切保留，文字、表格及常規幾何以原生物件重建。只有使用者指定時才啟用原生簡化；不把「加快」解讀成可改畫或刪除原圖特徵。

這套技能需要助理逐頁理解原圖並建立場景；工具負責可靠建置與檢查，不宣稱一個命令就能自動辨識所有圖片。OCR 可完全離線，也不需要雲端 token。

## 安裝與使用

將本倉庫複製到技能目錄，例如：

```powershell
git clone https://github.com/Robertwend/training-jpg2pptx-skill.git "$env:USERPROFILE\.codex\skills\training-jpg2pptx-skill"
```

在新對話中使用：

```text
$training-jpg2pptx-skill
將這個資料夾的圖片逐一轉成可編輯 PPTX，按檔名順序合併成完整簡報。
保留原圖內容、字級、顏色及圖層，完成逐頁渲染核對後，存回指定目錄。
```

也可附一張圖片要求單頁轉換，或提供已有的 PPTX 要求原生合併。

## 環境

Codex 桌面版可使用 `load_workspace_dependencies` 提供的 Node.js 與 Python。腳本會讀取本機套件或 `NODE_PATH`、`CODEX_PRIMARY_RUNTIME_NODE_MODULES`、`RUNTIME_NODE_MODULES`，不綁定特定使用者路徑。

一般環境：

```text
npm install
python -m pip install -r requirements.txt
```

依賴 Node.js 18+、Python 3.11+、PptxGenJS、`@napi-rs/canvas`、Pillow 與 python-pptx。PowerPoint 原生合併／主要渲染需 Windows 與已安裝的 Microsoft PowerPoint；替代渲染可用 LibreOffice 加 PyMuPDF（`python -m pip install PyMuPDF`）。Tesseract 是選用的本機 OCR。

## 單頁、批次與整併

| 動作 | 工具 | 產物 |
|---|---|---|
| 來源盤點 | `prepare_batch.py` | 自然排序的 `batch.json`、尺寸與 SHA-256 |
| 原圖素材裁切 | `crop_assets.py` | 無損 PNG、裁切座標、來源指紋與可直接使用的 image 元素 |
| 單頁重建 | `build_from_spec.cjs` | 原生可編輯 PPTX 與文字量測報告 |
| 批次建置／合併 | `build_batch.cjs` | 每頁 PPTX、合併 PPTX、來源對照報告 |
| 既有 PPTX 合併 | `merge_pptx.py` | PowerPoint 原生匯入，驗證頁數／文字／物件／備註 |
| 渲染 | `render_deck.py` | 固定頁序的 PNG 與綁定檔案指紋的紀錄 |
| 逐頁驗收 | `record_review.py` | 檢視原圖與預覽後記錄當頁驗收 |
| 最終批次檢查 | `validate_batch.py` | 內容、順序、可編輯性與驗收紀錄檢查 |

完整操作見 [SKILL.md](SKILL.md)、[批次流程](references/batch-workflow.md) 與 [場景規格](references/spec-schema.md)。

單頁／合併共用每頁的場景檢查與文字量測；字型清單及量測畫布只建立一次。PowerPoint 集中渲染變更頁，未變頁依母片、版式、佈景與素材指紋復用。明列已看過的多頁可共用一次驗收掃描。工具另記錄建置與渲染階段耗時，不將它當作完整轉換耗時。見 [保真重建與執行效率](references/efficient-rebuild.md)、[素材流程](references/asset-workflow.md) 與 [同圖比較方式](references/benchmark.md)。

## 品質與限制

所有可辨識文字都要納入原生文字清單，包含圖示旁的標籤。照片、紋理與複雜插畫可拆成可替換圖片，但不能用整頁圖或大型含文字裁切冒充完整可編輯。特定點陣文字例外必須有使用者授權並記錄。

圖片物件可移動、縮放、裁切與替換，內部像素不會自動向量化；原生文字與圖形才能直接修改內容、筆畫或樣式。驗收同時對照原圖外觀與內容，不以物件數作為品質證明。`crop_assets.py` 的去背只處理明確指定的近色邊界背景，仍須檢視高光和透明邊緣。

預設固定字級，文字超框即報錯；不使用 Office 延遲自動適配。各頁從自己的場景建置，合併時不套成相同內容模板。混合比例使用等比留邊；既有 PPTX 尺寸不同時不默默縮放。

自動檢查能證明頁數、指紋、文字與物件符合清單，無法單獨證明圖片辨識正確或視覺一致，因此仍要求實際逐頁渲染與檢視。沒有 PowerPoint 時不宣稱已驗證 PowerPoint 的實際顯示。

## 驗證技能工具

```text
python -m unittest discover -s tests -v
```

測試使用自建素材，不需要使用者文件。涵蓋排序、續作、來源變更、文字溢位、富文字、原生表格、圖片對應、無損裁切、邊界去背、量測共用、預覽快取及母片變更失效，並有文字／流程／表格／插畫／封面五類場景。Windows 有 PowerPoint 時執行實際合併與渲染；其他環境會明確略過。

## 授權與來源

本專案改寫自 CarbonJ-AIEra 的 [carbonj-jpg2pptx-skill](https://github.com/CarbonJ-AIEra/carbonj-jpg2pptx-skill)，保留原 MIT 授權及著作權聲明。新增繁體中文、批次生命週期、品質檢查與整併工具，見 [LICENSE](LICENSE)。
