# The production edge: domains, TLS, WAF and CDN

Terraform: `infra/terraform/modules/environment/edge.tf`, switched on with
`edge_enabled` (on by default in production). Each environment gets one global
external Application Load Balancer in front of its Cloud Run services and buckets.

```
                   ┌────────────── Cloud Armor (WAF, rate limits) ──────────────┐
barterly.in      ──┤ web (Cloud Run)              /_next/static/* → CDN         │
www.barterly.in  ──┤ 301 → barterly.in                                          │
api.barterly.in  ──┤ api (Cloud Run)              /static/* → static bucket CDN │
media.barterly.in ─┤ private media bucket via Cloud CDN, signed URLs only       │
                   └─────────────────────────────────────────────────────────────┘
http://*  → 301 https://   (TLS 1.2+, MODERN cipher profile, HSTS from the apps)
```

## Domains and DNS

The domains come from `terraform.tfvars` (`api_domains`, `web_domains`,
`media_domain`). The first web domain is canonical, and the others redirect to it.
After `terraform apply`:

```bash
terraform output -json environment | jq '.dns_records'
```

Create one **A record** for each domain, pointing at `edge_ip`, at the registrar. If
the zone already has `AAAA` records for these names, remove them (the load balancer
gets an IPv4 address). Production:

| Name | Type | Value |
| --- | --- | --- |
| `barterly.in` | A | `edge_ip` |
| `www.barterly.in` | A | `edge_ip` |
| `api.barterly.in` | A | `edge_ip` |
| `media.barterly.in` | A | `edge_ip` |

Also add a **CAA** record allowing Google's CA, if the zone has any CAA records:
`barterly.in. CAA 0 issue "pki.goog"`.

Staging uses the same layout under `staging.barterly.in`
(`envs/staging/terraform.tfvars.example`). Turn it on there first, so every edge
change is tried in staging before production.

## TLS

The certificate is Google-managed (`google_compute_managed_ssl_certificate`), with
one certificate covering every domain. Google can only issue it once **all** of its
domains resolve to the load balancer, which takes 15 to 60 minutes after DNS is
right. Check it with:

```bash
CERT="$(terraform output -json environment | jq -r .certificate_name)"
gcloud compute ssl-certificates describe "$CERT" --global \
  --format='value(managed.status, managed.domainStatus)'
```

`PROVISIONING` with a domain in `FAILED_NOT_VISIBLE` means that domain's DNS isn't
pointing at `edge_ip` yet. Renewal is automatic. Changing the domain list creates a
new certificate before the old one is removed, so there's no gap.

The SSL policy allows TLS 1.2 and 1.3 with the MODERN profile. Port 80 only redirects
to HTTPS. HSTS comes from the apps (Django in production; Next.js with `preload`).
Submit `barterly.in` to hstspreload.org only once every subdomain serves HTTPS.

## Cloud Armor

One security policy per environment, on the API and web backends. Rules are
evaluated by priority:

| Priority | Rule | Action |
| --- | --- | --- |
| 1000 | Webhooks (`/api/v1/<app>/webhooks/`: Razorpay, RazorpayX, KYC) and Cloud Tasks/Scheduler callbacks (`/api/v1/tasks/`, `/api/v1/jobs/`) | Allow: authenticated by the API (HMAC or OIDC), and their bodies would trip the WAF |
| 2000–2008 | OWASP CRS 3.3 preconfigured rules at sensitivity 1: SQLi, XSS, LFI, RFI, RCE, method enforcement, scanner detection, protocol attack, session fixation | 403 |
| 3000 | `/api/v1/auth/`: over `armor_auth_requests_per_minute` (120) per IP | 429 |
| 3100 | Everything: over `armor_requests_per_minute` (3000) per IP | 429 |
| default | | Allow |

Also enabled: Adaptive Protection (layer-7 DDoS detection, which suggests rules in
the console) and JSON body parsing, so chat text inside JSON is inspected field by
field.

The rate limits are deliberately high: Indian mobile carriers put many subscribers
behind one address (CGNAT). They stop floods, not individuals. The API's own
throttles (per phone number for sign-in) do the fine-grained limiting.

**Rolling it out:** set `armor_preview = true` for the first days after enabling. In
preview, rules only log. Look for false positives in Logs Explorer:

```
resource.type="http_load_balancer"
jsonPayload.enforcedSecurityPolicy.outcome="DENY" OR jsonPayload.previewSecurityPolicy.outcome="DENY"
```

Each blocked request names its rule (`preconfiguredExprIds` for the WAF). Tune a noisy
signature with `opt_out_rule_ids` rather than turning the whole rule off. Then set
`armor_preview = false` and apply.

## CDN

| Path | Backend | Caching |
| --- | --- | --- |
| `barterly.in/_next/static/*` | web (a second backend service, CDN on) | By origin headers: Next.js marks these `public, immutable` (content-hashed names) |
| `api.barterly.in/static/*` | static bucket (public) | All static content; 1 h default, 1 day max (names aren't hashed) |
| `media.barterly.in/*` | media bucket (private) | Everything for up to 1 h, and only for requests with a valid Cloud CDN signature |
| everything else | web / API | Never cached |

Pages are never cached at the edge, because signed-in pages are personal. Only
`/_next/static/` goes through the CDN backend.

Django's `STATIC_URL` becomes `https://api.barterly.in/static/` (Terraform sets
`STATIC_URL`).

### Media through the CDN

The media bucket stays private, with public access prevention enforced. The CDN
reads it with Cloud CDN's own fill account. The API hands out **Cloud CDN signed
URLs** (`apps.media.storage.CDNMediaStorage`) with the same short lifetimes as before
(`MEDIA_READ_URL_SECONDS`, at most 15 minutes). Downloads that need a file name or
`Content-Disposition: attachment` keep using Cloud Storage signed URLs. Uploads still
go straight to Cloud Storage.

Setting it up (once per environment, after the first apply with `media_domain`):

```bash
PROJECT_ID=... infra/scripts/set-cdn-key.sh production
# then in terraform.tfvars: media_cdn_signing_enabled = true
terraform apply   # grants the fill account read access, wires MEDIA_CDN_* into the API
```

Check it before launch:
- A signed URL from the API loads the image.
- The same URL with `Signature` changed returns 403.
- `https://media.barterly.in/<any key>` with no signature returns 403. Never ship if
  it doesn't.

Deleting a file removes it from the bucket at once. A copy cached at the edge can
live for up to an hour, but only someone holding a signed URL for it, which expires
within 15 minutes, can fetch it. For erasure requests that must be immediate,
invalidate the path too:

```bash
gcloud compute url-maps invalidate-cdn-cache barterly-edge-production --host media.barterly.in --path "/users/<id>/*" --async
```

Key rotation is described in the comments of `infra/scripts/set-cdn-key.sh`.

## Client IPs and the run.app URLs

- **X-Forwarded-For.** Behind the load balancer the API sees
  `X-Forwarded-For: <client>, <load balancer IP>`. `EdgeForwardedForMiddleware`
  drops the last hop when it is the load balancer (`EDGE_PROXY_IPS`, set by
  Terraform), so throttles and audit logs see the client. A request straight to
  `run.app` always ends with the real caller, so a forged header doesn't help.
- **The web server calls the API directly.** Its `API_URL` is the API's run.app URL.
  If it went through the load balancer, Cloud Armor would count every browser's calls
  against the web server's few egress addresses.
- **Known gap.** The run.app URLs stay reachable from the internet (ingress `all`),
  so the WAF can be bypassed by calling them directly. Two things depend on them
  today: the deploy's candidate smoke test (`infra/scripts/deploy.sh`) and the web's
  server-to-server calls. Closing it is a follow-up:
  - give the web service Direct VPC egress;
  - set the API's ingress to `internal-and-cloud-load-balancing`;
  - smoke-test candidates through a tagged URL behind the load balancer.

  Until then, apps and browsers only know the custom domains (the production app
  build uses `https://api.barterly.in`).

## Monitoring

The uptime checks use the custom domains (`local.api_url`, `local.web_url`), so they
test the whole edge: DNS, certificate, Armor and the backends. Load-balancer logs
(sampled at 100%) include the Armor outcome of every request.
