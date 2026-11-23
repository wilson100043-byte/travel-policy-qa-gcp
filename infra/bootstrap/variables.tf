variable "project_id" {
  description = "Existing Google Cloud project ID. Terraform does not create a billing account or a project."
  type        = string
}

variable "region" {
  description = "Region for the demonstration resources."
  type        = string
  default     = "us-central1"
}

variable "bucket_name" {
  description = "Globally unique private Cloud Storage bucket name, in us-central1."
  type        = string

  validation {
    condition     = length(var.bucket_name) >= 3 && length(var.bucket_name) <= 63 && can(regex("^[a-z0-9][a-z0-9._-]*[a-z0-9]$", var.bucket_name))
    error_message = "bucket_name must be a valid lowercase Cloud Storage bucket name (3-63 characters)."
  }
}

variable "repository_id" {
  description = "Artifact Registry Docker repository name."
  type        = string
  default     = "travel-policy-rag"
}

variable "secret_id" {
  description = "Name of the empty Secret Manager secret; the secret value is added outside Terraform."
  type        = string
  default     = "travel-rag-gemini-api-key"
}

variable "cloud_build_service_account_email" {
  description = "Actual Cloud Build execution identity. Set this after checking the project; when blank, no Artifact Registry writer grant is made."
  type        = string
  default     = ""
}
