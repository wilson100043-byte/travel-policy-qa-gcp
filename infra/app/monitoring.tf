# Alerts for the system administrator (NFR-10) and access audit logs (NFR-11).

resource "google_monitoring_notification_channel" "admin_email" {
  count = var.alert_email == "" ? 0 : 1

  project      = var.project_id
  display_name = "Travel policy Q&A administrator"
  type         = "email"
  labels = {
    email_address = var.alert_email
  }
}

locals {
  notification_channels = google_monitoring_notification_channel.admin_email[*].id
}

# Cloud Monitoring has no 90th-percentile aligner, so the 95th percentile is
# checked against the 8-second target (NFR-2); this is slightly stricter.
resource "google_monitoring_alert_policy" "slow_answers" {
  project      = var.project_id
  display_name = "Travel policy Q&A: answers slower than 8 s"
  combiner     = "OR"

  conditions {
    display_name = "p95 request latency above 8 s for 5 minutes"
    condition_threshold {
      filter          = "resource.type = \"cloud_run_revision\" AND resource.labels.service_name = \"${var.service_name}\" AND metric.type = \"run.googleapis.com/request_latencies\""
      comparison      = "COMPARISON_GT"
      threshold_value = 8000
      duration        = "300s"
      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_PERCENTILE_95"
        cross_series_reducer = "REDUCE_MAX"
      }
    }
  }

  notification_channels = local.notification_channels
}

resource "google_monitoring_alert_policy" "server_errors" {
  project      = var.project_id
  display_name = "Travel policy Q&A: server errors"
  combiner     = "OR"

  conditions {
    display_name = "More than 5 server errors in 5 minutes"
    condition_threshold {
      filter          = "resource.type = \"cloud_run_revision\" AND resource.labels.service_name = \"${var.service_name}\" AND metric.type = \"run.googleapis.com/request_count\" AND metric.labels.response_code_class = \"5xx\""
      comparison      = "COMPARISON_GT"
      threshold_value = 5
      duration        = "0s"
      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_SUM"
        cross_series_reducer = "REDUCE_SUM"
      }
    }
  }

  notification_channels = local.notification_channels
}

resource "google_monitoring_alert_policy" "index_job_failed" {
  project      = var.project_id
  display_name = "Travel policy Q&A: index rebuild failed"
  combiner     = "OR"

  conditions {
    display_name = "Index Job execution failed"
    condition_threshold {
      filter          = "resource.type = \"cloud_run_job\" AND resource.labels.job_name = \"${var.job_name}\" AND metric.type = \"run.googleapis.com/job/completed_execution_count\" AND metric.labels.result = \"failed\""
      comparison      = "COMPARISON_GT"
      threshold_value = 0
      duration        = "0s"
      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_SUM"
        cross_series_reducer = "REDUCE_SUM"
      }
    }
  }

  notification_channels = local.notification_channels
}

# Record who reached the page through IAP and when. The application itself does
# not log question text, and Cloud Run request logs contain only the URL path.
resource "google_project_iam_audit_config" "iap_access" {
  project = var.project_id
  service = "iap.googleapis.com"

  audit_log_config {
    log_type = "DATA_READ"
  }
}
