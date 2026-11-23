locals {
  gemini_enabled = var.ai_mode == "gemini"
  secret_path    = "projects/${var.project_id}/secrets/${var.secret_id}"
}

resource "google_service_account" "api" {
  project      = var.project_id
  account_id   = "travel-rag-api"
  display_name = "Travel policy RAG API runtime"
}

resource "google_service_account" "indexer" {
  project      = var.project_id
  account_id   = "travel-rag-indexer"
  display_name = "Travel policy RAG indexing job runtime"
}

# Both workloads can read the documents/index in this one private bucket.
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

# The Job may replace only processed/ objects. Its separate viewer grant above
# allows listing raw/; objectCreator alone cannot overwrite the existing index.
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

resource "google_secret_manager_secret_iam_member" "api_secret_access" {
  count = local.gemini_enabled ? 1 : 0

  project   = var.project_id
  secret_id = local.secret_path
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.api.email}"
}

resource "google_secret_manager_secret_iam_member" "indexer_secret_access" {
  count = local.gemini_enabled ? 1 : 0

  project   = var.project_id
  secret_id = local.secret_path
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.indexer.email}"
}

data "google_project" "current" {
  project_id = var.project_id
}

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

  scaling {
    min_instance_count = 0
    max_instance_count = 1
  }

  template {
    service_account                  = google_service_account.api.email
    timeout                          = "60s"
    max_instance_request_concurrency = 4

    containers {
      image = var.image_uri

      ports {
        container_port = 8080
      }

      resources {
        limits = {
          cpu    = "1"
          memory = "512Mi"
        }
      }

      env {
        name  = "STORAGE_MODE"
        value = "gcs"
      }
      env {
        name  = "GCS_BUCKET"
        value = var.bucket_name
      }
      env {
        name  = "GCS_RAW_PREFIX"
        value = "raw/"
      }
      env {
        name  = "GCS_PROCESSED_OBJECT"
        value = "processed/index.json"
      }
      env {
        name  = "AI_MODE"
        value = var.ai_mode
      }
      env {
        name  = "GEMINI_FREE_TIER_CONFIRMED"
        value = var.gemini_free_tier_confirmed ? "1" : "0"
      }

      dynamic "env" {
        for_each = local.gemini_enabled ? [1] : []
        content {
          name = "GEMINI_API_KEY"
          value_source {
            secret_key_ref {
              secret  = var.secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }

  lifecycle {
    precondition {
      condition     = !local.gemini_enabled || var.gemini_free_tier_confirmed
      error_message = "Gemini mode requires an explicit Free Tier confirmation. This does not guarantee zero Google Cloud charges."
    }
  }

  depends_on = [
    google_storage_bucket_iam_member.api_read,
    google_secret_manager_secret_iam_member.api_secret_access,
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

# People who may sign in through IAP and use the web page.
resource "google_iap_web_cloud_run_service_iam_member" "users" {
  for_each = toset(var.authorized_users)

  project                = var.project_id
  location               = google_cloud_run_v2_service.api.location
  cloud_run_service_name = google_cloud_run_v2_service.api.name
  role                   = "roles/iap.httpsResourceAccessor"
  member                 = each.value
}

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
      max_retries     = 0
      timeout         = "600s"

      containers {
        image   = var.image_uri
        command = ["python"]
        args    = ["-m", "app.indexer"]

        resources {
          limits = {
            cpu    = "1"
            memory = "512Mi"
          }
        }

        env {
          name  = "STORAGE_MODE"
          value = "gcs"
        }
        env {
          name  = "GCS_BUCKET"
          value = var.bucket_name
        }
        env {
          name  = "GCS_RAW_PREFIX"
          value = "raw/"
        }
        env {
          name  = "GCS_PROCESSED_OBJECT"
          value = "processed/index.json"
        }
        env {
          name  = "AI_MODE"
          value = var.ai_mode
        }
        env {
          name  = "GEMINI_FREE_TIER_CONFIRMED"
          value = var.gemini_free_tier_confirmed ? "1" : "0"
        }

        dynamic "env" {
          for_each = local.gemini_enabled ? [1] : []
          content {
            name = "GEMINI_API_KEY"
            value_source {
              secret_key_ref {
                secret  = var.secret_id
                version = "latest"
              }
            }
          }
        }
      }
    }
  }

  lifecycle {
    precondition {
      condition     = !local.gemini_enabled || var.gemini_free_tier_confirmed
      error_message = "Gemini mode requires an explicit Free Tier confirmation. This does not guarantee zero Google Cloud charges."
    }
  }

  depends_on = [
    google_storage_bucket_iam_member.indexer_read,
    google_storage_bucket_iam_member.indexer_write_processed,
    google_secret_manager_secret_iam_member.indexer_secret_access,
  ]
}

resource "google_cloud_run_v2_job_iam_member" "executor" {
  for_each = toset(var.authorized_job_executors)

  project  = var.project_id
  location = google_cloud_run_v2_job.indexer.location
  name     = google_cloud_run_v2_job.indexer.name
  role     = "roles/run.jobsExecutor"
  member   = each.value
}
