variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "jira_base_url" {
  type        = string
  description = "Jira Cloud site URL, e.g. https://yourorg.atlassian.net"
}

variable "jira_email" {
  type        = string
  description = "Email associated with the Jira API token"
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

