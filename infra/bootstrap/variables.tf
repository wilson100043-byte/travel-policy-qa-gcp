variable "project_id" {
  description = "Existing Google Cloud project ID inside the company's organization. Terraform does not create a billing account or a project."
  type        = string
}

variable "region" {
  description = "Region for storage, images and compute. Taiwan keeps internal documents in the country (NFR-8)."
  type        = string
  default     = "asia-east1"
}

variable "bucket_name" {
  description = "Globally unique private Cloud Storage bucket name for policies (raw/) and the index (processed/)."
  type        = string

  validation {
    condition     = length(var.bucket_name) >= 3 && length(var.bucket_name) <= 63 && can(regex("^[a-z0-9][a-z0-9._-]*[a-z0-9]$", var.bucket_name))
    error_message = "bucket_name must be a valid lowercase Cloud Storage bucket name (3-63 characters)."
  }
}

variable "policy_versions_to_keep" {
  description = "How many earlier versions of each object to keep for restoring a wrongly edited policy."
  type        = number
  default     = 10
}

variable "repository_id" {
  description = "Artifact Registry Docker repository name."
  type        = string
  default     = "travel-policy-rag"
}

variable "cloud_build_service_account_email" {
  description = "Actual Cloud Build execution identity. Set this after checking the project; when blank, no Artifact Registry writer grant is made."
  type        = string
  default     = ""
}
