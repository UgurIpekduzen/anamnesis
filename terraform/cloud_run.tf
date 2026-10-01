resource "google_project_service" "run" {
  service = "run.googleapis.com"
}

locals {
  image = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.app_images.repository_id}/app:${var.image_tag}"
}

resource "google_cloud_run_v2_service" "ui" {
  name       = "anamnesis-app"
  location   = var.region
  depends_on = [google_project_service.run]

  timeouts {
    create = "5m"
    update = "5m"
  }

  template {
    service_account = google_service_account.agent_sa.email

    # Capped at one instance: the API caches an ADK Runner and a session per
    # (owner_uid, tenant_id) in process memory (see api/runner.py). A second
    # instance would keep its own, separate cache, so a user's conversation
    # could silently reset depending on which instance handled a request.
    scaling {
      max_instance_count = 1
    }

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
        name  = "GOOGLE_OAUTH_CLIENT_ID"
        value = var.google_oauth_client_id
      }
      env {
        name  = "ALLOWED_EMAILS"
        value = var.owner_email
      }
      env {
        name = "GITHUB_TOKEN_ENCRYPTION_KEY"
        value_source {
          secret_key_ref {
            secret  = google_secret_manager_secret.github_token_encryption_key.secret_id
            version = "latest"
          }
        }
      }
      env {
        name  = "GITHUB_POLLER_SERVICE_ACCOUNT_EMAIL"
        value = google_service_account.github_poller.email
      }
      env {
        name  = "GITHUB_POLLER_AUDIENCE"
        value = local.github_poller_audience
      }
      env {
        name  = "GLOBAL_DAILY_MESSAGE_LIMIT"
        value = tostring(var.global_daily_message_limit)
      }
    }

    max_instance_request_concurrency = 40
  }
}

# Public at the network level — actual authorization (Google Sign-In +
# the ALLOWED_EMAILS allowlist above) is enforced inside the app itself,
# not by IAM. See README.md's "Access control" section for why.
resource "google_cloud_run_v2_service_iam_member" "app_public" {
  name     = google_cloud_run_v2_service.ui.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "allUsers"
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

    # Capped for cost, not correctness — unlike the ui service above, this
    # one holds no per-request in-memory state that a second instance
    # would fragment.
    scaling {
      max_instance_count = 1
    }

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

# Not public: the Pub/Sub push subscription (pubsub.tf) authenticates as
# agent_sa with an OIDC token, so only that identity may invoke it.
resource "google_cloud_run_v2_service_iam_member" "subscriber_pubsub_invoker" {
  name     = google_cloud_run_v2_service.subscriber.name
  location = var.region
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.agent_sa.email}"
}
