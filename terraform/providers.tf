terraform {
  # Matches the CLI version pinned everywhere else this runs: the
  # `terraform` Docker service (docker-compose.yml), and both GitHub
  # Actions workflows (.github/workflows/*.yml) — a local run on a
  # different version now fails loudly instead of silently drifting.
  required_version = "~> 1.9"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}