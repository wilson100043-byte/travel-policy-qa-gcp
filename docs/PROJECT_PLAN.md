# 報帳規定問答系統：實作測驗規格

狀態：**本機版本已完成並驗證；雲端部署尚未驗證**。以既定雲端架構為目標，完成不呼叫雲端的本機版本；這次不部署、不執行 Terraform `apply`。所有規定都是自行編寫的假資料，不代表任何公司的真實制度。

架構圖：[PNG](diagrams/cloud-architecture.png) · [互動 HTML](diagrams/cloud-architecture.html)；另有[架構說明](ARCHITECTURE.md)及[本機畫面](images/local-demo.png)。四份虛構規定文件與本機程式已建立；圖中雲端服務連線是預定設計，不代表已經部署或驗證雲端環境。

## 目標與範圍（已確定）

- 做一個企業內部報帳規定問答示範：使用者用中文提問，系統從文件找到相關小節，再整理答案並標示來源。本機用抽取式回答；選配雲端模式才用 Gemini 生成。
- 支援目前網頁內的追問。重新整理或關閉網頁後，對話消失；不建聊天紀錄資料庫。
- 只回答目前生效的規定。報銷進度查詢、上傳真實企業文件、對外公開使用都不在這次範圍。
- 以**不產生任何帳單**為前提：本機預設離線，使用本機文字向量與抽取式回答，不需要 API key；保留明確啟用的 Gemini 模式與 Terraform 設計，但本次不呼叫 Gemini/GCP，也不建立任何雲端資源。

## 系統怎麼運作（已確定的架構）

1. 假 Markdown 文件已放在專案的 `policy_docs/`；提交時可上傳 GitHub。Terraform 可建立私人 Cloud Storage 儲存空間，並把文件上傳到 `raw/`。本機測試時直接讀專案內的文件，完全不連線雲端。
2. 文件處理程式依 `##` 小節切開，整理空白，記下文件名稱、章節和生效日期。本機離線模式使用本機文字向量；選擇 Gemini 模式時才用 `gemini-embedding-001`。雲端架構規劃由手動啟動的 Cloud Run Job 執行，結果寫入同一儲存空間的 `processed/`。
3. HTML、CSS、JavaScript 前端與 Python FastAPI 後端一起放在私人 Cloud Run service。前端把問題和目前網頁的近期對話送到自己的 `/api/ask`。
4. 本機離線模式將追問與近期對話一起搜尋，只在生效中的小節裡做向量相似搜尋，再整理找到的文字與來源。Gemini 模式才請 `gemini-3.1-flash-lite` 補全追問與生成回答；兩種模式的索引分開，不混用向量。
5. 回答顯示文件名稱與小節；文件無法支持答案時，明說查不到。若未來啟用雲端 Gemini 模式，API key 放在 Secret Manager，前端、GitHub 與 Terraform state 都不存 key；使用者開啟服務網址，經 IAP 以授權的 Google 帳號登入後使用，不需安裝工具。

## 假文件內容（已確認）

這次把示範問題集中在「差旅報帳」，以四份文件展示不同規定、追問和舊版排除。

| 文件 | 生效期間 | 範例規定 |
| --- | --- | --- |
| 差旅報帳基本規範 | 2026-01-01 起 | 出差結束後 30 天內申請；附發票或收據、出差事由；主管核准後由財務審核。 |
| 交通與餐費規定 | 2026-01-01 起 | 火車報實際票價並附車票；計程車附收據與業務原因；餐費每人每日上限 NT$300。 |
| 住宿費規定（現行） | 2026-07-01 起 | 每人每晚住宿上限 NT$2,500，須附住宿發票。 |
| 住宿費規定（舊版） | 2025-01-01 至 2026-06-30 | 每人每晚上限 NT$2,000；保留作為排除過期規定的測試資料。 |

每份文件的標題、生效起迄日寫在檔案開頭；內文用 `##` 分小節。**每份約 1,500–2,500 個中文字、6–10 個有實質內容的小節**，包含適用範圍、申請步驟、憑證要求、例外情況、審核責任、期限與完整例子。現行與舊版住宿文件都寫成可閱讀的完整規定，讓版本過濾與來源引用有實際測試價值，而不是各寫幾句。金額、日期和規則均為自訂假資料。

## 問答細節（已確認）

- 網頁可顯示多輪對話、每次回答的來源，並有「清除對話」按鈕。後端每次最多使用最近 **3 輪**對話，避免追問帶入太久以前的話題。
- 後端搜尋相近程度最高的 **3 個生效中小節**，交給回答模型；答案只引用這些小節。若使用者明確詢問舊規定，回覆「目前只提供現行規定」。
- 用自行設計的問題驗證：直接問、追問、換話題、問不存在的補助，以及舊版與新版的住宿上限。找不到支持內容時回覆查無資料，不編造金額。
- 若 Gemini API key 未設定、免費額度已用完或 API 暫時失敗，顯示可理解的錯誤訊息；不把 key 或原始錯誤細節送到前端。

## Terraform 與部署順序（已確認的設計）

Terraform 分成兩階段，因為 Cloud Run 需要先有程式映像，Secret Manager 也需要先有 key 的值：

1. `bootstrap` 建立必要的 GCP API、私人 Cloud Storage、假文件、Artifact Registry（存放程式映像）與 Secret Manager 的空殼。
2. 使用者手動把自己的 Gemini API key 加入 Secret Manager；用 Cloud Build 建立映像並放進 Artifact Registry。這兩步不把 key 寫進 Terraform 或 GitHub。
3. `app` 建立 Cloud Run service、Cloud Run Job，以及各自只讀取必要資料的服務帳號與權限。Service 保持私人並由 IAP 驗證 Google 帳號登入（直接啟用於 Cloud Run，不需 Load Balancer）、閒置時不維持常駐實例；Job 不排程。
4. 手動執行 Job 產生 `processed/` 索引，再開啟服務網址、以授權的 Google 帳號登入測試。日後修改文件：更新 GitHub 文件、重新執行 Terraform 上傳、再執行 Job。

使用 `us-central1` 作為示範地區：假資料示範可符合 Cloud Storage 的美國地區免費用量條件；若考慮真實企業資料，需要另評估資料存放地區。即使選免費用量地區，也不保證付費帳戶絕不產生費用；實際部署前必須檢查 GCP 帳戶狀態。Gemini API key 也必須確認屬於 AI Studio 的 Free Tier 專案。

## 繳交與加分項目（已確認的設計）

- 必做：Python 原始碼、GitHub 儲存庫、雲端架構圖、README（用途、功能、服務選擇理由、執行與部署步驟）。架構圖以實際程式及 Terraform 為準。
- 已選加分：簡單前端、Terraform IaC。
- 已選加分：GitHub Actions 在提交時執行 Python 測試與 Terraform 格式／語法檢查；不自動部署。
- 驗證：本機離線問答不需要 key；自動測試驗證文件處理、版本過濾和 API。若工具可用，Terraform 執行格式與語法檢查。Gemini 實際呼叫、雲端部署與 `terraform apply` 本次均不執行，必須標示為未驗證。

## 本次驗證與交接

- `python -m app.indexer` 已在本機建立 36 個章節的索引；`python -m pytest -q` 為 15 項通過（含 GCS 索引快取與 Gemini 逾時預算的測試）。
- 啟動本機 Uvicorn 後，實際 HTTP 問答驗證住宿上限 2,500 元、憑證追問、餐費上限 300 元、舊規定排除與無依據問題拒答。
- Chromium 瀏覽器驗證送出問題、顯示來源、追問、清除對話及重新整理後清除；畫面見 `docs/images/local-demo.png`。
- Terraform 的 `fmt`、兩階段 `init -backend=false` 與 `validate` 已通過；沒有執行 `plan` 或 `apply`。Docker 映像未建置，因本機沒有 Docker CLI。
- 下一步由開發者理解程式與架構、檢查假規定內容，再自行決定是否建立 GitHub 儲存庫並上傳。若要維持零帳單，不執行任何雲端部署或遠端 API 測試。

參考：[Google Cloud 免費用量](https://docs.cloud.google.com/free/docs/free-cloud-features)、[Gemini API 價格](https://aistudio.google.com/docs/pricing)、[Gemini API 計費狀態](https://aistudio.google.com/docs/billing)、[私人 Cloud Run 測試](https://docs.cloud.google.com/run/docs/authenticating/developers)。
