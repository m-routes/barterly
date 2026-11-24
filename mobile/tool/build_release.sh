#!/usr/bin/env bash
# Build an obfuscated release and send its debug symbols to Sentry.
#
# Usage: SENTRY_AUTH_TOKEN=... SENTRY_ORG=... SENTRY_PROJECT=... \
#          tool/build_release.sh appbundle|ipa env/production.json
#
# The symbols stay out of the app (obfuscation shrinks it and hides names) and only
# Sentry can map stack traces back. Without SENTRY_AUTH_TOKEN the build still runs
# and the upload is skipped with a warning.
set -euo pipefail

TARGET="${1:?usage: build_release.sh appbundle|ipa env/<environment>.json}"
ENV_FILE="${2:?usage: build_release.sh appbundle|ipa env/<environment>.json}"
case "$TARGET" in appbundle|ipa) ;; *) echo "unknown target: $TARGET" >&2; exit 2 ;; esac

cd "$(dirname "$0")/.."
flutter build "$TARGET" --release \
  --obfuscate --split-debug-info=build/symbols \
  --dart-define-from-file="$ENV_FILE" \
  --dart-define-from-file=env/firebase-keys.json

if [[ -n "${SENTRY_AUTH_TOKEN:-}" ]]; then
  dart run sentry_dart_plugin
else
  echo "SENTRY_AUTH_TOKEN not set: symbols not uploaded (build/symbols kept)." >&2
fi
