# Configuration decisions

Copy to `<your-project>/.claude/audit/decisions.md`. **This file belongs to the project, never to
the plugin** — the plugin is the same bytes in every project that installs it.

Only what does not attach to a single check belongs here. A warning this project decided to accept
is recorded as an exemption in `.claude/audit.local.json`, with its `reason` and its `date`: that
puts the decision at the exact place the model looks when the check fires, and check 31 keeps the
shape honest.

Run-by-run results are not written here either — `audit.py --record` appends them to
`.claude/audit/history.jsonl`. A journal entrusted to a model is forgotten, and when it is not
forgotten it is embellished. The script records what it measured; this file records what was
decided.

| Date | Decision | Why | Revisit when |
| --- | --- | --- | --- |
| 2026-01-01 | *(example)* No `PostToolUse` hook | per-edit hooks add time to every task | a hook that only measures is proposed |
