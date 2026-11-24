# Monitoring: alerts, uptime checks, the availability SLO and a dashboard.
#
# Signals come from three places:
# - Cloud Run, Cloud Tasks and Cloud SQL's built-in metrics (errors, latency,
#   instances, queue depth, database connections).
# - Log-based metrics over the API's structured "ops events" (apps/common/ops.py):
#   webhook failures, reconciliation mismatches, dead letters, database connection
#   failures, failed jobs, and the backlog counts the ops_backlog job logs every five
#   minutes. An event's name is an interface: apps/common/tests/test_ops.py fails if
#   one has no metric here.
# - Uptime checks on the API and the web. (A synthetic sign-in isn't built yet; see
#   docs/operations.md.)
#
# Alerts go to var.alert_emails. Each policy's documentation names its runbook in
# docs/runbooks/.

locals {
  alerts_enabled = length(var.alert_emails) > 0
  channels       = [for c in google_monitoring_notification_channel.email : c.id]
  runbooks       = "https://github.com/m-routes/barterly/blob/main/docs/runbooks"

  api_filter = "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"${local.api_name}\""
  ops_filter = "resource.type=\"cloud_run_revision\" AND resource.labels.service_name=\"${local.api_name}\" AND jsonPayload.ops_event"

  # Ops event → the alert on its count. `threshold` is the count in `window` that
  # fires the alert.
  ops_counters = {
    webhook_rejected = {
      display   = "Webhook signature or format rejected"
      threshold = 5
      window    = "600s"
      runbook   = "payment-mismatch.md"
      labels    = ["provider"]
    }
    webhook_failed = {
      display   = "Signed webhook couldn't be applied"
      threshold = 1
      window    = "300s"
      runbook   = "payment-mismatch.md"
      labels    = ["provider"]
    }
    reconciliation_mismatch = {
      display   = "Ledger and gateway don't match"
      threshold = 1
      window    = "3600s"
      runbook   = "payment-mismatch.md"
      labels    = []
    }
    notification_dead_letter = {
      display   = "Notifications dead-lettered"
      threshold = 10
      window    = "3600s"
      runbook   = "otp-provider-outage.md"
      labels    = ["channel"]
    }
    db_connection_failed = {
      display   = "Database unreachable after retries"
      threshold = 1
      window    = "300s"
      runbook   = "database-outage.md"
      labels    = []
    }
    job_failed = {
      display   = "Scheduled job failed"
      threshold = 3
      window    = "3600s"
      runbook   = "stuck-payouts.md"
      labels    = ["job"]
    }
  }

  # Backlog counts (the ops_backlog job): a gauge each, alerting when the latest value
  # stays above the threshold for 15 minutes. The backlog event itself is the metric
  # source, so it has a counter too (below) to catch the job not running.
  backlog_gauges = {
    notifications_stuck    = { threshold = 50, runbook = "otp-provider-outage.md" }
    notifications_dead_24h = { threshold = 100, runbook = "otp-provider-outage.md" }
    payouts_stuck          = { threshold = 1, runbook = "stuck-payouts.md" }
    jobs_failed_24h        = { threshold = 10, runbook = "stuck-payouts.md" }
  }
}

resource "google_monitoring_notification_channel" "email" {
  for_each     = toset(var.alert_emails)
  display_name = "Barterly ${local.env} alerts: ${each.value}"
  type         = "email"
  labels       = { email_address = each.value }
}

# ---------- Log-based metrics over ops events ----------

resource "google_logging_metric" "ops" {
  for_each = local.ops_counters

  name   = "barterly/${local.env}/${each.key}"
  filter = "${local.ops_filter}=\"${each.key}\""

  metric_descriptor {
    metric_kind  = "DELTA"
    value_type   = "INT64"
    display_name = "${each.value.display} (${local.env})"

    dynamic "labels" {
      for_each = each.value.labels
      content {
        key        = labels.value
        value_type = "STRING"
      }
    }
  }
  label_extractors = { for l in each.value.labels : l => "EXTRACT(jsonPayload.${l})" }
}

# The backlog event: a counter (is the job running?) and a gauge per count.
resource "google_logging_metric" "backlog_runs" {
  name   = "barterly/${local.env}/backlog"
  filter = "${local.ops_filter}=\"backlog\""
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
}

resource "google_logging_metric" "backlog" {
  for_each = local.backlog_gauges

  name            = "barterly/${local.env}/backlog_${each.key}"
  filter          = "${local.ops_filter}=\"backlog\""
  value_extractor = "EXTRACT(jsonPayload.${each.key})"

  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "DISTRIBUTION"
    unit        = "1"
  }
  bucket_options {
    explicit_buckets {
      bounds = [0, 1, 5, 10, 50, 100, 500, 1000]
    }
  }
}

# Database errors during requests (not just at start-up): Django raises
# OperationalError/InterfaceError when a connection drops.
resource "google_logging_metric" "db_request_errors" {
  name   = "barterly/${local.env}/db_request_errors"
  filter = "${local.api_filter} AND severity>=ERROR AND jsonPayload.exception=~\"(OperationalError|InterfaceError)\""
  metric_descriptor {
    metric_kind = "DELTA"
    value_type  = "INT64"
  }
}

# ---------- Alerts ----------

resource "google_monitoring_alert_policy" "ops" {
  for_each = local.alerts_enabled ? local.ops_counters : {}

  display_name          = "[${local.env}] ${each.value.display}"
  combiner              = "OR"
  notification_channels = local.channels

  conditions {
    display_name = each.value.display
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.ops[each.key].name}\" AND resource.type=\"cloud_run_revision\""
      comparison      = "COMPARISON_GT"
      threshold_value = each.value.threshold - 0.5
      duration        = "0s"
      aggregations {
        alignment_period     = each.value.window
        per_series_aligner   = "ALIGN_SUM"
        cross_series_reducer = "REDUCE_SUM"
      }
      trigger {
        count = 1
      }
    }
  }

  documentation {
    mime_type = "text/markdown"
    content   = "${each.value.display}: ${each.value.threshold} or more in ${each.value.window}. Runbook: ${local.runbooks}/${each.value.runbook}"
  }
}

resource "google_monitoring_alert_policy" "backlog" {
  for_each = local.alerts_enabled ? local.backlog_gauges : {}

  display_name          = "[${local.env}] Backlog: ${replace(each.key, "_", " ")}"
  combiner              = "OR"
  notification_channels = local.channels

  conditions {
    display_name = "${each.key} above ${each.value.threshold}"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.backlog[each.key].name}\" AND resource.type=\"cloud_run_revision\""
      comparison      = "COMPARISON_GT"
      threshold_value = each.value.threshold - 0.5
      duration        = "900s"
      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_PERCENTILE_99"
        cross_series_reducer = "REDUCE_MAX"
      }
    }
  }

  documentation {
    mime_type = "text/markdown"
    content   = "The ops_backlog job reports ${each.key} above ${each.value.threshold} for 15 minutes. Runbook: ${local.runbooks}/${each.value.runbook}"
  }
}

resource "google_monitoring_alert_policy" "backlog_job_silent" {
  count = local.alerts_enabled ? 1 : 0

  display_name          = "[${local.env}] Backlog job not reporting"
  combiner              = "OR"
  notification_channels = local.channels

  conditions {
    display_name = "No backlog event for 20 minutes"
    condition_absent {
      filter   = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.backlog_runs.name}\" AND resource.type=\"cloud_run_revision\""
      duration = "1200s"
      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_SUM"
        cross_series_reducer = "REDUCE_SUM"
      }
    }
  }

  documentation {
    mime_type = "text/markdown"
    content   = "Scheduled jobs may not be running (Cloud Scheduler, the scheduler service account, or the API). Runbook: ${local.runbooks}/stuck-payouts.md"
  }
}

resource "google_monitoring_alert_policy" "db_errors" {
  count = local.alerts_enabled ? 1 : 0

  display_name          = "[${local.env}] Database connection errors"
  combiner              = "OR"
  notification_channels = local.channels

  conditions {
    display_name = "Requests failing on the database"
    condition_threshold {
      filter          = "metric.type=\"logging.googleapis.com/user/${google_logging_metric.db_request_errors.name}\" AND resource.type=\"cloud_run_revision\""
      comparison      = "COMPARISON_GT"
      threshold_value = 4.5
      duration        = "0s"
      aggregations {
        alignment_period     = "300s"
        per_series_aligner   = "ALIGN_SUM"
        cross_series_reducer = "REDUCE_SUM"
      }
    }
  }

  conditions {
    display_name = "Connections near the instance limit"
    condition_prometheus_query_language {
      query    = "max(cloudsql_googleapis_com:database_postgresql_num_backends{database_id=\"${var.project_id}:${local.db_instance_name}\"}) > ${var.db_connection_alert}"
      duration = "600s"
    }
  }

  documentation {
    mime_type = "text/markdown"
    content   = "Runbook: ${local.runbooks}/database-outage.md"
  }
}

resource "google_monitoring_alert_policy" "errors" {
  for_each = local.alerts_enabled ? { api = local.api_name, web = local.web_name } : {}

  display_name          = "[${local.env}] ${each.key}: 5xx error rate above ${var.error_rate_alert * 100}%"
  combiner              = "OR"
  notification_channels = local.channels

  conditions {
    display_name = "5xx share of requests over 10 minutes"
    condition_prometheus_query_language {
      query    = <<-EOT
        sum(rate(run_googleapis_com:request_count{monitored_resource="cloud_run_revision",service_name="${each.value}",response_code_class="5xx"}[10m]))
        / sum(rate(run_googleapis_com:request_count{monitored_resource="cloud_run_revision",service_name="${each.value}"}[10m]))
        > ${var.error_rate_alert}
      EOT
      duration = "300s"
    }
  }

  documentation {
    mime_type = "text/markdown"
    content   = "If a deploy just went out, roll it back first. Runbook: ${local.runbooks}/bad-deploy-rollback.md"
  }
}

resource "google_monitoring_alert_policy" "latency" {
  for_each = local.alerts_enabled ? { api = local.api_name, web = local.web_name } : {}

  display_name          = "[${local.env}] ${each.key}: p95 latency above ${var.latency_p95_alert_ms} ms"
  combiner              = "OR"
  notification_channels = local.channels

  conditions {
    display_name = "p95 request latency over 10 minutes"
    condition_prometheus_query_language {
      query    = <<-EOT
        histogram_quantile(0.95, sum by (le) (rate(run_googleapis_com:request_latencies_bucket{monitored_resource="cloud_run_revision",service_name="${each.value}"}[10m])))
        > ${var.latency_p95_alert_ms}
      EOT
      duration = "600s"
    }
  }

  documentation {
    mime_type = "text/markdown"
    content   = "Check Cloud SQL CPU and connections, then recent deploys. Runbooks: ${local.runbooks}/database-outage.md, ${local.runbooks}/bad-deploy-rollback.md"
  }
}

resource "google_monitoring_alert_policy" "instances" {
  for_each = local.alerts_enabled ? {
    api = { name = local.api_name, max = var.api_max_instances }
    web = { name = local.web_name, max = var.web_max_instances }
  } : {}

  display_name          = "[${local.env}] ${each.key}: instances near the maximum"
  combiner              = "OR"
  notification_channels = local.channels

  conditions {
    display_name = "Instances at 80% of max_instance_count for 10 minutes"
    condition_prometheus_query_language {
      query    = "sum(run_googleapis_com:container_instance_count{monitored_resource=\"cloud_run_revision\",service_name=\"${each.value.name}\",state=\"active\"}) >= ${ceil(each.value.max * 0.8)}"
      duration = "600s"
    }
  }

  documentation {
    mime_type = "text/markdown"
    content   = "Requests may start queueing. Raising max instances also raises database connections: check db_tier first (database.tf)."
  }
}

resource "google_monitoring_alert_policy" "queue_backlog" {
  count = local.alerts_enabled ? 1 : 0

  display_name          = "[${local.env}] Background task queue backing up"
  combiner              = "OR"
  notification_channels = local.channels

  conditions {
    display_name = "More than ${var.queue_depth_alert} tasks waiting for 15 minutes"
    condition_prometheus_query_language {
      query    = "max(cloudtasks_googleapis_com:queue_depth{monitored_resource=\"cloud_tasks_queue\",queue_id=\"${google_cloud_tasks_queue.tasks.name}\"}) > ${var.queue_depth_alert}"
      duration = "900s"
    }
  }

  documentation {
    mime_type = "text/markdown"
    content   = "Tasks (mostly notifications) are failing or the API is overloaded. Runbook: ${local.runbooks}/otp-provider-outage.md"
  }
}

# ---------- Uptime checks ----------

resource "google_monitoring_uptime_check_config" "api" {
  display_name = "Barterly API ${local.env}"
  timeout      = "10s"
  period       = "60s"

  http_check {
    path         = "/api/v1/health/"
    port         = 443
    use_ssl      = true
    validate_ssl = true
    accepted_response_status_codes {
      status_class = "STATUS_CLASS_2XX"
    }
  }

  monitored_resource {
    type   = "uptime_url"
    labels = { project_id = var.project_id, host = trimprefix(local.api_url, "https://") }
  }

  checker_type     = "STATIC_IP_CHECKERS"
  selected_regions = ["ASIA_PACIFIC", "EUROPE", "USA_VIRGINIA"]
}

resource "google_monitoring_uptime_check_config" "web" {
  display_name = "Barterly web ${local.env}"
  timeout      = "10s"
  period       = "60s"

  http_check {
    path         = "/"
    port         = 443
    use_ssl      = true
    validate_ssl = true
    accepted_response_status_codes {
      status_class = "STATUS_CLASS_2XX"
    }
  }

  content_matchers {
    content = "Barterly"
    matcher = "CONTAINS_STRING"
  }

  monitored_resource {
    type   = "uptime_url"
    labels = { project_id = var.project_id, host = trimprefix(local.web_url, "https://") }
  }

  checker_type     = "STATIC_IP_CHECKERS"
  selected_regions = ["ASIA_PACIFIC", "EUROPE", "USA_VIRGINIA"]
}

resource "google_monitoring_alert_policy" "uptime" {
  for_each = local.alerts_enabled ? {
    api = google_monitoring_uptime_check_config.api.uptime_check_id
    web = google_monitoring_uptime_check_config.web.uptime_check_id
  } : {}

  display_name          = "[${local.env}] ${each.key} is down"
  combiner              = "OR"
  notification_channels = local.channels

  conditions {
    display_name = "Uptime check failing from 2+ regions"
    condition_threshold {
      filter          = "metric.type=\"monitoring.googleapis.com/uptime_check/check_passed\" AND resource.type=\"uptime_url\" AND metric.label.check_id=\"${each.value}\""
      comparison      = "COMPARISON_GT"
      threshold_value = 1
      duration        = "120s"
      aggregations {
        alignment_period     = "60s"
        per_series_aligner   = "ALIGN_NEXT_OLDER"
        cross_series_reducer = "REDUCE_COUNT_FALSE"
        group_by_fields      = ["resource.label.host"]
      }
    }
  }

  documentation {
    mime_type = "text/markdown"
    content   = "Runbooks: ${local.runbooks}/bad-deploy-rollback.md, ${local.runbooks}/database-outage.md"
  }
}

# ---------- SLO: availability ----------
#
# docs/slo.md: 99.5% of API requests succeed (not 5xx) over a rolling 28 days. That
# leaves an error budget of 0.5%, about 3.4 hours of full outage. Alerts fire on how
# fast the budget burns, not on single errors.

resource "google_monitoring_custom_service" "api" {
  service_id   = "barterly-api-${local.env}"
  display_name = "Barterly API (${local.env})"
}

resource "google_monitoring_slo" "api_availability" {
  service      = google_monitoring_custom_service.api.service_id
  slo_id       = "availability"
  display_name = "API availability: ${var.availability_slo * 100}% of requests succeed (28 days)"

  goal                = var.availability_slo
  rolling_period_days = 28

  request_based_sli {
    good_total_ratio {
      good_service_filter = join(" AND ", [
        "metric.type=\"run.googleapis.com/request_count\"",
        "resource.type=\"cloud_run_revision\"",
        "resource.label.\"service_name\"=\"${local.api_name}\"",
        "metric.label.\"response_code_class\"!=\"5xx\"",
      ])
      total_service_filter = join(" AND ", [
        "metric.type=\"run.googleapis.com/request_count\"",
        "resource.type=\"cloud_run_revision\"",
        "resource.label.\"service_name\"=\"${local.api_name}\"",
      ])
    }
  }
}

# Multi-window burn rates (the SRE workbook): 14.4x for an hour spends 2% of the
# budget (page); 6x for six hours spends 5% (ticket-level, same channel for now).
resource "google_monitoring_alert_policy" "slo_burn" {
  for_each = local.alerts_enabled ? {
    fast = { lookback = "3600s", rate = 14.4 }
    slow = { lookback = "21600s", rate = 6 }
  } : {}

  display_name          = "[${local.env}] API error budget burning (${each.key})"
  combiner              = "OR"
  notification_channels = local.channels

  conditions {
    display_name = "Burn rate above ${each.value.rate}x over ${each.value.lookback}"
    condition_threshold {
      filter          = "select_slo_burn_rate(\"${google_monitoring_slo.api_availability.id}\", \"${each.value.lookback}\")"
      comparison      = "COMPARISON_GT"
      threshold_value = each.value.rate
      duration        = "0s"
    }
  }

  documentation {
    mime_type = "text/markdown"
    content   = "The availability SLO's error budget is going fast. See docs/slo.md for what to freeze, and the bad-deploy runbook: ${local.runbooks}/bad-deploy-rollback.md"
  }
}

# ---------- Dashboard ----------

resource "google_monitoring_dashboard" "ops" {
  dashboard_json = jsonencode({
    displayName = "Barterly ${local.env}"
    mosaicLayout = {
      columns = 12
      tiles = [
        for i, w in concat(
          [
            for svc in [local.api_name, local.web_name] : {
              title = "${svc}: requests by status class"
              q     = "sum by (response_code_class) (rate(run_googleapis_com:request_count{monitored_resource=\"cloud_run_revision\",service_name=\"${svc}\"}[5m]))"
            }
          ],
          [
            for svc in [local.api_name, local.web_name] : {
              title = "${svc}: p50 / p95 latency (ms)"
              q     = "histogram_quantile(0.95, sum by (le) (rate(run_googleapis_com:request_latencies_bucket{monitored_resource=\"cloud_run_revision\",service_name=\"${svc}\"}[5m])))"
            }
          ],
          [
            for svc in [local.api_name, local.web_name] : {
              title = "${svc}: instances"
              q     = "sum by (state) (run_googleapis_com:container_instance_count{monitored_resource=\"cloud_run_revision\",service_name=\"${svc}\"})"
            }
          ],
          [
            {
              title = "Task queue depth"
              q     = "max(cloudtasks_googleapis_com:queue_depth{monitored_resource=\"cloud_tasks_queue\",queue_id=\"${google_cloud_tasks_queue.tasks.name}\"})"
            },
            {
              title = "Database connections"
              q     = "max(cloudsql_googleapis_com:database_postgresql_num_backends{database_id=\"${var.project_id}:${local.db_instance_name}\"})"
            },
            {
              title = "Database CPU"
              q     = "max(cloudsql_googleapis_com:database_cpu_utilization{database_id=\"${var.project_id}:${local.db_instance_name}\"})"
            },
          ],
          [
            for key, c in local.ops_counters : {
              title = c.display
              q     = "sum(rate(logging_googleapis_com:user_${replace(google_logging_metric.ops[key].name, "/", "_")}[10m]))"
            }
          ],
          ) : {
          xPos   = (i % 2) * 6
          yPos   = floor(i / 2) * 4
          width  = 6
          height = 4
          widget = {
            title = w.title
            xyChart = {
              dataSets = [{
                plotType        = "LINE"
                timeSeriesQuery = { prometheusQuery = w.q }
              }]
            }
          }
        }
      ]
    }
  })
}
