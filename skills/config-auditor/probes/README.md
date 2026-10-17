# Probes

`evidence.json` records, for some checks, a fact measured on a given Claude Code
version (`tested*` entries: date, version, method, result). `run_probes.py` replays the
ones whose method is written precisely enough to repeat without guessing, against the
`claude` binary on this machine, and says whether the recorded result still holds.

```sh
python3 skills/config-auditor/probes/run_probes.py --list       # what exists, runs nothing
python3 skills/config-auditor/probes/run_probes.py --no-model   # free probes only
python3 skills/config-auditor/probes/run_probes.py              # all, including billed runs
```

Each line reads `PASS`, `FAIL`, `ERROR` or `SKIP`, the check id, the evidence entry and
the version it was recorded on; the first line is `claude --version`. A `FAIL` means the
reference may be stale for this version: re-read the documentation before changing the
check. An `ERROR` means the probe could not run as written, which says nothing about the
fact: a timeout, a binary that prints nothing or does not know the subcommand, a model
that did not make the calls asked for, or a probe that tries more `claude` calls than it
declares. The run ends with the tests left out and why, and the number of `claude` calls.
`--only` takes check ids; one that names no probe exits 2 and runs nothing.

| Check | Entry | Calls | Model |
| --- | --- | --- | --- |
| `44-plugin-path` | `tested` | 4 × `claude plugin validate` | no |
| `43-mcp-shape` | `tested` | 1 × `claude mcp list` | no |
| `35-hooks-shape` | `tested` | 2 × `claude -p` | haiku |
| `23-agent-tools` | `tested_taskoutput` (first agent only) | 1 × `claude -p` | haiku |
| `42-permissions-rule` | `tested_mid_colon_star` (`git status` and the control) | 2 × `claude -p` | haiku |
| `35-hooks-matcher` | `tested` (`Bash(git *)\|Write`, `Write\|Edit(*.ts)`, each with a `Bash\|Write` control) | 2 × `claude -p` | haiku |
| `frontmatter-bom` | `tested` (skill, agent and path-scoped rule behind a BOM, each with a twin) | 1 × `claude -p` | haiku |
| `35-hooks-shape` | `tested_skill_hooks_empty` (`hooks: []` in a skill) | 1 × `claude -p` | haiku |
| `01-claude-md-import-syntax` | `tested` (25 `@path` spellings in one CLAUDE.md, and a six-file import chain) | 1 × `claude -p` | haiku |

The model probes read facts from the stream (`init.skills`, `init.agents`, `tool_use`,
`tool_result`, `permission_denials`) and from command hooks that append their input to a
log inside the temporary folder (`PreToolUse` tool names, `InstructionsLoaded` load
reasons); one fact, the quoted skill description of `frontmatter-bom`, is the model's own
account. Cost measured on 2.1.302: about $0.002 per Haiku run.

Safety: every probe works in its own temporary directory, deleted afterwards (`--keep`
keeps it, with each run's stream in `probe-stream.jsonl`). Probes without a model also get
a temporary `CLAUDE_CONFIG_DIR`. Model probes use the binary's own login - the script
never reads credentials - with `--setting-sources project`, `--strict-mcp-config`,
`--no-session-persistence`, `--max-budget-usd 0.25` and a timeout; `--isolate-config` gives
them a temporary `CLAUDE_CONFIG_DIR` too, for a machine whose credentials are in the
environment. Without `claude` on `PATH`, every probe is `SKIP` and the exit status is 0.
Measured on 2.1.302: even with `--no-session-persistence`, each model run leaves a
`~/.claude/projects/<temporary path>/` folder (an empty `memory/`) behind; with
`--isolate-config` it should land in the temporary folder instead (not measured).

`tests/test_probes.py` holds these properties with a fake binary: no write outside the
temporary folder, nothing under `HOME`, a temporary `CLAUDE_CONFIG_DIR` for every local
call, a timeout on every call, no billed call under `--no-model`, no more calls than each
probe declares, and each probe's PASS on the recorded behaviour and FAIL on its opposite.

Adding a probe: record the test in `evidence.json` first (method and result), then add a
function and a `Probe` entry; `tests/test_probes.py` fails while a `tested*` entry is
neither a probe nor listed in `NOT_IMPLEMENTED` with a reason.
