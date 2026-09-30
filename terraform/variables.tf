variable "project_id" {
  description = "The GCP project everything in this configuration is created in."
  type        = string
}

variable "region" {
  description = "The GCP region for regional resources (Cloud Run, Artifact Registry, Firestore)."
  type        = string
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
  description = "The initial allowlisted Google account, with the owner/admin role — set from ALLOWED_EMAILS on the Cloud Run service; the app enforces its own sign-in and allowlist, not GCP IAM/IAP."
  type        = string
}

variable "google_oauth_client_id" {
  description = "Google OAuth 2.0 Client ID used for Sign In With Google — not a secret, embedded in the frontend bundle too"
  type        = string
}

variable "global_daily_message_limit" {
  description = "Shared daily message ceiling across every allowed user combined, on top of each user's own. At ~$0.005/message, 100 keeps the worst case (every day maxed out, all month) around $15/month."
  type        = number
  default     = 100
}
