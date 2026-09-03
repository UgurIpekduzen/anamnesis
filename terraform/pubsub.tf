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

  dead_letter_policy {
    dead_letter_topic     = google_pubsub_topic.fact_events_dlq.id
    max_delivery_attempts = 5
  }
}

data "google_project" "current" {}

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
