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

resource "google_project_iam_member" "agent_vertexai" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.agent_sa.email}"
}
