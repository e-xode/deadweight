# Runtime data — what the sessions know that the files do not

> Examples use a fictional online shop (`shop-api`). Quotes are from the Claude Code
> documentation; measurements are dated, with the version. Sources:
> [hooks](https://code.claude.com/docs/en/hooks), [skills](https://code.claude.com/docs/en/skills),
> [monitoring](https://code.claude.com/docs/en/monitoring-usage), [sessions](https://code.claude.com/docs/en/sessions).

## Contents

- What the files cannot say
- The sources, and which one the audit reads
- Recording the log (a hook you place yourself)
- Reading it: `audit.py --runtime`
- What a log proves, and what it does not

## What the files cannot say

Every other check reads files. Three questions have no answer in them:

- a `.claude/rules/*.md` whose `paths:` match real files **nobody opens** — `22-rule-glob-match`
  sees the glob match, and the rule still never loads;
- a nested `CLAUDE.md` in a folder nobody works in;
- a rule the audit reads as path-scoped that the harness **loads at session start anyway**.

## The sources, and which one the audit reads

| Source | What the documentation says | Read by the audit |
| --- | --- | --- |
| `InstructionsLoaded` hook | "Fires when a `CLAUDE.md` or `.claude/rules/*.md` file is loaded into context", with `file_path`, `memory_type`, `load_reason` ("`session_start`, `nested_traversal`, `path_glob_match`, `include`, or `compact`"), `globs`, `trigger_file_path`, `parent_file_path` (hooks) | **yes**, through `--runtime` |
| `/skill-doctor` | "see what each of your skills costs and how often it gets used"; with `-p`, "Claude Code prints it as text" (skills) — no file export, no documented format | no — step 2 of the audit method, read by you |
| `claude_code.skill_activated` | an OpenTelemetry event (monitoring) — needs an exporter and a backend | no |
| Session transcripts | "The entry format is internal to Claude Code and changes between versions, so scripts that parse these files directly can break on any release" (sessions) | no, by the documentation's own warning |

The hook is the only source that is documented field by field and written for this use:
"Use this event for audit logging, compliance tracking, or observability." It "doesn't
support blocking or decision control", runs asynchronously, and Claude Code "discards
their JSON output fields" — it costs no context.

What it does not see: it "doesn't fire when Claude reads `AGENTS.md` directly"; it does
when a `CLAUDE.md` imports `AGENTS.md`. Skills are not instruction files and never appear.

## Recording the log (a hook you place yourself)

**This plugin never places a hook for you** — hooks execute, and placing one is the
maintainer's decision (core rule 10). Add this to the project's `.claude/settings.local.json`
(yours alone) or `.claude/settings.json` (the team's):

```json
{
  "hooks": {
    "InstructionsLoaded": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 -c \"import json,os,sys,time; d=json.load(sys.stdin); d['ts']=time.strftime('%Y-%m-%dT%H:%M:%S'); p=os.path.join(os.environ.get('XDG_CACHE_HOME') or os.path.expanduser('~/.cache'), 'claude-audit', 'loads'); os.makedirs(p, exist_ok=True); open(os.path.join(p, os.path.basename(os.path.normpath(os.environ.get('CLAUDE_PROJECT_DIR') or d['cwd'])) + '.jsonl'), 'a', encoding='utf-8').write(json.dumps(d) + chr(10))\""
          }
        ]
      }
    ]
  }
}
```

It appends one line per load, with a timestamp the event does not carry, to
`~/.cache/claude-audit/loads/<project folder>.jsonl` — **outside the repository**, on
purpose: each line holds absolute paths, your user `~/.claude/CLAUDE.md` included. Where the
interpreter is `python` rather than `python3`, change the first word.

Measured on Claude Code 2.1.284 (2026-09-29), one session of `shop-api` reading
`src/api/refunds.ts`: five lines — the user and project `CLAUDE.md` (`session_start`), the
file it imports (`include`, with `parent_file_path`), `src/api/CLAUDE.md`
(`nested_traversal`) and `.claude/rules/api.md` (`path_glob_match`, triggered by the file
read). Two things the documentation does not say: `globs` arrives normalised (`["src/api"]`
for `src/api/**`), and `.claude/rules/infra.md`, whose glob matched nothing read, left **no
line at all**.

## Reading it: `audit.py --runtime`

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/audit.py --runtime ~/.cache/claude-audit/loads/shop-api.jsonl
```

| Check | Says |
| --- | --- |
| `57-runtime-log` (INFO) | sessions, dates and files of this repository in the log; lines it skipped |
| `57-runtime-never-loaded` (NOTICE) | a rule with `paths:`, or a nested `CLAUDE.md`, that loaded in none of the recorded sessions |
| `57-runtime-rule-unscoped` (NOTICE) | a rule with `paths:` that loaded at `session_start`: the harness did not read it as path-scoped |

Lines about files outside the audited repository are ignored. Without `--runtime`, none of
these runs and the report is unchanged.

## What a log proves, and what it does not

- **A load is a fact; an absence is an inference.** A file that never loads leaves nothing,
  so "never loaded" is only said over at least 5 sessions (`RUNTIME_MIN_SESSIONS`), with
  their count and dates. Fewer, and the audit says why it says nothing.
- **The log covers the work that was done.** A rule for release week, silent for the three
  weeks recorded, is not dead. The finding asks a question; the maintainer answers it.
- **NOTICE, not WARN.** These checks have not yet been measured against logs from real
  projects; until they are, they are counted by no floor.
