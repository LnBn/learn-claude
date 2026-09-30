#!/usr/bin/env bash
# Render a hand-written SVG file to PNG (2x for crispness).
#
#   render-svg.sh <picture.svg>                  preview: prints the PNG path to LOOK at
#   render-svg.sh <picture.svg> --publish <slug>  also copies it into $PWD/viz with a
#                                                 unique name and prints filename/path
#
# Renderer order: rsvg-convert -> magick (IM7) -> convert (IM6) -> headless Chrome.
set -u
source "$(dirname "${BASH_SOURCE[0]}")/_common.sh"

src="${1:-}"; shift || true
[ -n "$src" ] && [ -f "$src" ] || { echo "usage: render-svg.sh <picture.svg> [--publish <slug>]" >&2; exit 2; }
slug=""
while [ $# -gt 0 ]; do
  case "$1" in
    --publish) slug="${2:-viz}"; shift 2;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

work="$(mktemp -d "${TMPDIR:-/tmp}/learn-svg.XXXXXX")"
out="$work/render.png"; log="$work/log"; : > "$log"

# Basic well-formedness check first: renderers are lenient and can silently draw nothing.
if command -v python3 >/dev/null 2>&1; then
  if ! python3 -c 'import sys,xml.dom.minidom; xml.dom.minidom.parse(sys.argv[1])' "$src" 2>>"$log"; then
    echo "RENDER FAILED: SVG is not well-formed XML: $(tail -1 "$log")" >&2; exit 1
  fi
fi

try() { "$@" >>"$log" 2>&1 && [ -s "$out" ]; }
ok=0
if command -v rsvg-convert >/dev/null 2>&1; then try rsvg-convert -z 2 -b white "$src" -o "$out" && ok=1; fi
if [ $ok = 0 ] && command -v magick >/dev/null 2>&1; then try magick -density 192 -background white "$src" "$out" && ok=1; fi
if [ $ok = 0 ] && command -v convert >/dev/null 2>&1; then try convert -density 192 -background white "$src" "$out" && ok=1; fi
if [ $ok = 0 ]; then
  chrome="$(find_chrome || true)"
  if [ -n "$chrome" ]; then
    # Read width/height (or viewBox) so the screenshot window matches the picture.
    dims="$(python3 - "$src" <<'PY'
import re,sys
s=open(sys.argv[1]).read()
def num(a):
    m=re.search(r'\b%s="([\d.]+)'%a,s); return float(m.group(1)) if m else None
w,h=num('width'),num('height')
if not (w and h):
    m=re.search(r'viewBox="([\d.\s-]+)"',s)
    if m:
        p=m.group(1).split(); w,h=float(p[2]),float(p[3])
print(int(w or 800),int(h or 600))
PY
)"
    set -- $dims
    try timeout 60 "$chrome" --headless=new --no-sandbox --disable-gpu --hide-scrollbars \
        --force-device-scale-factor=2 --window-size="$1,$2" --screenshot="$out" "file://$(realpath "$src")" && ok=1
  fi
fi
if [ $ok = 0 ]; then
  echo "RENDER FAILED — no image produced (tried rsvg-convert, magick, convert, chrome). Fix the source and re-run." >&2
  cat "$log" >&2; exit 1
fi
echo "Rendered OK: $out"
echo "Now LOOK at it with the Read tool before deciding it is correct."
if [ -n "$slug" ]; then publish "$out" "$slug"; fi
