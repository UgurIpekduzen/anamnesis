resource "google_project_service" "run" {
  service = "run.googleapis.com"
}

locals {
  image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.app_images.repository_id}/streamlit-app:${var.image_tag}"
}

resource "google_cloud_run_v2_service" "ui" {
  name       = "anamnesis-ui"
  location   = var.region
  depends_on = [google_project_service.run]

  timeouts {
    create = "5m"
    update = "5m"
  }

  template {
    service_account = google_service_account.agent_sa.email
    containers {
      image = local.image

      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "GOOGLE_GENAI_USE_ENTERPRISE"
        value = "1"
      }
      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = var.project_id
      }
      env {
        name  = "GOOGLE_CLOUD_LOCATION"
        value = var.region
      }
      env {
        name  = "JIRA_BASE_URL"
        value = var.jira_base_url
      }
      env {
        name  = "JIRA_EMAIL"
        value = var.jira_email
      }
      env {
        name = "JIRA_API_TOKEN"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.jira_api_token.secret_id
            version = "latest"
          }
        }
      }
    }
  }
}

resource "google_cloud_run_v2_service_iam_member" "ui_owner" {
  name     = google_cloud_run_v2_service.ui.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "user:${var.owner_email}"
}

resource "google_cloud_run_v2_service" "subscriber" {
  name       = "anamnesis-subscriber"
  location   = var.region
  depends_on = [google_project_service.run]

  timeouts {
    create = "5m"
    update = "5m"
  }

  template {
    service_account = google_service_account.agent_sa.email
    containers {
      image   = local.image
      command = ["python", "-m", "src.subscriber"]

      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
    }
  }
}

resource "google_cloud_run_v2_service_iam_member" "subscriber_pubsub_invoker" {
  name     = google_cloud_run_v2_service.subscriber.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.agent_sa.email}"
}
