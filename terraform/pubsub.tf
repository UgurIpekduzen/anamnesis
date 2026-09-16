resource "google_project_service" "pubsub" {
  service = "pubsub.googleapis.com"
}

resource "google_pubsub_topic" "fact_events" {
  name       = "fact-events"
  depends_on = [google_project_service.pubsub]
}

resource "google_pubsub_topic" "fact_events_dlq" {
  name       = "fact-events-dlq"
  depends_on = [google_project_service.pubsub]
}

resource "google_pubsub_subscription" "fact_events_sub" {
  name  = "fact-events-sub"
  topic = google_pubsub_topic.fact_events.id

  ack_deadline_seconds = 30

  retry_policy {
    minimum_backoff = "10s"
    maximum_backoff = "60s"
  }

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.fact_events_dlq.id
    max_delivery_attempts = 5
  }

  push_config {
    push_endpoint = google_cloud_run_v2_service.subscriber.uri
    oidc_token {
      service_account_email = google_service_account.agent_sa.email
    }
  }
}

resource "google_project_service" "serviceusage" {
  service = "serviceusage.googleapis.com"
}

resource "google_project_service" "cloudresourcemanager" {
  service    = "cloudresourcemanager.googleapis.com"
  depends_on = [google_project_service.serviceusage]
}

data "google_project" "current" {
  depends_on = [google_project_service.cloudresourcemanager]
}

resource "google_pubsub_topic_iam_member" "dlq_publisher" {
  topic  = google_pubsub_topic.fact_events_dlq.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_pubsub_subscription_iam_member" "dlq_subscriber" {
  subscription = google_pubsub_subscription.fact_events_sub.name
  role         = "roles/pubsub.subscriber"
  member       = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}

resource "google_pubsub_topic_iam_member" "agent_publish" {
  topic  = google_pubsub_topic.fact_events.name
  role   = "roles/pubsub.publisher"
  member = "serviceAccount:${google_service_account.agent_sa.email}"
}

resource "google_pubsub_subscription_iam_member" "agent_subscribe" {
  subscription = google_pubsub_subscription.fact_events_sub.name
  role         = "roles/pubsub.subscriber"
  member       = "serviceAccount:${google_service_account.agent_sa.email}"
}

resource "google_service_account_iam_member" "pubsub_can_mint_agent_tokens" {
  service_account_id = google_service_account.agent_sa.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:service-${data.google_project.current.number}@gcp-sa-pubsub.iam.gserviceaccount.com"
}
