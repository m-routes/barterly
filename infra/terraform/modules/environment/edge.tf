# The public edge (docs/edge.md): one global external Application Load Balancer for the
# environment's domains, with
# - a Google-managed TLS certificate (TLS 1.2+, MODERN profile) and HTTP -> HTTPS;
# - Cloud Armor in front of the API and web (OWASP rules, per-IP rate limits, adaptive
#   protection);
# - Cloud CDN for the web's hashed assets, Django's static files and private media
#   (Cloud CDN signed URLs).
#
# Hosts:
#   api_domains[*]   -> API (Cloud Run); /static/* -> static bucket (CDN)
#   web_domains[0]   -> web (Cloud Run); /_next/static/* through the CDN
#   web_domains[1..] -> 301 to web_domains[0]
#   media_domain     -> private media bucket (CDN, signed URLs only)
#
# Everything here is created only when edge_enabled is set.

locals {
  edge          = var.edge_enabled
  canonical_web = length(var.web_domains) > 0 ? var.web_domains[0] : ""
  web_aliases   = length(var.web_domains) > 1 ? slice(var.web_domains, 1, length(var.web_domains)) : []
  media_cdn     = local.edge && var.media_domain != ""
  edge_domains = distinct(concat(
    var.api_domains,
    var.web_domains,
    var.media_domain == "" ? [] : [var.media_domain],
  ))
  # Provider webhooks and Cloud Tasks/Scheduler callbacks carry arbitrary text and are
  # authenticated by the API itself (HMAC signature or OIDC token), so they skip the
  # WAF and rate limits. Every webhook lives at /api/v1/<app>/webhooks/.
  armor_bypass_paths = "^/api/v1/([a-z_]+/webhooks|tasks|jobs)/"
  waf_rules = [
    "sqli-v33-stable",
    "xss-v33-stable",
    "lfi-v33-stable",
    "rfi-v33-stable",
    "rce-v33-stable",
    "methodenforcement-v33-stable",
    "scannerdetection-v33-stable",
    "protocolattack-v33-stable",
    "sessionfixation-v33-stable",
  ]
}

resource "google_compute_global_address" "edge" {
  count = local.edge ? 1 : 0
  name  = "barterly-edge-${local.env}"

  lifecycle {
    precondition {
      condition     = length(var.api_domains) > 0 && length(var.web_domains) > 0
      error_message = "edge_enabled needs at least one api_domains and one web_domains entry."
    }
  }
}

# --- TLS ---

resource "google_compute_managed_ssl_certificate" "edge" {
  count = local.edge ? 1 : 0
  # A new name per domain set, so a domain change provisions the new certificate before
  # the old one goes (create_before_destroy).
  name = "barterly-edge-${local.env}-${substr(sha1(join(",", local.edge_domains)), 0, 8)}"

  managed {
    domains = local.edge_domains
  }

  lifecycle {
    create_before_destroy = true
  }
}

resource "google_compute_ssl_policy" "edge" {
  count           = local.edge ? 1 : 0
  name            = "barterly-edge-${local.env}"
  profile         = "MODERN"
  min_tls_version = "TLS_1_2"
}

# --- Cloud Armor ---

resource "google_compute_security_policy" "edge" {
  count       = local.edge ? 1 : 0
  name        = "barterly-edge-${local.env}"
  description = "Barterly ${local.env}: OWASP rules, per-IP rate limits (docs/edge.md)."
  type        = "CLOUD_ARMOR"

  adaptive_protection_config {
    layer_7_ddos_defense_config {
      enable = true
    }
  }

  advanced_options_config {
    # Lets the WAF read JSON bodies field by field (fewer false positives on chat text).
    json_parsing = "STANDARD"
    log_level    = "NORMAL"
  }

  rule {
    priority    = 1000
    action      = "allow"
    description = "Webhooks and task callbacks: authenticated by the API"
    match {
      expr {
        expression = "request.path.matches('${local.armor_bypass_paths}')"
      }
    }
  }

  dynamic "rule" {
    for_each = { for i, name in local.waf_rules : name => 2000 + i }
    content {
      priority    = rule.value
      action      = "deny(403)"
      preview     = var.armor_preview
      description = "OWASP ${rule.key} (sensitivity 1)"
      match {
        expr {
          expression = "evaluatePreconfiguredWaf('${rule.key}', {'sensitivity': 1})"
        }
      }
    }
  }

  # Sign-in is the brute-force target: a tighter limit. Generous by design: Indian
  # mobile carriers put many people behind one address (CGNAT). The API's own
  # per-phone throttles still apply.
  rule {
    priority    = 3000
    action      = "throttle"
    preview     = var.armor_preview
    description = "Sign-in: ${var.armor_auth_requests_per_minute}/min per IP"
    match {
      expr {
        expression = "request.path.startsWith('/api/v1/auth/')"
      }
    }
    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      enforce_on_key = "IP"
      rate_limit_threshold {
        count        = var.armor_auth_requests_per_minute
        interval_sec = 60
      }
    }
  }

  rule {
    priority    = 3100
    action      = "throttle"
    preview     = var.armor_preview
    description = "Everything: ${var.armor_requests_per_minute}/min per IP"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
    rate_limit_options {
      conform_action = "allow"
      exceed_action  = "deny(429)"
      enforce_on_key = "IP"
      rate_limit_threshold {
        count        = var.armor_requests_per_minute
        interval_sec = 60
      }
    }
  }

  rule {
    priority    = 2147483647
    action      = "allow"
    description = "Default: allow"
    match {
      versioned_expr = "SRC_IPS_V1"
      config {
        src_ip_ranges = ["*"]
      }
    }
  }
}

# --- Backends ---

resource "google_compute_region_network_endpoint_group" "api" {
  count                 = local.edge ? 1 : 0
  name                  = "barterly-api-${local.env}"
  region                = var.region
  network_endpoint_type = "SERVERLESS"

  cloud_run {
    service = google_cloud_run_v2_service.api.name
  }
}

resource "google_compute_region_network_endpoint_group" "web" {
  count                 = local.edge ? 1 : 0
  name                  = "barterly-web-${local.env}"
  region                = var.region
  network_endpoint_type = "SERVERLESS"

  cloud_run {
    service = google_cloud_run_v2_service.web.name
  }
}

resource "google_compute_backend_service" "api" {
  count                 = local.edge ? 1 : 0
  name                  = "barterly-api-${local.env}"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  protocol              = "HTTPS"
  security_policy       = google_compute_security_policy.edge[0].id
  enable_cdn            = false

  backend {
    group = google_compute_region_network_endpoint_group.api[0].id
  }

  log_config {
    enable      = true
    sample_rate = 1
  }
}

resource "google_compute_backend_service" "web" {
  count                 = local.edge ? 1 : 0
  name                  = "barterly-web-${local.env}"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  protocol              = "HTTPS"
  security_policy       = google_compute_security_policy.edge[0].id
  enable_cdn            = false

  backend {
    group = google_compute_region_network_endpoint_group.web[0].id
  }

  log_config {
    enable      = true
    sample_rate = 1
  }
}

# Next.js's content-hashed assets (Cache-Control: public, immutable). Only this path
# goes through the CDN: pages can be personal, so the web backend above never caches.
resource "google_compute_backend_service" "web_assets" {
  count                 = local.edge ? 1 : 0
  name                  = "barterly-web-assets-${local.env}"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  protocol              = "HTTPS"
  enable_cdn            = true

  backend {
    group = google_compute_region_network_endpoint_group.web[0].id
  }

  cdn_policy {
    cache_mode       = "USE_ORIGIN_HEADERS"
    negative_caching = false
    cache_key_policy {
      include_host         = false
      include_protocol     = false
      include_query_string = false
    }
  }
}

# Django admin and API static files (public bucket; names aren't hashed, so short TTLs).
resource "google_compute_backend_bucket" "static" {
  count       = local.edge ? 1 : 0
  name        = "barterly-static-${local.env}"
  bucket_name = google_storage_bucket.static.name
  enable_cdn  = true

  cdn_policy {
    cache_mode  = "CACHE_ALL_STATIC"
    default_ttl = 3600
    client_ttl  = 3600
    max_ttl     = 86400
  }
}

# Private media. The bucket stays private: only Cloud CDN's fill account may read it
# (storage.tf), and the API hands out Cloud CDN signed URLs (apps.media.storage). TTLs
# are short so a deleted file leaves the cache within the hour; erasure also
# invalidates it (docs/edge.md).
resource "google_compute_backend_bucket" "media" {
  count       = local.media_cdn ? 1 : 0
  name        = "barterly-media-${local.env}"
  bucket_name = google_storage_bucket.media.name
  enable_cdn  = true

  cdn_policy {
    cache_mode                   = "FORCE_CACHE_ALL"
    default_ttl                  = 3600
    max_ttl                      = 3600
    client_ttl                   = 300
    signed_url_cache_max_age_sec = 300
    request_coalescing           = true
  }
}

# --- Routing ---

resource "google_compute_url_map" "edge" {
  count = local.edge ? 1 : 0
  name  = "barterly-edge-${local.env}"

  # Requests for unknown hosts (or the bare IP) go to the canonical site.
  default_url_redirect {
    host_redirect          = local.canonical_web
    https_redirect         = true
    redirect_response_code = "MOVED_PERMANENTLY_DEFAULT"
    strip_query            = false
  }

  host_rule {
    hosts        = var.api_domains
    path_matcher = "api"
  }

  path_matcher {
    name            = "api"
    default_service = google_compute_backend_service.api[0].id

    path_rule {
      paths   = ["/static/*"]
      service = google_compute_backend_bucket.static[0].id
    }
  }

  host_rule {
    hosts        = [local.canonical_web]
    path_matcher = "web"
  }

  path_matcher {
    name            = "web"
    default_service = google_compute_backend_service.web[0].id

    path_rule {
      paths   = ["/_next/static/*"]
      service = google_compute_backend_service.web_assets[0].id
    }
  }

  dynamic "host_rule" {
    for_each = length(local.web_aliases) > 0 ? [1] : []
    content {
      hosts        = local.web_aliases
      path_matcher = "web-aliases"
    }
  }

  dynamic "path_matcher" {
    for_each = length(local.web_aliases) > 0 ? [1] : []
    content {
      name = "web-aliases"
      default_url_redirect {
        host_redirect          = local.canonical_web
        https_redirect         = true
        redirect_response_code = "MOVED_PERMANENTLY_DEFAULT"
        strip_query            = false
      }
    }
  }

  dynamic "host_rule" {
    for_each = local.media_cdn ? [1] : []
    content {
      hosts        = [var.media_domain]
      path_matcher = "media"
    }
  }

  dynamic "path_matcher" {
    for_each = local.media_cdn ? [1] : []
    content {
      name            = "media"
      default_service = google_compute_backend_bucket.media[0].id
    }
  }
}

resource "google_compute_target_https_proxy" "edge" {
  count            = local.edge ? 1 : 0
  name             = "barterly-edge-${local.env}"
  url_map          = google_compute_url_map.edge[0].id
  ssl_certificates = [google_compute_managed_ssl_certificate.edge[0].id]
  ssl_policy       = google_compute_ssl_policy.edge[0].id
}

resource "google_compute_global_forwarding_rule" "https" {
  count                 = local.edge ? 1 : 0
  name                  = "barterly-edge-https-${local.env}"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  ip_address            = google_compute_global_address.edge[0].address
  port_range            = "443"
  target                = google_compute_target_https_proxy.edge[0].id
}

# Port 80 only redirects to HTTPS.
resource "google_compute_url_map" "http_redirect" {
  count = local.edge ? 1 : 0
  name  = "barterly-edge-http-${local.env}"

  default_url_redirect {
    https_redirect         = true
    redirect_response_code = "MOVED_PERMANENTLY_DEFAULT"
    strip_query            = false
  }
}

resource "google_compute_target_http_proxy" "http_redirect" {
  count   = local.edge ? 1 : 0
  name    = "barterly-edge-http-${local.env}"
  url_map = google_compute_url_map.http_redirect[0].id
}

resource "google_compute_global_forwarding_rule" "http" {
  count                 = local.edge ? 1 : 0
  name                  = "barterly-edge-http-${local.env}"
  load_balancing_scheme = "EXTERNAL_MANAGED"
  ip_address            = google_compute_global_address.edge[0].address
  port_range            = "80"
  target                = google_compute_target_http_proxy.http_redirect[0].id
}
