output "service_name" {
  value       = google_cloud_run_v2_service.api.name
  description = "Private Cloud Run service protected by IAP."
}

output "service_url" {
  value       = google_cloud_run_v2_service.api.uri
  description = "Open in a browser and sign in with a Google account listed in authorized_users."
}

output "index_job_name" {
  value       = google_cloud_run_v2_job.indexer.name
  description = "Run manually after uploading policies or changing the image."
}
