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
