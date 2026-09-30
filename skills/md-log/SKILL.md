---
name: md-log
description: Link a markdown file (e.g. a note inside your Obsidian vault) and mirror this session into it — your prompts, the lesson prose, and every quiz/question with its answer. Backfills the session so far.
argument-hint: <path/to/lesson.md>
disable-model-invocation: true
allowed-tools: Bash(python3 .claude/hooks/md_log.py *)
---

Link the markdown log for this session by running exactly this command (do not modify the path the user gave; expand `~` is fine):

```
python3 .claude/hooks/md_log.py link "$ARGUMENTS" --session ${CLAUDE_SESSION_ID}
```

If `$ARGUMENTS` is empty, ask for the file path with AskUserQuestion, or default to `./lessons/<today>-lesson.md` if the user says to pick one.

Then reply with ONLY the single line the script printed that starts with `🗒 md-log linked:` — nothing else. From now on, remember that everything you write is being read rendered in Obsidian: markdown, LaTeX (`$…$` / `$$…$$`), mermaid code blocks and `![[image.png|500]]` embeds all render there.
