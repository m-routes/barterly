#!/usr/bin/env bash
# Create the Cloud CDN signing key for media (docs/edge.md): 16 random bytes, base64url.
# It goes to the media backend bucket (so the CDN can check signatures) and to Secret
# Manager as media-cdn-key-<env> (so the API can sign). The key is held in a private
# temporary file for the gcloud call and never printed.
#
# Usage: PROJECT_ID=... infra/scripts/set-cdn-key.sh staging|production [key-name]
#
# First time: run after `terraform apply` created the backend bucket, then set
# media_cdn_signing_enabled = true and apply again (that grants Cloud CDN's fill account
# read access to the media bucket, which this script's first key creates).
#
# Rotation: run with a new key name (media-key-2), set media_cdn_key_name to it and
# apply (the API signs with the new key), wait 15 minutes for old links to expire, then
# remove the old key:
#   gcloud compute backend-buckets delete-signed-url-key barterly-media-<env> --key-name media-key-1
set -euo pipefail

ENVIRONMENT="${1:?usage: set-cdn-key.sh staging|production [key-name]}"
KEY_NAME="${2:-media-key-1}"
: "${PROJECT_ID:?set PROJECT_ID}"
case "$ENVIRONMENT" in staging|production) ;; *) echo "unknown environment: $ENVIRONMENT" >&2; exit 2 ;; esac

BACKEND_BUCKET="barterly-media-${ENVIRONMENT}"
SECRET="media-cdn-key-${ENVIRONMENT}"

umask 077
KEY_FILE="$(mktemp)"
trap 'rm -f "$KEY_FILE"' EXIT
openssl rand 16 | openssl base64 -A | tr '+/' '-_' | tr -d '=' >"$KEY_FILE"

gcloud compute backend-buckets add-signed-url-key "$BACKEND_BUCKET" \
  --project "$PROJECT_ID" --key-name "$KEY_NAME" --key-file "$KEY_FILE"
gcloud secrets versions add "$SECRET" --project "$PROJECT_ID" --data-file="$KEY_FILE"

echo "Added CDN key ${KEY_NAME} to ${BACKEND_BUCKET} and a new version of ${SECRET}."
echo "Next: media_cdn_signing_enabled = true (and media_cdn_key_name = \"${KEY_NAME}\" if not the default), terraform apply, then redeploy."
