"""A throwaway vault for tests: <tmp>/.claude/hooks is a copy of this repo's hooks, so every script resolves its
state directory to <tmp>/.claude/md-log-state and never touches the real one. (A symlink would not do: Python
resolves the script's directory, so the modules a script imports would find the repo's state directory.)"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "hooks"))


def make_vault(test: unittest.TestCase | None = None) -> Path:
    vault = Path(tempfile.mkdtemp(prefix="learn-vault-"))
    (vault / ".claude").mkdir()
    shutil.copytree(REPO / "hooks", vault / ".claude" / "hooks", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(REPO / "mcp", vault / ".claude" / "mcp", ignore=shutil.ignore_patterns("__pycache__"))
    (vault / ".claude" / "md-log-state").mkdir()
    if test is not None:
        test.addCleanup(shutil.rmtree, vault, True)
    return vault


def run(vault: Path, script: str, *args: str, stdin: str | None = None,
        env: dict | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "CLAUDE_CONFIG_DIR": str(vault / "config"), **(env or {})}
    return subprocess.run([sys.executable, str(vault / ".claude" / "hooks" / script), *args], cwd=vault,
                          input=stdin, capture_output=True, text=True, env=env, timeout=60)


def hook(vault: Path, payload: dict) -> subprocess.CompletedProcess:
    return run(vault, "md_log.py", stdin=json.dumps(payload))


def transcript(vault: Path, session: str) -> Path:
    tp = vault / "config" / "projects" / "p" / f"{session}.jsonl"
    tp.parent.mkdir(parents=True, exist_ok=True)
    tp.touch()
    return tp


def user(text: str) -> dict:
    return {"type": "user", "message": {"role": "user", "content": text}}


def assistant(msg_id: str, text: str | None = None, tool: str | None = None) -> dict:
    content = []
    if text is not None:
        content.append({"type": "text", "text": text})
    if tool is not None:
        content.append({"type": "tool_use", "id": f"tu-{msg_id}", "name": tool, "input": {}})
    return {"type": "assistant", "message": {"id": msg_id, "role": "assistant", "content": content}}


def tool_result(tool_use_id: str) -> dict:
    return {"type": "user", "message": {"role": "user", "content": [
        {"type": "tool_result", "tool_use_id": tool_use_id, "content": "ok"}]}}


def append(tp: Path, *entries: dict) -> None:
    with open(tp, "a", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


def _entry(id_, title, kind, level, chapter, start, end):
    return {"id": id_, "title": title, "kind": kind, "level": level, "chapter": chapter, "start": start,
            "end": end, "starred": False, "exercises": False, "mid_start": False, "mid_end": False}


def make_course(vault: Path, slug: str = "pml1") -> Path:
    cdir = vault / "courses" / slug
    (cdir / ".course").mkdir(parents=True)
    entries = [
        _entry("1", "Introduction", "chapter", 1, "1", 10, 29),
        _entry("1.1", "What is learning", "section", 2, "1", 10, 19),
        _entry("1.2", "Supervised learning", "section", 2, "1", 20, 29),
        _entry("2", "Probability: univariate models", "chapter", 1, "2", 30, 59),
        _entry("2.1", "Intro", "section", 2, "2", 30, 39),
        _entry("2.2", "Rules", "section", 2, "2", 40, 49),
        _entry("2.3", "Bayes' rule", "section", 2, "2", 50, 59),
    ]
    book = {"pdf": str(vault / "book.pdf"), "pages": 100, "generated_ids": False, "labels": None, "offset": 0,
            "entries": entries}
    state = {"slug": slug, "title": "Probabilistic Machine Learning", "syllabus": ["1.1", "1.2", "2.1", "2.2", "2.3"],
             "status": {}, "exercises": {}}
    (cdir / ".course" / "book.json").write_text(json.dumps(book), encoding="utf-8")
    (cdir / ".course" / "state.json").write_text(json.dumps(state), encoding="utf-8")
    (vault / ".claude" / "md-log-state" / "course.json").write_text(json.dumps({"course": str(cdir)}), encoding="utf-8")
    return cdir


def set_status(cdir: Path, **units: tuple[str, str]) -> None:
    """set_status(cdir, **{"2.1": ("done", "2026-10-05")})"""
    p = cdir / ".course" / "state.json"
    st = json.loads(p.read_text(encoding="utf-8"))
    for uid, (s, at) in units.items():
        st["status"][uid] = {"s": s, "at": at}
    p.write_text(json.dumps(st), encoding="utf-8")


def write_note(path: Path, headings: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(f"### {h}\n\nText about {h}.\n\n" for h in headings), encoding="utf-8")
