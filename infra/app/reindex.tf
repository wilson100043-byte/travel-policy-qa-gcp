# Rebuild the index automatically when the administration team uploads, replaces
# or removes a policy (FR-3, FR-5, NFR-5). Eventarc cannot start a Cloud Run Job directly, so the
# documented path is: Cloud Storage event -> Eventarc -> Workflows -> Job.

resource "google_service_account" "reindex" {
  project      = var.project_id
  account_id   = "travel-rag-reindex"
  display_name = "Travel policy Q&A reindex trigger and workflow"
}

resource "google_project_iam_member" "reindex_roles" {
  for_each = toset([
    "roles/eventarc.eventReceiver",
    "roles/workflows.invoker",
    "roles/logging.logWriter",
  ])

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.reindex.email}"
}

# The workflow may start this one Job and nothing else.
resource "google_cloud_run_v2_job_iam_member" "reindex_run_job" {
  project  = var.project_id
  location = google_cloud_run_v2_job.indexer.location
  name     = google_cloud_run_v2_job.indexer.name
  role     = "roles/run.jobsExecutor"
  member   = "serviceAccount:${google_service_account.reindex.email}"
}

# For an archived event the workflow checks whether a live raw/ policy with the
# same name remains (replaced) or not (removed). It may read raw/ objects only.
resource "google_storage_bucket_iam_member" "reindex_read_raw" {
  bucket = var.bucket_name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.reindex.email}"

  condition {
    title       = "read_raw_only"
    description = "Check whether an archived policy still has a live version"
    expression  = "resource.name.startsWith('projects/_/buckets/${var.bucket_name}/objects/raw/')"
  }
}

# Cloud Storage delivers its events to Eventarc through Pub/Sub.
data "google_storage_project_service_account" "gcs" {
  project = var.project_id
}

resource "google_project_iam_member" "gcs_pubsub_publisher" {
  project = var.project_id
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${data.google_storage_project_service_account.gcs.email_address}"
}

resource "google_workflows_workflow" "reindex" {
  project         = var.project_id
  name            = "travel-rag-reindex"
  region          = var.region
  description     = "Start the index Job when a policy file is uploaded to raw/"
  service_account = google_service_account.reindex.email
  source_contents = templatefile("${path.module}/reindex.workflow.yaml", {
    project_id  = var.project_id
    region      = var.region
    job_name    = google_cloud_run_v2_job.indexer.name
    bucket_name = var.bucket_name
  })
  deletion_protection = false

  depends_on = [
    google_cloud_run_v2_job_iam_member.reindex_run_job,
    google_storage_bucket_iam_member.reindex_read_raw,
  ]
}

# One trigger per event type: "finalized" for uploaded or replaced policies,
# "archived" for removed ones (the bucket keeps versions, so a delete archives).
resource "google_eventarc_trigger" "policy_changed" {
  for_each = {
    uploaded = "google.cloud.storage.object.v1.finalized"
    removed  = "google.cloud.storage.object.v1.archived"
  }

  project  = var.project_id
  name     = "travel-rag-policy-${each.key}"
  location = var.region

  matching_criteria {
    attribute = "type"
    value     = each.value
  }
  matching_criteria {
    attribute = "bucket"
    value     = var.bucket_name
  }

  destination {
    workflow = google_workflows_workflow.reindex.id
  }

  service_account = google_service_account.reindex.email

  depends_on = [
    google_project_iam_member.reindex_roles,
    google_project_iam_member.gcs_pubsub_publisher,
  ]
}
