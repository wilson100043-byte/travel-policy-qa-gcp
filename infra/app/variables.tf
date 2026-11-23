variable "project_id" {
  description = "Existing Google Cloud project ID."
  type        = string
}

variable "region" {
  description = "Must match the bootstrap region."
  type        = string
  default     = "us-central1"
}

variable "bucket_name" {
  description = "Private document bucket created by bootstrap."
  type        = string
}

variable "image_uri" {
  description = "Full Artifact Registry image URI produced by Cloud Build, preferably with an immutable tag or digest."
  type        = string

  validation {
    condition     = can(regex("-docker\\.pkg\\.dev/.+/.+/.+(:[^/]+|@sha256:[a-f0-9]{64})$", var.image_uri))
    error_message = "image_uri must be a full Artifact Registry Docker image URI with a tag or sha256 digest."
  }
}

variable "service_name" {
  description = "Private Cloud Run web/API service name."
  type        = string
  default     = "travel-policy-rag"
}

variable "job_name" {
  description = "Manual Cloud Run indexing job name."
  type        = string
  default     = "travel-policy-rag-index"
}

variable "secret_id" {
  description = "Existing empty secret created by bootstrap; add a version outside Terraform before enabling Gemini mode."
  type        = string
  default     = "travel-rag-gemini-api-key"
}

variable "ai_mode" {
  description = "Defaults to offline to avoid remote AI calls. Set gemini only after confirming an AI Studio Free Tier project."
  type        = string
  default     = "offline"

  validation {
    condition     = contains(["offline", "gemini"], var.ai_mode)
    error_message = "ai_mode must be offline or gemini."
  }
}

variable "gemini_free_tier_confirmed" {
  description = "Explicit acknowledgement for the application's own remote-AI guard; Terraform cannot verify billing status."
  type        = bool
  default     = false
}

variable "authorized_users" {
  description = "Exact principals allowed to sign in through IAP and use the web page, such as user:you@example.com or group:team@example.com. Empty means no one is granted by this module."
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for member in var.authorized_users : can(regex("^(user|group|serviceAccount):[^[:space:]]+$", member))])
    error_message = "authorized_users must contain explicit user:, group:, or serviceAccount: principals."
  }
}

variable "authorized_job_executors" {
  description = "Exact IAM principals allowed to run the manual indexing job."
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for member in var.authorized_job_executors : can(regex("^(user|group|serviceAccount):[^[:space:]]+$", member))])
    error_message = "authorized_job_executors must contain explicit user:, group:, or serviceAccount: principals."
  }
}
