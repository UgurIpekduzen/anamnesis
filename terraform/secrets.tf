resource "google_project_service" "secretmanager" {
  service = "secretmanager.googleapis.com"
}

resource "google_secret_manager_secret" "jira_api_token" {
  secret_id  = "jira-api-token"
  depends_on = [google_project_service.secretmanager]

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_iam_member" "agent_access" {
  secret_id = google_secret_manager_secret.jira_api_token.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agent_sa.email}"
}
