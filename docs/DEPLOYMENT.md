# 部署與費用界線

目前只交付可審查的 Terraform 與本機程式；**本專案沒有執行任何 `terraform apply`、Cloud Build、Cloud Run Job，也沒有建立 GCP 資源。**下方雲端命令是日後由持有者自行評估費用後使用的操作範例，不是零費用承諾。即使服務能縮到 0，Cloud Storage、Secret Manager、Artifact Registry、Cloud Build、Cloud Logging 和 API 呼叫仍可能產生用量或費用。若要求「不產生任何帳單」，請停在本機執行與靜態檢查。

## 對應架構

| 階段 | Terraform 內容 | 執行後的資料 |
| --- | --- | --- |
| `infra/bootstrap` | 啟用必要 API、私人 Cloud Storage bucket、上傳 `policy_docs/*.md` 至 `raw/`、建立 Artifact Registry Docker repository、建立**沒有版本或值**的 Secret Manager secret。 | `raw/*.md`，尚無 `processed/index.json`。 |
| 手動準備 | 把自己的 Gemini API key 以標準輸入加入 Secret Manager；Cloud Build 將同一份 Docker image 推到 Artifact Registry。 | Terraform state、Git 和映像都不保存 API key。 |
| `infra/app` | 兩個各自的 runtime service account、bucket/secret 的 IAM 權限、啟用 IAP 的私人 Cloud Run service、IAP 使用者授權、手動 Cloud Run Job。 | Job 執行後才有 `processed/index.json`，Service 才能查詢。 |

`app` 的 `ai_mode` 預設是 `offline`，不設定 Gemini key、不呼叫遠端 AI。若要開啟 Gemini，需同時把 `ai_mode` 改為 `gemini`、`gemini_free_tier_confirmed` 設為 `true`，而且 Secret Manager 中要先有可用版本。這是程式內的操作護欄，**不能證明 GCP 或 Gemini 不收費**。

## 不連接雲端的檢查

需要本機 Terraform CLI；以下指令只下載 Terraform provider 並檢查設定，不讀取 GCP 帳戶、不建立資源：

```sh
terraform fmt -check -recursive infra
terraform -chdir=infra/bootstrap init -backend=false -input=false
terraform -chdir=infra/bootstrap validate -no-color
terraform -chdir=infra/app init -backend=false -input=false
terraform -chdir=infra/app validate -no-color
```

GitHub Actions 的 CI 也只做 Python 測試、Terraform `fmt` 和 `validate`；沒有 GCP 憑證、`plan`、`apply`、Cloud Build 或部署權限。依 [GitHub Actions 計費規則](https://docs.github.com/en/actions/concepts/billing-and-usage)，公開儲存庫的標準 runner 免費，但私人儲存庫超過內含時數可能計費。因此 workflow 在**私人儲存庫會跳過兩個 job**；先在本機執行檢查，只有公開儲存庫才自動跑 CI。

## 只有自行決定部署後才使用的步驟

1. 準備**獨立測試專案**、檢查其帳單狀態與 GCP/AI Studio 免費用量規則，並知道停止、刪除資源的方法。免費用量不是「絕不計費」開關。Terraform 目前使用本機 state；`*.tfstate` 和 `*.tfvars` 已列入 `.gitignore`，也不要分享這些檔案。
2. 複製 `infra/bootstrap/terraform.tfvars.example` 為 `infra/bootstrap/terraform.tfvars`，填入既有 `project_id` 和全球唯一的 `bucket_name`。四份假政策應已存在於 `policy_docs/`。
3. 初始化並套用 bootstrap。**下列操作會修改雲端資源，現在不要執行：**

   ```sh
   terraform -chdir=infra/bootstrap init
   terraform -chdir=infra/bootstrap plan
   terraform -chdir=infra/bootstrap apply
   ```

4. 查詢此專案實際的 Cloud Build 執行身分；新舊 GCP 專案可能使用不同的預設 service account。把查到的 email 放進 bootstrap 的 `cloud_build_service_account_email`，再檢查並套用 bootstrap，使它取得**該 repository** 的 Artifact Registry writer 權限。若專案原有額外組織限制，應按限制調整建置身分。

   ```sh
   gcloud builds get-default-service-account --project=YOUR_GCP_PROJECT_ID --region=us-central1
   terraform -chdir=infra/bootstrap plan
   terraform -chdir=infra/bootstrap apply
   ```

5. Gemini 模式才需要加入 Secret Manager secret version。不要把 key 放在 `.tfvars`、GitHub Actions secret、指令參數、Docker build argument、一般文件或程式碼。以下在終端機隱藏輸入，透過標準輸入傳給 `gcloud`；本機 shell 變數在該終端機關閉後消失。

   ```sh
   read -r -s GEMINI_API_KEY
   printf '%s' "$GEMINI_API_KEY" | gcloud secrets versions add travel-rag-gemini-api-key \
     --project=YOUR_GCP_PROJECT_ID --data-file=-
   unset GEMINI_API_KEY
   ```

6. 確認工作區沒有真實公司資料或本機 key，選一個唯一 image tag，才手動建置。根目錄 `.gcloudignore` 排除 `.env*`、Terraform state、虛擬環境與本機索引；可以先用 `gcloud meta list-files-for-upload` 在本機檢查實際會上傳的檔案。`cloudbuild.yaml` 只建置和推送映像；不傳入 Gemini key。Artifact Registry 的 immutable tags 防止同名標籤被覆蓋。`gcloud builds submit` 本身會上傳本機來源並可能產生 Cloud Build 用量。

   ```sh
   gcloud builds submit . --config=cloudbuild.yaml --region=us-central1 \
     --project=YOUR_GCP_PROJECT_ID \
     --substitutions=_IMAGE_TAG=YOUR_UNIQUE_TAG
   ```

   映像路徑為 `us-central1-docker.pkg.dev/PROJECT_ID/travel-policy-rag/app:YOUR_UNIQUE_TAG`。如果 build identity 缺少 staging bucket 或 Logging 權限，先依錯誤訊息修正該專案的 build IAM；不要改成給所有 service account 專案層級 Editor 權限。

7. **IAP 首次設定。**服務以 IAP（Identity-Aware Proxy，Google 帳號登入閘道）保護，使用者開啟網址並以 Google 帳號登入後才能使用。依官方文件，若專案**不屬於任何 Google Cloud 組織**（例如個人帳號建立的專案），無法以程式建立 OAuth client，第一次啟用 IAP 須先在 Cloud Run Console 完成設定；要讓組織外帳號（例如一般 Gmail）登入時，OAuth 同意畫面須設為「外部」類型，並使用自訂 OAuth client。屬於組織的專案則可使用 Google 管理的 OAuth client，但只涵蓋組織內帳號。

8. 複製 `infra/app/terraform.tfvars.example` 為 `infra/app/terraform.tfvars`，填入同一個專案、bucket 和實際 image URI。`authorized_users` 填入可以登入使用網頁的帳號（`user:email` 或 `group:email`），`authorized_job_executors` 填入可以執行索引 Job 的帳號。如果要遠端 Gemini，確認 AI Studio Free Tier 專案與 key 後才設 `ai_mode = "gemini"`、`gemini_free_tier_confirmed = true`。接著手動套用：

   ```sh
   terraform -chdir=infra/app init
   terraform -chdir=infra/app plan
   terraform -chdir=infra/app apply
   ```

9. 手動執行一次索引 Job；更新假文件後也要重跑 bootstrap 上傳及 Job。Job 不排程、不自動執行。

   ```sh
   gcloud run jobs execute travel-policy-rag-index --region=us-central1 \
     --project=YOUR_GCP_PROJECT_ID --wait
   ```

10. 用瀏覽器開啟 `terraform -chdir=infra/app output service_url` 顯示的網址，以 `authorized_users` 中的 Google 帳號登入即可使用；使用者不需要安裝 gcloud 或執行任何指令。未列入名單的帳號會被 IAP 拒絕，請求不會進入應用程式。

    `gcloud run services proxy` 在啟用 IAP 後是否仍可使用，官方文件沒有說明，本專案不以它作為存取方式。

## 權限與資料範圍

- Cloud Run service 與 Job 各用獨立 service account；兩者只有私人 bucket 的 object viewer 權限。
- Job 額外有一筆帶條件的 object admin 權限，只能替換 `processed/` 物件。由於 Cloud Storage 的 object listing 在 bucket 層級授權，Job 仍能列出 bucket 內物件；此限制已在設計中明示。
- `ai_mode = "gemini"` 時，兩個 runtime service account 才取得對**單一 secret** 的 accessor 權限，Cloud Run 只引用 `latest` 版本。Terraform 只管理 secret 空殼與 IAM，不管理 secret value/version。
- 使用者透過 IAP 登入：`authorized_users` 取得 `roles/iap.httpsResourceAccessor`；Cloud Run Invoker 只授予 IAP 的 service agent（`service-PROJECT_NUMBER@gcp-sa-iap.iam.gserviceaccount.com`），使用者本身不直接持有 Invoker。Terraform 沒有授予 `allUsers` 或 `allAuthenticatedUsers`。
- IAP 直接啟用於 Cloud Run，保護預設的 `run.app` 網址，不需要建立 Load Balancer。`INGRESS_TRAFFIC_ALL` 讓瀏覽器能連到 `run.app` 網址，存取權由 IAP 控制。
- Bucket 啟用 uniform bucket-level access、public access prevention，並關閉 Cloud Storage 預設 7 天 soft delete，避免每次覆寫假資料後保留舊物件。這些設定是測試資料的取捨；真實公司文件需要重新設計保存政策。

## 來源

- [Cloud Run 直接啟用 IAP](https://docs.cloud.google.com/run/docs/securing/identity-aware-proxy-cloud-run)
- [IAP for Cloud Run 的 OAuth 與組織限制](https://docs.cloud.google.com/iap/docs/enabling-cloud-run)
- [Cloud Build 預設 service account 可能不同](https://docs.cloud.google.com/build/docs/cloud-build-service-account-updates)
- [Cloud Storage IAM 條件與 object listing 限制](https://docs.cloud.google.com/storage/docs/access-control/iam)
- [Cloud Storage objectCreator 無法覆寫](https://docs.cloud.google.com/storage/docs/access-control/iam-roles)
- [Cloud Run 的 Secret Manager 設定](https://docs.cloud.google.com/run/docs/configuring/services/secrets)
