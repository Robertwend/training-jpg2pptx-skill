# training-jpg2pptx-skill

將單張或批次圖片逐頁重建為可編輯 PowerPoint，並保留原生文字、圖形、線條、表格與獨立圖片物件。支援自然排序、來源指紋、續作、逐頁驗收，以及合併成完整 PPTX。

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
| 單頁重建 | `build_from_spec.cjs` | 原生可編輯 PPTX 與文字量測報告 |
| 批次建置／合併 | `build_batch.cjs` | 每頁 PPTX、合併 PPTX、來源對照報告 |
| 既有 PPTX 合併 | `merge_pptx.py` | PowerPoint 原生匯入，驗證頁數／文字／物件／備註 |
| 渲染 | `render_deck.py` | 固定頁序的 PNG 與綁定檔案指紋的紀錄 |
| 逐頁驗收 | `record_review.py` | 檢視原圖與預覽後記錄當頁驗收 |
| 最終批次檢查 | `validate_batch.py` | 內容、順序、可編輯性與驗收紀錄檢查 |

完整操作見 [SKILL.md](SKILL.md)、[批次流程](references/batch-workflow.md) 與 [場景規格](references/spec-schema.md)。

預設以資訊結構建立原生文字與圖形，精簡背景細格、弱漸層及微光裝飾；批次共用繪圖函式與建置快取，集中渲染合併檔，再逐頁核對。具體做法見 [精簡重建與渲染效率](references/efficient-rebuild.md)。

## 品質與限制

所有可辨識文字都要納入原生文字清單，包含圖示旁的標籤。照片、紋理與複雜插畫可拆成可替換圖片，但不能用整頁圖或大型含文字裁切冒充完整可編輯。特定點陣文字例外必須有使用者授權並記錄。

預設固定字級，文字超框即報錯；不使用 Office 延遲自動適配。各頁從自己的場景建置，合併時不套成相同內容模板。混合比例使用等比留邊；既有 PPTX 尺寸不同時不默默縮放。

自動檢查能證明頁數、指紋、文字與物件符合清單，無法單獨證明圖片辨識正確或視覺一致，因此仍要求實際逐頁渲染與檢視。沒有 PowerPoint 時不宣稱已驗證 PowerPoint 的實際顯示。

## 驗證技能工具

```text
python -m unittest discover -s tests -v
```

測試使用自建素材，不需要使用者文件。涵蓋排序、續作、來源變更、文字溢位、富文字、原生表格、圖片對應、混合比例、驗收失效與原生合併。Windows 有 PowerPoint 時另外執行實際合併與渲染；其他環境會明確略過這部分。

## 授權與來源

本專案改寫自 CarbonJ-AIEra 的 [carbonj-jpg2pptx-skill](https://github.com/CarbonJ-AIEra/carbonj-jpg2pptx-skill)，保留原 MIT 授權及著作權聲明。新增繁體中文、批次生命週期、品質檢查與整併工具，見 [LICENSE](LICENSE)。
