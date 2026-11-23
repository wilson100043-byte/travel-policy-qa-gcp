variable "project_id" {
  description = "Existing Google Cloud project ID inside the company's organization."
  type        = string
}

variable "region" {
  description = "Must match the bootstrap region. Taiwan keeps internal documents in the country (NFR-8)."
  type        = string
  default     = "asia-east1"
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
  description = "Cloud Run web/API service name."
  type        = string
  default     = "travel-policy-rag"
}

variable "job_name" {
  description = "Cloud Run indexing job name."
  type        = string
  default     = "travel-policy-rag-index"
}

# ---------- AI ----------

variable "ai_mode" {
  description = "vertex (default) answers with Vertex AI; offline uses local TF-IDF retrieval and makes no AI calls."
  type        = string
  default     = "vertex"

  validation {
    condition     = contains(["offline", "vertex"], var.ai_mode)
    error_message = "ai_mode must be offline or vertex."
  }
}

# Google's docs confirm pay-as-you-go use of gemini-3.5-flash-lite on the "us"
# multi-region, and of gemini-embedding-001 on us-central1. Neither model is
# listed for Taiwan, so AI inference is processed in the United States while
# documents, the index and compute stay in asia-east1 (see REQUIREMENTS NFR-8).
variable "vertex_location" {
  description = "Vertex AI location for the generation model: a region, or the us / eu multi-region."
  type        = string
  default     = "us"
}

variable "vertex_embedding_location" {
  description = "Vertex AI location for the embedding model. gemini-embedding-001 does not support the us / eu multi-region endpoints."
  type        = string
  default     = "us-central1"
}

variable "generation_model" {
  description = "Vertex AI Gemini model for query rewriting and answers."
  type        = string
  default     = "gemini-3.5-flash-lite"
}

variable "embedding_model" {
  description = "Vertex AI embedding model for documents and questions."
  type        = string
  default     = "gemini-embedding-001"
}

# ---------- Capacity ----------

variable "min_instances" {
  description = "Instances kept warm so no user waits for a cold start (NFR-3)."
  type        = number
  default     = 1
}

variable "max_instances" {
  description = "Upper bound on instances; with request_concurrency it sets peak capacity (NFR-1)."
  type        = number
  default     = 5
}

variable "request_concurrency" {
  description = "Requests one instance handles at once. Requests mostly wait on Vertex AI, so 10 is safe for 1 vCPU."
  type        = number
  default     = 10
}

# ---------- People ----------

variable "authorized_users" {
  description = "Employees allowed to sign in through IAP, such as group:all-staff@example.com. Empty means no one is granted by this module."
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for member in var.authorized_users : can(regex("^(user|group|serviceAccount):[^[:space:]]+$", member))])
    error_message = "authorized_users must contain explicit user:, group:, or serviceAccount: principals."
  }
}

variable "policy_admins" {
  description = "Administration team allowed to upload policies to raw/, such as group:admin-dept@example.com (NFR-13)."
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for member in var.policy_admins : can(regex("^(user|group):[^[:space:]]+$", member))])
    error_message = "policy_admins must contain explicit user: or group: principals."
  }
}

variable "authorized_job_executors" {
  description = "Maintainers allowed to run the indexing job by hand."
  type        = list(string)
  default     = []

  validation {
    condition     = alltrue([for member in var.authorized_job_executors : can(regex("^(user|group|serviceAccount):[^[:space:]]+$", member))])
    error_message = "authorized_job_executors must contain explicit user:, group:, or serviceAccount: principals."
  }
}

variable "alert_email" {
  description = "Email address that receives monitoring alerts (NFR-10). Empty creates the alert policies without a notification channel."
  type        = string
  default     = ""
}
