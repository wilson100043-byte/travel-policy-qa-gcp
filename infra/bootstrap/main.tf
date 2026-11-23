locals {
  required_apis = toset([
    "aiplatform.googleapis.com",
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "eventarc.googleapis.com",
    "iam.googleapis.com",
    "iap.googleapis.com",
    "logging.googleapis.com",
    "monitoring.googleapis.com",
    "pubsub.googleapis.com",
    "run.googleapis.com",
    "storage.googleapis.com",
    "workflows.googleapis.com",
  ])
}

resource "google_project_service" "required" {
  for_each = local.required_apis

  project            = var.project_id
  service            = each.key
  disable_on_destroy = false
}

# raw/ holds the policies uploaded by the administration team; processed/ holds
# the index written by the Cloud Run Job. Terraform does not upload policies, so
# a later apply never overwrites what the team published (NFR-13).
resource "google_storage_bucket" "documents" {
  name                        = var.bucket_name
  project                     = var.project_id
  location                    = var.region
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  # Keep earlier versions so a wrongly edited policy can be restored (NFR-12).
  versioning {
    enabled = true
  }

  lifecycle_rule {
    condition {
      with_state         = "ARCHIVED"
      num_newer_versions = var.policy_versions_to_keep
    }
    action {
      type = "Delete"
    }
  }

  depends_on = [google_project_service.required]
}

resource "google_artifact_registry_repository" "images" {
  project       = var.project_id
  location      = var.region
  repository_id = var.repository_id
  description   = "Travel policy Q&A service and indexing job image"
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
