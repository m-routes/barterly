#!/usr/bin/env bash
# Build a signed, obfuscated store release and send its debug symbols to Sentry.
# docs/release.md has the whole mobile release flow.
#
# Usage: [BUILD_NUMBER=...] [SENTRY_AUTH_TOKEN=... SENTRY_ORG=... SENTRY_PROJECT=...] \
#          tool/build_release.sh appbundle|ipa env/<environment>.json
#
# Versioning:
# - The version name is pubspec.yaml's `version` (1.4.2): bump it in the release PR.
# - The build number (Android versionCode, iOS CFBundleVersion) must only go up across
#   every upload to a store. Default: the number of commits on HEAD, which grows with
#   every merge to main. Override with BUILD_NUMBER (CI passes its run number + offset).
#
# Signing:
# - Android: android/key.properties or BARTERLY_UPLOAD_* (see key.properties.example).
#   A production bundle is refused without the upload key.
# - iOS: automatic signing with the team in ios/ExportOptions.plist (copy
#   ExportOptions.plist.example; it is gitignored because it names the team).
#
# Symbols: --split-debug-info keeps them out of the app (obfuscation shrinks it and
# hides names); sentry_dart_plugin uploads them under the same release name the app
# reports (barterly@<version>+<build>), so Sentry maps stack traces back. Without
# SENTRY_AUTH_TOKEN the build still runs and the upload is skipped with a warning.
set -euo pipefail

TARGET="${1:?usage: build_release.sh appbundle|ipa env/<environment>.json}"
ENV_FILE="${2:?usage: build_release.sh appbundle|ipa env/<environment>.json}"
case "$TARGET" in appbundle|ipa) ;; *) echo "unknown target: $TARGET" >&2; exit 2 ;; esac

cd "$(dirname "$0")/.."

[[ -f "$ENV_FILE" ]] || { echo "no such environment file: $ENV_FILE" >&2; exit 2; }
[[ -f env/firebase-keys.json ]] || {
  echo "env/firebase-keys.json is missing (copy env/firebase-keys.example.json and fill it in)." >&2
  exit 2
}

VERSION="$(sed -n 's/^version: *\([0-9][0-9.]*\).*/\1/p' pubspec.yaml)"
if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "pubspec.yaml version must look like 1.4.2 (found '${VERSION}')" >&2
  exit 2
fi
BUILD_NUMBER="${BUILD_NUMBER:-$(git rev-list --count HEAD)}"
[[ "$BUILD_NUMBER" =~ ^[0-9]+$ ]] || { echo "BUILD_NUMBER must be a whole number" >&2; exit 2; }
RELEASE="barterly@${VERSION}+${BUILD_NUMBER}"
IS_PRODUCTION=0
grep -q '"BARTERLY_ENV": *"production"' "$ENV_FILE" && IS_PRODUCTION=1

extra=()
if [[ "$TARGET" == "appbundle" && "$IS_PRODUCTION" == "1" ]]; then
  if [[ ! -f android/key.properties && -z "${BARTERLY_UPLOAD_STORE_FILE:-}" ]]; then
    echo "No upload key: add android/key.properties or BARTERLY_UPLOAD_* (docs/release.md, Signing)." >&2
    exit 2
  fi
fi
if [[ "$TARGET" == "ipa" ]]; then
  [[ -f ios/ExportOptions.plist ]] || {
    echo "ios/ExportOptions.plist is missing (copy ios/ExportOptions.plist.example and set your team id)." >&2
    exit 2
  }
  extra+=(--export-options-plist=ios/ExportOptions.plist)
fi

echo "Building ${RELEASE} (${TARGET}, ${ENV_FILE})"
flutter build "$TARGET" --release \
  --build-name "$VERSION" --build-number "$BUILD_NUMBER" \
  --obfuscate --split-debug-info=build/symbols \
  --dart-define-from-file="$ENV_FILE" \
  --dart-define-from-file=env/firebase-keys.json \
  --dart-define=SENTRY_RELEASE="$RELEASE" \
  --dart-define=SENTRY_DIST="$BUILD_NUMBER" \
  ${extra[@]+"${extra[@]}"}

if [[ -n "${SENTRY_AUTH_TOKEN:-}" ]]; then
  SENTRY_RELEASE="$RELEASE" SENTRY_DIST="$BUILD_NUMBER" dart run sentry_dart_plugin
else
  echo "SENTRY_AUTH_TOKEN not set: symbols not uploaded (build/symbols kept)." >&2
fi

echo "Built ${RELEASE}."
