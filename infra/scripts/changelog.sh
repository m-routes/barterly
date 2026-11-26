#!/usr/bin/env bash
# Write the release's section of CHANGELOG.md from the pull requests merged since the
# previous release tag. Run it in the release PR (docs/release.md) and commit the result;
# deploy.yml publishes the same notes as the GitHub release when the tag ships.
#
# Usage: infra/scripts/changelog.sh v1.4.0 [previous-tag]
#        infra/scripts/changelog.sh unreleased   (what main has that production doesn't)
#
# With the GitHub CLI signed in, the notes come from GitHub's generator, grouped by the
# labels in .github/release.yml. Without it, they come from git: every commit on main
# whose subject ends in "(#123)" (the squash-merge subject) since the previous tag.
set -euo pipefail

VERSION="${1:?usage: changelog.sh vMAJOR.MINOR.PATCH|unreleased [previous-tag]}"
if [[ "$VERSION" != "unreleased" && ! "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
  echo "not a release tag: $VERSION" >&2
  exit 2
fi
cd "$(git rev-parse --show-toplevel)"

PREVIOUS="${2:-$(git describe --tags --abbrev=0 --match 'v[0-9]*.[0-9]*.[0-9]*' origin/main 2>/dev/null || true)}"
RANGE="${PREVIOUS:+${PREVIOUS}..}origin/main"
TODAY="$(date -u +%Y-%m-%d)"
REPO="${GITHUB_REPOSITORY:-m-routes/barterly}"

notes_from_github() {
  local args=(-f tag_name="$VERSION" -f target_commitish=main)
  [[ -n "$PREVIOUS" ]] && args+=(-f previous_tag_name="$PREVIOUS")
  gh api "repos/${REPO}/releases/generate-notes" "${args[@]}" --jq .body
}

notes_from_git() {
  echo "## Merged pull requests"
  echo
  git log --first-parent --format='%s' "$RANGE" |
    grep -E '\(#[0-9]+\)$' |
    sed -E "s/^(.*) \(#([0-9]+)\)$/- \1 ([#\2](https:\/\/github.com\/${REPO//\//\\/}\/pull\/\2))/" || true
}

if [[ "$VERSION" != "unreleased" ]] && command -v gh >/dev/null && gh auth status >/dev/null 2>&1; then
  BODY="$(notes_from_github)"
else
  BODY="$(notes_from_git)"
fi
# GitHub's generator titles sections "## What's Changed"; one level down fits here.
BODY="$(printf '%s\n' "$BODY" | sed -E 's/^## /### /')"

if [[ "$VERSION" == "unreleased" ]]; then
  SECTION="$(printf '## Unreleased\n\nOn main, not yet in production (as of %s).\n\n%s\n' "$TODAY" "$BODY")"
else
  SECTION="$(printf '## %s (%s)\n\n%s\n' "$VERSION" "$TODAY" "$BODY")"
fi
HEADER="# Changelog

Every production release, newest first. Each section is generated from the merged pull
requests (infra/scripts/changelog.sh); see docs/release.md.
"

if [[ -f CHANGELOG.md ]] && grep -q "^## ${VERSION} " CHANGELOG.md; then
  echo "CHANGELOG.md already has ${VERSION}" >&2
  exit 1
fi
{
  printf '%s\n' "$HEADER"
  printf '%s\n\n' "$SECTION"
  if [[ -f CHANGELOG.md ]]; then
    # Keep earlier releases (from the first "## v" heading on); a release replaces
    # the Unreleased section.
    sed -n '/^## v/,$p' CHANGELOG.md
  fi
} >CHANGELOG.md.new
mv CHANGELOG.md.new CHANGELOG.md
echo "CHANGELOG.md: added ${VERSION} (${RANGE})"
