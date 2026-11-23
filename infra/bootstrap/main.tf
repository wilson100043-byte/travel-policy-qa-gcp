locals {
  required_apis = toset([
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "iam.googleapis.com",
    "iap.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "storage.googleapis.com",
  ])

  policy_dir   = abspath("${path.module}/../../policy_docs")
  policy_files = fileset(local.policy_dir, "*.md")
}

resource "google_project_service" "required" {
  for_each = local.required_apis

  project            = var.project_id
  service            = each.key
  disable_on_destroy = false
}

resource "google_storage_bucket" "documents" {
  name                        = var.bucket_name
  project                     = var.project_id
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  # Avoid retaining replaced demo objects for seven extra days by default.
  soft_delete_policy {
    retention_duration_seconds = 0
  }

  depends_on = [google_project_service.required]
}

resource "google_storage_bucket_object" "raw_policy" {
  for_each = local.policy_files

  name         = "raw/${each.value}"
  bucket       = google_storage_bucket.documents.name
  source       = "${local.policy_dir}/${each.value}"
  content_type = "text/markdown; charset=utf-8"
  # Reupload a changed document, including when its filename stays the same.
  source_md5hash = filemd5("${local.policy_dir}/${each.value}")
}

resource "google_artifact_registry_repository" "images" {
  project       = var.project_id
  location      = var.region
  repository_id = var.repository_id
  description   = "RAG demo service and indexing job image"
  format        = "DOCKER"

  docker_config {
    immutable_tags = true
  }

  depends_on = [google_project_service.required]
}

# Cloud Build's execution identity varies by project configuration. Grant
# writer to the identity the user verified, rather than assuming an email.
resource "google_artifact_registry_repository_iam_member" "cloud_build_writer" {
  count = var.cloud_build_service_account_email == "" ? 0 : 1

  project    = google_artifact_registry_repository.images.project
  location   = google_artifact_registry_repository.images.location
  repository = google_artifact_registry_repository.images.name
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${var.cloud_build_service_account_email}"
}

resource "google_secret_manager_secret" "gemini_api_key" {
  project   = var.project_id
  secret_id = var.secret_id

  replication {
    user_managed {
      replicas {
        location = var.region
      }
    }
  }

  depends_on = [google_project_service.required]
}

# No google_secret_manager_secret_version: the key must never enter Terraform state.
