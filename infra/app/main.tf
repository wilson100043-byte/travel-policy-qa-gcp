locals {
  vertex_enabled = var.ai_mode == "vertex"

  # Shared by the Service and the Job so both read the same bucket and models.
  runtime_env = {
    STORAGE_MODE              = "gcs"
    GCS_BUCKET                = var.bucket_name
    GCS_RAW_PREFIX            = "raw/"
    GCS_PROCESSED_OBJECT      = "processed/index.json"
    AI_MODE                   = var.ai_mode
    GOOGLE_CLOUD_PROJECT      = var.project_id
    VERTEX_LOCATION           = var.vertex_location
    VERTEX_EMBEDDING_LOCATION = var.vertex_embedding_location
    VERTEX_GENERATION_MODEL   = var.generation_model
    VERTEX_EMBEDDING_MODEL    = var.embedding_model
  }
}

data "google_project" "current" {
  project_id = var.project_id
}

# ---------- Runtime identities (one per workload) ----------

resource "google_service_account" "api" {
  project      = var.project_id
  account_id   = "travel-rag-api"
  display_name = "Travel policy Q&A API runtime"
}

resource "google_service_account" "indexer" {
  project      = var.project_id
  account_id   = "travel-rag-indexer"
  display_name = "Travel policy Q&A indexing job runtime"
}

# Both workloads can read the documents and index in the private bucket.
resource "google_storage_bucket_iam_member" "api_read" {
  bucket = var.bucket_name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.api.email}"
}

resource "google_storage_bucket_iam_member" "indexer_read" {
  bucket = var.bucket_name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.indexer.email}"
}

# The Job may replace only processed/ objects. Its viewer grant above allows
# listing raw/; objectCreator alone cannot overwrite the existing index.
resource "google_storage_bucket_iam_member" "indexer_write_processed" {
  bucket = var.bucket_name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.indexer.email}"

  condition {
    title       = "write_processed_only"
    description = "Limit object writes to the processed index prefix"
    expression  = "resource.name.startsWith('projects/_/buckets/${var.bucket_name}/objects/processed/')"
  }
}

# Vertex AI is called with the service account identity: no API key (NFR-9).
resource "google_project_iam_member" "api_vertex" {
  count = local.vertex_enabled ? 1 : 0

  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.api.email}"
}

resource "google_project_iam_member" "indexer_vertex" {
  count = local.vertex_enabled ? 1 : 0

  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.indexer.email}"
}

# ---------- Policy publishing (NFR-13) ----------

# The administration team can browse the bucket and replace policies in raw/
# only; employees have no access to the bucket at all.
resource "google_storage_bucket_iam_member" "policy_admin_view" {
  for_each = toset(var.policy_admins)

  bucket = var.bucket_name
  role   = "roles/storage.objectViewer"
  member = each.value
}

resource "google_storage_bucket_iam_member" "policy_admin_write_raw" {
  for_each = toset(var.policy_admins)

  bucket = var.bucket_name
  role   = "roles/storage.objectAdmin"
  member = each.value

  condition {
    title       = "write_raw_only"
    description = "Limit policy uploads to the raw/ prefix"
    expression  = "resource.name.startsWith('projects/_/buckets/${var.bucket_name}/objects/raw/')"
  }
}

# ---------- Web page and API ----------

resource "google_cloud_run_v2_service" "api" {
  project              = var.project_id
  name                 = var.service_name
  location             = var.region
  ingress              = "INGRESS_TRAFFIC_ALL"
  invoker_iam_disabled = false
  deletion_protection  = false
  # Users open the run.app URL and sign in with a Google account; IAP checks
  # their access before any request reaches the container. No load balancer.
  iap_enabled = true

  # One instance stays warm so nobody waits for a cold start (NFR-3);
  # 5 instances x 10 requests covers 25 concurrent users twice over (NFR-1).
  scaling {
    min_instance_count = var.min_instances
    max_instance_count = var.max_instances
  }

  template {
    service_account                  = google_service_account.api.email
    timeout                          = "60s"
    max_instance_request_concurrency = var.request_concurrency

    containers {
      image = var.image_uri

      ports {
        container_port = 8080
      }

      # The whole index is held in memory; 1 GiB leaves room for a few thousand sections (NFR-6).
      resources {
        limits = {
          cpu    = "1"
          memory = "1Gi"
        }
      }

      dynamic "env" {
        for_each = local.runtime_env
        content {
          name  = env.key
          value = env.value
        }
      }
    }
  }

  depends_on = [
    google_storage_bucket_iam_member.api_read,
    google_project_iam_member.api_vertex,
  ]
}

# IAP forwards signed-in requests as its own service agent, so that agent is the
# only principal granted Cloud Run Invoker. No allUsers/allAuthenticatedUsers.
resource "google_cloud_run_v2_service_iam_member" "iap_invoker" {
  project  = var.project_id
  location = google_cloud_run_v2_service.api.location
  name     = google_cloud_run_v2_service.api.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-iap.iam.gserviceaccount.com"
}

# Employees who may sign in through IAP and use the web page (NFR-7).
resource "google_iap_web_cloud_run_service_iam_member" "users" {
  for_each = toset(var.authorized_users)

  project                = var.project_id
  location               = google_cloud_run_v2_service.api.location
  cloud_run_service_name = google_cloud_run_v2_service.api.name
  role                   = "roles/iap.httpsResourceAccessor"
  member                 = each.value
}

# ---------- Index builder ----------

resource "google_cloud_run_v2_job" "indexer" {
  project             = var.project_id
  name                = var.job_name
  location            = var.region
  deletion_protection = false

  template {
    task_count  = 1
    parallelism = 1

    template {
      service_account = google_service_account.indexer.email
      max_retries     = 1
      # Hundreds of documents are embedded one section at a time.
      timeout = "3600s"

      containers {
        image   = var.image_uri
        command = ["python"]
        args    = ["-m", "app.indexer"]

        resources {
          limits = {
            cpu    = "1"
            memory = "1Gi"
          }
        }

        dynamic "env" {
          for_each = local.runtime_env
          content {
            name  = env.key
            value = env.value
          }
        }
      }
    }
  }

  depends_on = [
    google_storage_bucket_iam_member.indexer_read,
    google_storage_bucket_iam_member.indexer_write_processed,
    google_project_iam_member.indexer_vertex,
  ]
}

# Maintainers may still run the Job by hand, for example after an image update.
resource "google_cloud_run_v2_job_iam_member" "executor" {
  for_each = toset(var.authorized_job_executors)

  project  = var.project_id
  location = google_cloud_run_v2_job.indexer.location
  name     = google_cloud_run_v2_job.indexer.name
  role     = "roles/run.jobsExecutor"
  member   = each.value
}
