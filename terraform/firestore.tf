resource "google_project_service" "firestore" {
  service = "firestore.googleapis.com"
}

resource "google_firestore_database" "default" {
  name        = "(default)"
  location_id = var.region
  type        = "FIRESTORE_NATIVE"

  depends_on = [google_project_service.firestore]
}

resource "google_firestore_field" "chat_turns_ttl" {
  collection = "chat_turns"
  field      = "expire_at"

  ttl_config {}

  depends_on = [google_firestore_database.default]
}
