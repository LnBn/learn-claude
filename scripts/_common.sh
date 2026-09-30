#!/usr/bin/env bash
# Shared helpers for render-mermaid.sh / render-svg.sh.
#
#   find_chrome            -> prints path of an installed Chrome/Chromium, or nothing
#   publish <png> <slug>   -> copies <png> into $PWD/viz as viz-<slug>-<timestamp>.png
#                             and prints "filename: ..." / "path: ..."
#
# Rendering is done in a per-call temp dir; only the PUBLISHED png ever lands in
# the project (which is meant to sit inside the Obsidian vault).

export PATH="/opt/local/bin:/usr/local/bin:/opt/homebrew/bin:$PATH"

CLAUDE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VIZ_DIRNAME="viz"

find_chrome() {
  local c
  for c in google-chrome google-chrome-stable chromium chromium-browser chrome; do
    if command -v "$c" >/dev/null 2>&1; then command -v "$c"; return 0; fi
  done
  for c in "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" \
           "/Applications/Chromium.app/Contents/MacOS/Chromium" \
           "$HOME/.cache/puppeteer"/chrome/*/chrome-linux64/chrome; do
    if [ -x "$c" ]; then echo "$c"; return 0; fi
  done
  return 1
}

slugify() {
  echo "$1" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//'
}

publish() {
  local png="$1" slug; slug="$(slugify "${2:-viz}")"; [ -n "$slug" ] || slug="viz"
  local dir="$PWD/$VIZ_DIRNAME"; mkdir -p "$dir"
  local name="viz-${slug}-$(date +%s%3N).png"
  cp "$png" "$dir/$name"
  echo "Published to $VIZ_DIRNAME/."
  echo "filename: $name"
  echo "path: $dir/$name"
}
