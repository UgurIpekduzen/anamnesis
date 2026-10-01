resource "google_project_service" "firestore" {
  service = "firestore.googleapis.com"
}

resource "google_firestore_database" "default" {
  name                              = "(default)"
  location_id                       = var.region
  type                              = "FIRESTORE_NATIVE"
  point_in_time_recovery_enablement = "POINT_IN_TIME_RECOVERY_ENABLED"
  delete_protection_state           = "DELETE_PROTECTION_ENABLED"
  depends_on                        = [google_project_service.firestore]
}

# Firestore's built-in TTL deletes a chat_turns document once its own
# expire_at timestamp passes, without a scheduled job or manual cleanup.
resource "google_firestore_field" "chat_turns_ttl" {
  collection = "chat_turns"
  field      = "expire_at"

  ttl_config {}

  depends_on = [google_firestore_database.default]
}
