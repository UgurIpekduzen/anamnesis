resource "google_project_service" "secretmanager" {
  service = "secretmanager.googleapis.com"
}

resource "google_secret_manager_secret" "github_token_encryption_key" {
  secret_id  = "github-token-encryption-key"
  depends_on = [google_project_service.secretmanager]

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_iam_member" "github_encryption_key_access" {
  secret_id = google_secret_manager_secret.github_token_encryption_key.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.agent_sa.email}"
}
