output "bucket_name" {
  value       = google_storage_bucket.documents.name
  description = "Private bucket for raw policies and the processed index."
}

output "repository_path" {
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.images.repository_id}"
  description = "Prefix for the Docker image URI."
}
