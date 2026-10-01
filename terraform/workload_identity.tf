# Two GitHub Actions service accounts below, with deliberately different
# scopes: github_actions (deploy-capable, main-branch only) and
# github_actions_plan (read-only + securityReviewer, any branch/PR) — a PR
# workflow needs to run `terraform plan` without ever being able to touch
# real infrastructure, so it gets the narrower identity.
resource "google_iam_workload_identity_pool" "github_actions" {
  workload_identity_pool_id = "github-actions-pool"
  display_name              = "GitHub Actions Pool"
}

resource "google_iam_workload_identity_pool_provider" "github_actions" {
  workload_identity_pool_id          = google_iam_workload_identity_pool.github_actions.workload_identity_pool_id
  workload_identity_pool_provider_id = "github-actions-provider"
  display_name                       = "GitHub Actions Provider"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }

  # Only THIS repo's workflows can use this provider — without this,
  # any GitHub Actions workflow anywhere could request the identity.
  attribute_condition = "assertion.repository == \"UgurIpekduzen/anamnesis\""
}

resource "google_service_account" "github_actions" {
  account_id   = "github-actions-ci"
  display_name = "GitHub Actions CI/CD"
}

# Scoped to the main branch specifically (attribute.ref), not the whole
# repo — only a push to main (the deploy workflow) may assume this identity.
resource "google_service_account_iam_member" "github_actions_wif" {
  service_account_id = google_service_account.github_actions.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github_actions.name}/attribute.ref/refs/heads/main"
}

resource "google_project_iam_member" "github_actions_viewer" {
  project = var.project_id
  role    = "roles/viewer"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

resource "google_storage_bucket_iam_member" "github_actions_tfstate" {
  bucket = "anamnesis-tfstate-b7db2ae1"
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.github_actions.email}"
}

resource "google_service_account" "github_actions_plan" {
  account_id   = "github-actions-plan"
  display_name = "GitHub Actions PR plan (read-only)"
}

resource "google_project_iam_member" "github_actions_plan_viewer" {
  project = var.project_id
  role    = "roles/viewer"
  member  = "serviceAccount:${google_service_account.github_actions_plan.email}"
}

resource "google_project_iam_member" "github_actions_plan_security_reviewer" {
  project = var.project_id
  role    = "roles/iam.securityReviewer"
  member  = "serviceAccount:${google_service_account.github_actions_plan.email}"
}

resource "google_storage_bucket_iam_member" "github_actions_plan_tfstate" {
  bucket = "anamnesis-tfstate-b7db2ae1"
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.github_actions_plan.email}"
}

# Scoped to the whole repo (attribute.repository), not just main — any
# branch or PR workflow may assume this identity, since it's read-only.
resource "google_service_account_iam_member" "github_actions_plan_wif" {
  service_account_id = google_service_account.github_actions_plan.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github_actions.name}/attribute.repository/UgurIpekduzen/anamnesis"
}

resource "google_project_iam_member" "github_actions_security_reviewer" {
  project = var.project_id
  role    = "roles/iam.securityReviewer"
  member  = "serviceAccount:${google_service_account.github_actions.email}"
}

resource "google_artifact_registry_repository_iam_member" "github_actions_image_push" {
  repository = google_artifact_registry_repository.app_images.name
  location   = google_artifact_registry_repository.app_images.location
  role       = "roles/artifactregistry.writer"
  member     = "serviceAccount:${google_service_account.github_actions.email}"
}

resource "google_cloud_run_v2_service_iam_member" "github_actions_ui_deploy" {
  name     = google_cloud_run_v2_service.ui.name
  location = var.region
  role     = "roles/run.developer"
  member   = "serviceAccount:${google_service_account.github_actions.email}"
}

resource "google_cloud_run_v2_service_iam_member" "github_actions_subscriber_deploy" {
  name     = google_cloud_run_v2_service.subscriber.name
  location = var.region
  role     = "roles/run.developer"
  member   = "serviceAccount:${google_service_account.github_actions.email}"
}

# Deploying a Cloud Run revision that runs as agent_sa (cloud_run.tf)
# requires this grant on the deploying identity, not just run.developer above.
resource "google_service_account_iam_member" "github_actions_act_as_agent" {
  service_account_id = google_service_account.agent_sa.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.github_actions.email}"
}
