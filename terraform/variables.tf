variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "image_tag" {
  description = "Container image tag to deploy. Defaults to latest for local/manual use; CI passes the git commit SHA."
  type        = string
  default     = "latest"
}

variable "artifact_retention_count" {
  description = "Number of most recent container image versions to always keep"
  type        = number
  default     = 10
}

variable "artifact_retention_days" {
  description = "Delete container images older than this many days (beyond the retained count)"
  type        = number
  default     = 30
}

variable "owner_email" {
  description = "Google account authorized to access anamnesis-ui via IAP"
  type        = string
}

variable "google_oauth_client_id" {
  description = "Google OAuth 2.0 Client ID used for Sign In With Google — not a secret, embedded in the frontend bundle too"
  type        = string
}
