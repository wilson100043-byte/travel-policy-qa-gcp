terraform {
  required_version = ">= 1.6.0"

  # State lives in a versioned Cloud Storage bucket, not on one person's laptop:
  # it is shared, locked during apply, and recoverable. The bucket and prefix
  # are passed at init time; see docs/DEPLOYMENT.md.
  backend "gcs" {}

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 7.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
