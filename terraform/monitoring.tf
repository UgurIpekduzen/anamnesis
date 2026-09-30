# Fires on a severity=ERROR structured log line with one of these event
# names — the github_poll one can be muted from the app's own Admin panel
# (src/integrations/github/alerts.py) by logging at WARNING instead,
# without touching this policy or granting the app any new GCP permission.
resource "google_monitoring_alert_policy" "app_errors" {
  for_each = toset(["agent_call_failed", "github_poll"])

  display_name = "Anamnesis: ${each.key}"
  combiner     = "OR"

  conditions {
    display_name = each.key
    condition_matched_log {
      filter = "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"anamnesis-app\" AND jsonPayload.event=\"${each.key}\" AND severity=ERROR"
    }
  }

  alert_strategy {
    notification_rate_limit {
      period = "3600s"
    }
    auto_close = "1800s"
  }

  notification_channels = [google_monitoring_notification_channel.owner_email.id]
  documentation {
    content   = "Check the anamnesis-app logs: jsonPayload.event is agent_call_failed or github_poll."
    mime_type = "text/markdown"
  }
}

resource "google_project_service" "monitoring" {
  service = "monitoring.googleapis.com"
}

resource "google_monitoring_notification_channel" "owner_email" {
  display_name = "Anamnesis owner email"
  type         = "email"

  labels = {
    email_address = var.owner_email
  }

  depends_on = [google_project_service.monitoring]
}
