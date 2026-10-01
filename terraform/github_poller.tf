resource "google_project_service" "cloudscheduler" {
  service = "cloudscheduler.googleapis.com"
}

# A distinct identity from agent_sa, used only to call the poll endpoint —
# api/internal_auth.py checks the caller against this exact account, a
# separate, narrower trust boundary from the user-facing allowlist in
# api/deps.py.
resource "google_service_account" "github_poller" {
  account_id = "anamnesis-github-poller"
}

resource "google_cloud_run_v2_service_iam_member" "github_poller_invoker" {
  name     = google_cloud_run_v2_service.ui.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.github_poller.email}"
}

resource "google_cloud_scheduler_job" "github_poller" {
  name       = "anamnesis-github-poller"
  schedule   = "0 */2 * * *" # every 2 hours — change to whatever frequency you want
  region     = var.region
  depends_on = [google_project_service.cloudscheduler]

  http_target {
    uri         = "${google_cloud_run_v2_service.ui.uri}/internal/poll-github"
    http_method = "POST"

    oidc_token {
      service_account_email = google_service_account.github_poller.email
      audience              = local.github_poller_audience
    }
  }
}

locals {
  github_poller_audience = "anamnesis-github-poller"
}
