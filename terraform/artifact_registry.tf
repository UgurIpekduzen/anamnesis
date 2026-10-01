resource "google_project_service" "artifactregistry" {
  service = "artifactregistry.googleapis.com"
}

resource "google_artifact_registry_repository" "app_images" {
  repository_id = "anamnesis"
  format        = "DOCKER"
  location      = var.region
  depends_on    = [google_project_service.artifactregistry]

  # Two policies, evaluated together: an image is deleted only once it's
  # both past the keep-recent count and older than the delete-old cutoff —
  # so a burst of deploys doesn't get pruned down to nothing right away,
  # and a stale image doesn't linger forever just because few deploys
  # happened since.
  cleanup_policy_dry_run = false

  cleanup_policies {
    id     = "keep-recent"
    action = "KEEP"
    most_recent_versions {
      keep_count = var.artifact_retention_count
    }
  }

  cleanup_policies {
    id     = "delete-old"
    action = "DELETE"
    condition {
      older_than = "${var.artifact_retention_days * 86400}s"
    }
  }
}
