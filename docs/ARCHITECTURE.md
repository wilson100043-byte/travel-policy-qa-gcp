# 雲端架構說明

本文件說明系統由哪些部分組成、每個部分選用哪項 GCP 服務，以及選擇的理由。架構依[需求規格](REQUIREMENTS.md)設計，括號中的編號對應需求；雲端部分只做設計與 Terraform 靜態驗證，尚未部署。

![GCP 雲端架構圖：建置、索引、問答三條流程與 IAM 權限](diagrams/cloud-architecture.png)

互動版 [`cloud-architecture.html`](diagrams/cloud-architecture.html) 含逐步流程導覽，下載後以瀏覽器開啟。

## 一句話說明

員工以公司帳號登入後提問；Cloud Run 上的 FastAPI 從索引找出現行規定中最相關的章節，交給 Vertex AI 整理成答案並附上來源。管理部門上傳新規定後，系統自動重建索引。

## 系統組成

| 角色 | GCP 服務 | 負責什麼 | 選用原因 |
| --- | --- | --- | --- |
| 使用者介面 | Cloud Run Service（與 API 同一服務） | 提問、顯示答案與來源；對話只存在瀏覽器（FR-6）。 | 只有一頁，不需另外架設網站或處理 CORS。 |
| 登入 | IAP | 員工以公司 Google 帳號登入，名單外的人進不來（NFR-7）。 | 直接啟用於 Cloud Run，不需 Load Balancer；採零信任做法，不限制連線地點。 |
| 問答 API | Cloud Run Service（FastAPI） | 改寫追問、檢索現行規定、呼叫 Vertex AI 生成答案。 | 免管伺服器、依流量自動擴充；保留 1 個實例避免冷啟動（NFR-1、NFR-3）。 |
| AI 模型 | Vertex AI（Gemini、gemini-embedding-001） | 文件與問題的向量、追問改寫、生成回答。 | 以服務帳號驗證，不需要 API key（NFR-9）。 |
| 文件與索引儲存 | Cloud Storage | `raw/` 放規定文件，`processed/` 放索引 JSON；開啟版本保留（NFR-12）。 | 數百份文件、數千個章節，一個 JSON 讀進記憶體即可，不需向量資料庫（NFR-6）。 |
| 建立索引 | Cloud Run Job | 切分章節、產生向量、寫入索引。 | 偶爾執行的批次工作，跑完就結束，不佔常駐資源。 |
| 自動觸發 | Eventarc＋Workflows | 管理部門上傳規定後，自動啟動索引 Job（FR-5、NFR-5）。 | Eventarc 無法直接啟動 Job，官方做法是經由 Workflows。 |
| 建置 | Cloud Build＋Artifact Registry | 建置並保存容器映像，tag 不可覆寫。 | 在雲端建置，結果一致、版本可追溯。 |
| 監控與稽核 | Cloud Monitoring＋Cloud Logging | 回應過慢、錯誤、索引失敗時通知；記錄誰存取系統（NFR-10、NFR-11）。 | GCP 內建，不需另外架設。 |
| 基礎設施 | Terraform | 以程式碼定義上述所有資源。 | 可審查、可重建。 |

## 三條主要流程

編號與架構圖的 ①②③ 一致。

1. **① 建置映像：** Terraform bootstrap 建立儲存空間與映像庫；以 `gcloud builds submit` 交由 Cloud Build 建置映像；Terraform app 再建立 Service、Job、IAP、自動觸發與告警。
2. **② 建立索引：** 管理部門上傳規定到 `raw/` → Eventarc 收到上傳事件 → Workflows 確認是 `raw/` 下的 `.md` 檔 → 啟動 Cloud Run Job。Job 讀取文件、依 `##` 切章節、標記生效日期，呼叫 Vertex AI 產生向量，寫入 `processed/index.json`。
3. **③ 使用者提問：** 員工開啟網址，經 IAP 以公司帳號登入 → FastAPI 讀取索引（依版本號快取）→ 改寫追問、排除失效規定、取最相關的 3 個章節 → Vertex AI 依章節生成答案 → 回傳答案與來源。找不到依據時明說查無資料。

## 容量設計

| 項目 | 設定 | 依據 |
| --- | --- | --- |
| 最少實例 | 1 | 全天保留，上班時間第一位使用者不用等冷啟動（NFR-3）。 |
| 每個實例同時處理 | 10 個請求 | 請求大部分時間在等 Vertex AI 回覆，1 vCPU 可以同時處理。 |
| 最多實例 | 5 | 5 × 10 = 50 個同時請求，是尖峰 25 人的 2 倍（NFR-1）。 |
| 記憶體 | 1 GiB | 索引整份讀進記憶體，數千個章節仍在範圍內（NFR-6）。 |
| 請求逾時 | 60 秒 | 一題最多呼叫 Vertex AI 3 次，每次最多 15 秒。 |

文件超過約一萬個章節，或需要依部門過濾文件時，再改用向量資料庫（例如 Vertex AI Vector Search 或 Cloud SQL 的 pgvector）。

## 本機模式

本機開發與評審測試時，`AI_MODE=local`：直接讀取 `policy_docs/`，用 TF-IDF 檢索並抽取原文句子回答，不連網、不需要任何雲端帳號。雲端部署時由 Terraform 設定 `AI_MODE=vertex`。

## 安全重點

- 服務不公開：只有 IAP 授權名單內、已開兩步驟驗證的員工能進入。
- 每個工作負載各用一個服務帳號，只拿需要的權限；Job 只能寫 `processed/`，管理部門只能寫 `raw/`。
- 沒有長期 API key，也就不需要 Secret Manager。
- 資料存放在台灣（asia-east1）。Vertex AI 的推論地點要在部署前確認，見[部署文件](DEPLOYMENT.md)。

## 編輯與重產生

架構圖的來源是 `diagrams/cloud-architecture.html`，方塊、連線與流程導覽都定義在頁面內的 JavaScript。修改後執行 `python3 docs/diagrams/export_png.py`，會先檢查文字是否超出方塊，再匯出 2 倍解析度的 `cloud-architecture.png`（需要 Python Playwright 與 Chromium）。

GCP 產品圖示來自 [Google Cloud 官方圖示庫](https://cloud.google.com/icons)，已內嵌在 HTML 中。
