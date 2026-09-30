#!/usr/bin/env bash
# One-time setup: install the bundled mermaid-cli (for the mermaid-maker agent).
# SVG rendering needs no install if rsvg-convert, ImageMagick or Chrome is present.
set -e
CLAUDE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
source "$CLAUDE_DIR/scripts/_common.sh"
chrome="$(find_chrome || true)"
cd "$CLAUDE_DIR/visual-tools"
if [ -n "$chrome" ]; then
  echo "Using installed browser: $chrome (skipping puppeteer's Chromium download)"
  PUPPETEER_SKIP_DOWNLOAD=1 npm install --no-audit --no-fund
else
  echo "No Chrome/Chromium found; letting puppeteer download one."
  npm install --no-audit --no-fund
fi
echo
echo "SVG renderers available:"
for c in rsvg-convert magick convert; do command -v $c >/dev/null 2>&1 && echo "  $c: $(command -v $c)"; done
[ -n "$chrome" ] && echo "  chrome fallback: $chrome"
echo
echo "Smoke test:"
tmp="$(mktemp -d)"; printf 'graph TD\n  A[truth] --> B[derived]\n' > "$tmp/t.mmd"
bash "$CLAUDE_DIR/scripts/render-mermaid.sh" "$tmp/t.mmd" | head -1
printf '<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100"><rect width="200" height="100" fill="white"/><circle cx="100" cy="50" r="20" fill="crimson"/></svg>' > "$tmp/t.svg"
bash "$CLAUDE_DIR/scripts/render-svg.sh" "$tmp/t.svg" | head -1
echo "Done."
