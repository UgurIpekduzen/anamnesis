resource "google_project_service" "artifactregistry" {
  service = "artifactregistry.googleapis.com"
}

resource "google_artifact_registry_repository" "app_images" {
  repository_id = "anamnesis"
  format        = "DOCKER"
  location      = var.region
  depends_on    = [google_project_service.artifactregistry]
}
