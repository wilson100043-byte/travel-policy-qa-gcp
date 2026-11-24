# 差旅報帳規定問答系統

這是**假想企業內部文件問答示範**。使用者在網頁輸入問題，系統從自編的差旅報帳規定找出相關小節，回答並列出文件來源。所有規定、金額、日期及流程都是虛構測試資料

情境設定為約 200 名員工的中小企業：員工以公司帳號登入後提問，Vertex AI 依現行規定生成答案；管理部門上傳新規定後，系統自動重建索引。雲端架構以 Terraform 設計在 GCP 台灣區域，**只做設計與靜態驗證，沒有實際部署**。本機另有離線模式，不需任何帳號即可測試。

## 快速導覽

| 想看什麼 | 位置 |
| --- | --- |
| 需求與設計依據 | [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) |
| 雲端架構圖 | [架構與技術選擇](#架構與技術選擇)、[架構說明](docs/ARCHITECTURE.md) |
| 部署步驟與權限設計 | [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) |
| CI/CD 流程圖 | [docs/CICD.md](docs/CICD.md) |
| 多人協作 Git 流程 | [docs/GIT_WORKFLOW.md](docs/GIT_WORKFLOW.md) |
| 在本機執行 | [五分鐘在本機啟動](#五分鐘在本機啟動) |
| 問答與檢索程式 | [`app/rag.py`](app/rag.py)、[`app/indexer.py`](app/indexer.py)、[`app/vertex.py`](app/vertex.py) |
| Terraform | [`infra/bootstrap`](infra/bootstrap)、[`infra/app`](infra/app) |
| 開發過程與驗證紀錄 | [docs/PROJECT_PLAN.md](docs/PROJECT_PLAN.md) |

## 主要功能

- 員工用中文提問並追問，答案附上依據的文件與章節。
- 只引用目前生效的規定；文件中找不到依據時，明說查無資料。
- 管理部門上傳規定到 Cloud Storage 後，自動重建索引。
- 對話只存在瀏覽器，伺服器不保存提問內容。
- 本機離線模式：不需 API key、不連網，評審可以直接測試完整流程。

## 五分鐘在本機啟動

需要 Python 3.9 以上。以下指令只安裝本機 Python 套件，使用離線模式，不會連接任何雲端服務。

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m app.indexer
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

開啟 <http://127.0.0.1:8000>，例如問「住宿費每晚可以報多少？」或「那需要附什麼憑證？」。`python -m app.indexer` 會事先建立本機索引；若沒有先執行，後端也會在第一次提問時建立索引。

![本機問答畫面：住宿費上限與引用來源](docs/images/local-demo.png)

離線模式用 TF-IDF 檢索，從找到的章節抽取原文句子回答，**不是由大型語言模型生成**。雲端部署時由 Terraform 設定 `AI_MODE=vertex`，改用 Vertex AI 生成回答。

## 架構與技術選擇

![GCP 雲端架構圖：建置、索引、問答三條流程與 IAM 權限](docs/diagrams/cloud-architecture.png)

圖中列出 Terraform 設定的實際資源名稱、service account、IAM 權限與執行規格。①②③ 分別對應建置映像、建立索引、使用者提問三條流程。圖中內容都是設定，尚未在 GCP 上實際部署。

互動版 [`docs/diagrams/cloud-architecture.html`](docs/diagrams/cloud-architecture.html) 含逐步流程導覽；GitHub 不會直接執行 HTML，請下載後以瀏覽器開啟。

| 流程 | 元件 | 用途與選擇理由 |
| --- | --- | --- |
| ③ 使用者提問 | 前端（原生 HTML、CSS、JavaScript） | 送出問題、顯示回答與來源；單一頁面，與 API 放在同一個服務。 |
| ③ 使用者提問 | IAP | 員工以公司 Google 帳號登入，只有授權名單可使用；直接啟用於 Cloud Run，不需 Load Balancer。 |
| ③ 使用者提問 | Cloud Run Service（FastAPI） | 提供網頁與 `/api/ask`；保留 1 個實例避免冷啟動，最多 5 個實例、每個同時處理 10 個請求。 |
| ② ③ | Vertex AI | Embedding、追問改寫與生成回答；以服務帳號驗證，不需要 API key。 |
| ② 建立索引 | Cloud Storage | 私人 bucket：`raw/` 放規定，`processed/` 放索引 JSON；開啟版本保留，規定改錯可還原。 |
| ② 建立索引 | Eventarc、Workflows | 管理部門上傳規定後，自動啟動索引 Job。 |
| ② 建立索引 | Cloud Run Job | 依 `##` 切分章節、產生向量、寫入索引；跑完即結束。 |
| ① 建置映像 | Cloud Build、Artifact Registry | 建置並保存容器映像；Job 與 Service 共用同一映像，tag 不可覆寫。 |
| 維運 | Cloud Monitoring、Cloud Logging | 回應過慢、伺服器錯誤、索引失敗時寄信通知；記錄誰存取系統。 |
| 基礎設施 | Terraform | 分 `bootstrap` 與 `app` 兩階段建立資源；每個工作負載各用獨立 service account。 |
| 品質檢查 | pytest、GitHub Actions | 測試文件處理、版本過濾、索引快取、Vertex AI 呼叫與 API；CI 另執行 Terraform `fmt` 與 `validate`，不含部署。 |

各元件對應的需求編號與詳細理由見[架構說明](docs/ARCHITECTURE.md)。

## 測試

```bash
python -m pytest
```

GitHub Actions 在 push 與 Pull Request 時執行上述測試，以及 Terraform 的 `fmt` 與 `validate` 靜態檢查；CI 不含任何部署步驟。完整流程見 [CI/CD 流程](docs/CICD.md)。

可以手動檢查：

1. 問「目前住宿費上限是多少？」應引用現行住宿規定，不引用舊版金額。
2. 接著問「要附什麼？」應能利用近期對話找到住宿憑證條款。
3. 問文件沒有記載的補助，應明確表示找不到依據。
4. 重新整理網頁，舊對話應消失。

## 專案結構

```text
.
├── app/                  FastAPI 後端：文件解析、索引、檢索、Vertex AI 呼叫
├── web/                  前端頁面（原生 HTML、CSS、JavaScript）
├── policy_docs/          四份虛構差旅報帳規定（Markdown）
├── tests/                pytest 自動測試
├── infra/
│   ├── bootstrap/        Terraform 第一階段：API、Cloud Storage、Artifact Registry
│   └── app/              Terraform 第二階段：Cloud Run、IAP、IAM、自動索引、監控
├── docs/
│   ├── REQUIREMENTS.md   需求規格
│   ├── ARCHITECTURE.md   架構與服務選擇理由
│   ├── DEPLOYMENT.md     部署步驟與權限設計
│   ├── CICD.md           CI/CD 流程圖
│   ├── GIT_WORKFLOW.md   多人協作 Git 流程
│   ├── PROJECT_PLAN.md   開發過程與驗證紀錄
│   ├── diagrams/         架構圖（PNG、互動 HTML）與 PNG 匯出腳本
│   └── images/           本機執行畫面
├── .github/workflows/    CI：pytest 與 Terraform 靜態檢查
├── Dockerfile            Cloud Run 映像
└── cloudbuild.yaml       Cloud Build 建置設定
```

## 已知限制

- 雲端部分只通過 Terraform 靜態檢查，尚未實際部署；Vertex AI 的回答品質未經驗證。
- 文件與執行環境放在台灣，但官方沒有列出台灣提供所需的 Gemini 模型，所以 AI 推論採用官方確認可用的美國區域，見[需求規格](docs/REQUIREMENTS.md)。
- 規定為全公司共用，沒有依部門區分文件權限；也不提供報銷申請等交易功能。
- 規定文件為虛構資料，只用來展示系統流程。
