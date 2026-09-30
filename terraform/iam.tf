# One service account for every user's agent turns and Pub/Sub write path —
# not per-user; data isolation between users is enforced in the app
# (owner_uid scoping), not by separate GCP identities.
resource "google_service_account" "agent_sa" {
  account_id = "anamnesis-agent"
}

resource "google_project_iam_member" "agent_firestore" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.agent_sa.email}"
}

# Every other API this project uses is enabled here in Terraform (see
# firestore.tf, pubsub.tf, cloud_run.tf...) — Vertex AI is no exception,
# so a fresh `terraform apply` never needs a separate manual
# `gcloud services enable` step the README would otherwise have to
# document and someone could forget.
resource "google_project_service" "aiplatform" {
  service = "aiplatform.googleapis.com"
}

resource "google_project_iam_member" "agent_vertexai" {
  project    = var.project_id
  role       = "roles/aiplatform.user"
  member     = "serviceAccount:${google_service_account.agent_sa.email}"
  depends_on = [google_project_service.aiplatform]
}
