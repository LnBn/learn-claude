#!/usr/bin/env bash
# Render a Mermaid source file to PNG.
#
#   render-mermaid.sh <diagram.mmd>                 preview: prints the PNG path to LOOK at
#   render-mermaid.sh <diagram.mmd> --publish <slug> also copies it into $PWD/viz with a
#                                                    unique name and prints filename/path
#
# Uses the mermaid-cli bundled under .claude/visual-tools (run scripts/install.sh once),
# driven through an installed Chrome/Chromium so nothing is downloaded at render time.
set -u
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

src="${1:-}"; shift || true
[ -n "$src" ] && [ -f "$src" ] || { echo "usage: render-mermaid.sh <diagram.mmd> [--publish <slug>]" >&2; exit 2; }
slug=""
while [ $# -gt 0 ]; do
  case "$1" in
    --publish) slug="${2:-viz}"; shift 2;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

MMDC="$CLAUDE_DIR/visual-tools/node_modules/.bin/mmdc"
if [ ! -x "$MMDC" ]; then
  echo "RENDER FAILED: mermaid-cli not installed. Run: bash $CLAUDE_DIR/scripts/install.sh" >&2; exit 1
fi

work="$(mktemp -d "${TMPDIR:-/tmp}/learn-mermaid.XXXXXX")"
chrome="$(find_chrome || true)"
if [ -n "$chrome" ]; then
  printf '{"executablePath":"%s","args":["--no-sandbox","--disable-gpu"]}' "$chrome" > "$work/puppeteer.json"
else
  printf '{"args":["--no-sandbox","--disable-gpu"]}' > "$work/puppeteer.json"
fi
out="$work/render.png"
if ! timeout 120 "$MMDC" -p "$work/puppeteer.json" -i "$src" -o "$out" -b white -s 2 >"$work/log" 2>&1 || [ ! -s "$out" ]; then
  echo "RENDER FAILED (mermaid syntax or renderer error). Fix the source and re-run." >&2
  echo "--- mmdc output ---" >&2; grep -v "^Generating" "$work/log" | grep -v "^ *at " | sed '/^Parser\.parseError/q' >&2; exit 1
fi
echo "Rendered OK: $out"
echo "Now LOOK at it with the Read tool before deciding it is correct."
if [ -n "$slug" ]; then publish "$out" "$slug"; fi
