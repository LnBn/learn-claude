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
# Register the quiz MCP server for this project (project-scope .mcp.json lives at the project root).
PROJECT_DIR="$(dirname "$CLAUDE_DIR")"
if [ ! -e "$PROJECT_DIR/.mcp.json" ]; then
  cp "$CLAUDE_DIR/mcp.json" "$PROJECT_DIR/.mcp.json"
  echo "Wrote $PROJECT_DIR/.mcp.json (quiz MCP server). Claude Code will ask once to enable it."
else
  echo "NOTE: $PROJECT_DIR/.mcp.json already exists — merge the 'quiz' entry from $CLAUDE_DIR/mcp.json into it."
fi
# Callout styles for the lesson environments (definition, theorem, notation, …).
if [ -d "$PROJECT_DIR/.obsidian" ]; then
  mkdir -p "$PROJECT_DIR/.obsidian/snippets"
  cp "$CLAUDE_DIR/obsidian/learn-callouts.css" "$PROJECT_DIR/.obsidian/snippets/learn-callouts.css"
  python3 - "$PROJECT_DIR/.obsidian/appearance.json" <<'PY'
import json, sys, os
p = sys.argv[1]
d = json.load(open(p)) if os.path.exists(p) else {}
s = d.setdefault("enabledCssSnippets", [])
if "learn-callouts" not in s:
    s.append("learn-callouts")
json.dump(d, open(p, "w"), indent=2)
PY
  echo "Installed and enabled the Obsidian CSS snippet learn-callouts (restart Obsidian if styles do not show)."
fi
echo "Done."
