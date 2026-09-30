---
name: md-unlog
description: Stop mirroring this session to the linked markdown file.
disable-model-invocation: true
allowed-tools: Bash(python3 .claude/hooks/md_log.py *)
---

Run exactly:

```
python3 .claude/hooks/md_log.py unlink --session ${CLAUDE_SESSION_ID}
```

Then reply with ONLY the single line the script printed that starts with `🗒 md-log`.
