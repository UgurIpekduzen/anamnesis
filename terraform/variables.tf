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
