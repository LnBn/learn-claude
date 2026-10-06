#!/usr/bin/env python3
"""
Make block links (`[[#^fig-1-4]]`, `[[#^eq-2-51]]`, `[[#^ex-3]]`) jump in PDFs exported with the Obsidian
plugin Better Export PDF (l1xnan/obsidian-better-export-pdf, 2.0.x).

The plugin turns a heading link into a PDF jump: each heading gets a hidden `af://<id>` anchor, each link to
it becomes `an://<id>`, and after printing it rewrites every `an://` link annotation into a GoTo to the
position of the matching `af://` annotation. Block ids get a `<span class="blockid">` but no `af://` anchor,
and block links stay `#^id`, which leads nowhere in a PDF. This patch gives every block span an
`af://blk-<id>` anchor and points block links at `an://blk-<id>`.

    patch-better-export-pdf.py [<vault>]     (default: the vault this .claude directory sits in)

Idempotent; keeps the original as main.js.orig. Re-run after the plugin updates.
"""
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MARK = "/* learn-claude: block anchors */"
# link rewrite: block links are skipped by `!o.startsWith(`^`)`; give them an an:// target instead
LINK_OLD = "i&&!o.startsWith(`^`)&&(e.href=`an://${i}`)"
LINK_NEW = ("o.startsWith(`^`)?(e.href=`an://blk-${o.slice(1).toLowerCase()}`):i&&(e.href=`an://${i}`)")
# the same function walks the rendered note first: add an af:// anchor to every block span
FUNC_OLD = "function Ga(e,t,n){let r=Wa(t);"
FUNC_NEW = (FUNC_OLD + MARK + "e.querySelectorAll(`span.blockid`).forEach(s=>{if(s.querySelector(`a.md-print-anchor`))"
            "return;let a=document.createElement(`a`);a.href=`af://blk-${s.id.replace(/^\\^/,``).toLowerCase()}`;"
            "a.className=`md-print-anchor`;s.appendChild(a)});")


def main(argv):
    vault = os.path.abspath(argv[1]) if len(argv) > 1 else os.path.dirname(os.path.dirname(HERE))
    path = os.path.join(vault, ".obsidian", "plugins", "better-export-pdf", "main.js")
    if not os.path.isfile(path):
        print(f"not found: {path} (is Better Export PDF installed in this vault?)", file=sys.stderr)
        return 1
    with open(path, encoding="utf-8") as f:
        src = f.read()
    if MARK in src:
        print("already patched")
        return 0
    if src.count(LINK_OLD) != 1 or src.count(FUNC_OLD) != 1:
        print("this version of the plugin is not the one the patch was written for; nothing changed", file=sys.stderr)
        return 1
    shutil.copyfile(path, path + ".orig")
    src = src.replace(FUNC_OLD, FUNC_NEW).replace(LINK_OLD, LINK_NEW)
    with open(path, "w", encoding="utf-8") as f:
        f.write(src)
    print(f"patched {path} (original kept as main.js.orig). Reload Obsidian or toggle the plugin off and on.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
