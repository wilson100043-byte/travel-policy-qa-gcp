# 部署步驟與權限設計

本專案只交付可審查的 Terraform 與本機程式，**沒有執行任何 `terraform apply`、Cloud Build 或 Cloud Run，也沒有建立 GCP 資源。**下列步驟說明日後在公司專案部署時的順序；設計依據見[需求規格](REQUIREMENTS.md)。

## 前提

- 公司使用 Google Workspace，GCP 專案屬於公司的 Google Cloud 組織。這樣 IAP 可以使用 Google 管理的 OAuth client，員工以公司帳號登入，不需手動建立 OAuth 設定。
- 在 Google Workspace 管理控制台**強制所有員工開啟兩步驟驗證**（NFR-7）。這是 Workspace 的帳號政策，不由 Terraform 管理。
- **Vertex AI 的模型與區域。**只採用官方文件明確列出可用的組合：生成用 `gemini-3.5-flash-lite`（`us` 多區域），Embedding 用 `gemini-embedding-001`（`us-central1`）。官方沒有列出台灣提供這些模型，因此 AI 推論在美國處理；文件、索引與執行環境仍留在台灣。不使用 `global` 端點，因為它不保證資料處理地點。

## 對應架構

| 階段 | Terraform 內容 | 執行後的狀態 |
| --- | --- | --- |
| `infra/bootstrap` | 啟用必要 API；建立私人 Cloud Storage bucket（開啟版本保留）；建立 Artifact Registry Docker repository。 | bucket 是空的，尚未有規定文件與索引。 |
| 手動準備 | Cloud Build 建置映像並推送到 Artifact Registry。 | 映像就緒。 |
| `infra/app` `main.tf` | 服務帳號與權限、啟用 IAP 的 Cloud Run Service、Cloud Run Job、管理部門的上傳權限。 | 服務上線，但還沒有索引。 |
| `infra/app` `reindex.tf` | Eventarc 觸發器與 Workflows：`raw/` 有新的 `.md` 檔時自動執行 Job。 | 上傳規定後自動產生索引。 |
| `infra/app` `monitoring.tf` | 回應過慢、伺服器錯誤、索引失敗三個告警，以及 IAP 存取稽核記錄。 | 異常時寄信通知系統管理者。 |

## 不連接雲端的檢查

以下指令只下載 Terraform provider 並檢查設定，不讀取 GCP 帳戶、不建立資源。GitHub Actions 每次 push 也會執行相同檢查。

```sh
terraform fmt -check -recursive infra
terraform -chdir=infra/bootstrap init -backend=false -input=false
terraform -chdir=infra/bootstrap validate -no-color
terraform -chdir=infra/app init -backend=false -input=false
terraform -chdir=infra/app validate -no-color
```

## 部署順序

> 以下指令會建立雲端資源並產生費用，本專案沒有執行。

1. 複製 `infra/bootstrap/terraform.tfvars.example` 為 `terraform.tfvars`，填入專案 ID 與全球唯一的 bucket 名稱，然後套用：

   ```sh
   terraform -chdir=infra/bootstrap init
   terraform -chdir=infra/bootstrap apply
   ```

2. 查詢專案實際的 Cloud Build 執行身分，填入 `cloud_build_service_account_email` 後再套用一次 bootstrap，讓它取得這個 repository 的寫入權限：

   ```sh
   gcloud builds get-default-service-account --project=YOUR_GCP_PROJECT_ID --region=asia-east1
   ```

3. 用唯一的 tag 建置映像。`.gcloudignore` 會排除 `.env*`、Terraform state 與虛擬環境；映像 tag 不可覆寫：

   ```sh
   gcloud builds submit . --config=cloudbuild.yaml --region=asia-east1 \
     --project=YOUR_GCP_PROJECT_ID --substitutions=_IMAGE_TAG=YOUR_UNIQUE_TAG
   ```

4. 複製 `infra/app/terraform.tfvars.example` 為 `terraform.tfvars`，填入映像路徑、員工群組（`authorized_users`）、管理部門群組（`policy_admins`）、維運人員（`authorized_job_executors`）與告警信箱（`alert_email`），然後套用：

   ```sh
   terraform -chdir=infra/app init
   terraform -chdir=infra/app apply
   ```

5. 管理部門上傳規定文件到 `raw/`。上傳完成後，Eventarc 會啟動 Workflows，再由 Workflows 執行索引 Job：

   ```sh
   gcloud storage cp policy_docs/*.md gs://YOUR_BUCKET/raw/
   ```

6. 員工用瀏覽器開啟 `terraform -chdir=infra/app output service_url` 顯示的網址，以公司帳號登入即可使用，不需要安裝任何工具。

更新映像後，可由維運人員手動執行一次索引 Job，確保索引與新程式相容：

```sh
gcloud run jobs execute travel-policy-rag-index --region=asia-east1 --project=YOUR_GCP_PROJECT_ID
```

## 權限設計

| 身分 | 權限 | 目的 |
| --- | --- | --- |
| 員工群組 | IAP `roles/iap.httpsResourceAccessor` | 登入使用網頁；不能存取 bucket 或其他資源。 |
| IAP 服務代理 | Cloud Run `roles/run.invoker` | IAP 驗證身分後，代替使用者呼叫 Service；使用者本身沒有 Invoker 權限。 |
| 管理部門群組 | bucket `objectViewer`；`objectAdmin`，條件限定 `raw/` | 瀏覽並上傳、更新規定文件。 |
| `travel-rag-api` | bucket `objectViewer`；專案 `roles/aiplatform.user` | Service 讀取索引、呼叫 Vertex AI。 |
| `travel-rag-indexer` | bucket `objectViewer`；`objectAdmin`，條件限定 `processed/`；專案 `roles/aiplatform.user` | Job 讀取規定、寫入索引、呼叫 Embedding。 |
| `travel-rag-reindex` | `eventarc.eventReceiver`、`workflows.invoker`、`logging.logWriter`；Job 的 `run.jobsExecutor` | 接收上傳事件，只能啟動這一個 Job。 |
| Cloud Storage 服務代理 | `roles/pubsub.publisher` | 將上傳事件送給 Eventarc。 |
| 維運人員 | Job 的 `run.jobsExecutor` | 必要時手動重建索引。 |

- 沒有任何身分使用長期 API key；Service 與 Job 以服務帳號呼叫 Vertex AI（NFR-9）。
- 沒有授予 `allUsers` 或 `allAuthenticatedUsers`。
- Cloud Storage 的列出物件權限在 bucket 層級授權，所以管理部門與 Job 都看得到 bucket 內所有檔名，但只能修改各自的路徑。

## 資料保存與稽核

- **版本保留**：bucket 開啟物件版本，每個檔案保留最近 10 個舊版本，規定改錯時可以還原（NFR-12）。
- **存取記錄**：開啟 IAP 的 Data Access 稽核記錄，記錄誰在何時進入系統（NFR-11）。
- **不記錄提問內容**：程式不寫入提問文字；Cloud Run 的請求記錄只包含網址路徑，例如 `POST /api/ask`。

## 已知限制

- 自動重建索引：短時間內上傳多個檔案時，每個檔案都會啟動一次 Job。Job 每次都重建完整索引，結果一致，但會重複執行。
- 告警門檻：Cloud Monitoring 沒有第 90 百分位的對齊器，回應時間告警使用第 95 百分位、門檻 8 秒，比需求略嚴格。
- 以上設定都只通過 Terraform 靜態檢查，IAM、Eventarc 與告警的實際行為尚未在 GCP 上驗證。

## 來源

- [Cloud Run 直接啟用 IAP](https://docs.cloud.google.com/run/docs/securing/identity-aware-proxy-cloud-run)
- [IAP for Cloud Run 的 OAuth 與組織限制](https://docs.cloud.google.com/iap/docs/enabling-cloud-run)
- [用 Eventarc 與 Workflows 執行 Cloud Run Job](https://docs.cloud.google.com/workflows/docs/tutorials/execute-cloud-run-jobs)
- [Eventarc 支援的區域](https://docs.cloud.google.com/eventarc/docs/locations)
- [Workflows 支援的區域](https://docs.cloud.google.com/workflows/docs/locations)
- [Vertex AI 生成式 AI 的區域](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/locations)
- [Vertex AI 資料落地](https://docs.cloud.google.com/gemini-enterprise-agent-platform/resources/data-residency)
- [Cloud Storage IAM 條件與 object listing 限制](https://docs.cloud.google.com/storage/docs/access-control/iam)
