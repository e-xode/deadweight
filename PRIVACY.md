# Privacy

Deadweight reads the Claude Code configuration of the project you run it in, and prints what it finds.
The maintainer receives nothing: no telemetry, no analytics, no account. This page says what runs on your
machine, what it reads, writes and keeps, and the only two commands that send anything anywhere, both
through your own Claude Code session. The code is public: every statement below can be checked in it.

## Network

The code that runs on your machine (`hooks/`, `bin/`, `skills/config-auditor/scripts/`,
`skills/config-auditor/templates/`) imports no network library (`urllib.parse` only decodes the links
written in your files) and starts no program other than Python itself, `git` and `claude`. Only
`claude`, under the two commands of "What it sends", reaches a network.

`git` is run in the project (`ls-files`, `check-ignore`) four times, each with `-c core.fsmonitor=false`
since 0.28.0, so the program a repository's own `.git/config` names there is not run. Until 0.27.0 it was:
measured with git 2.53.0, a test repository and a harmless witness script, all four calls the audit makes
ran it (`tests/test_git_fsmonitor.py` holds the fix, and fails if a git call written as a literal list in the shipped code lacks it before the subcommand; a call assembled another way, such as a string run through a shell, is not seen by that test).
A clone does not carry that setting; a `.git/` folder received as files can. Two of the calls also pass
`-c core.excludesFile=` (empty), so a global ignore file on your machine does not change what counts as
ignored, and one sets `LC_ALL=C` and `LANGUAGE=C` for git, to read its error message. No other git setting
is overridden.

`--semantic` and `--environment --measure` start Claude Code, which runs git itself in the folder it runs in
(`status`, `log`, `ls-files`, `remote`, `config`, in a run whose only reply was "OK"): that is Claude Code's
behaviour, not this plugin's, and it is not under this plugin's control. Measured on Claude Code 2.1.306,
with a logging `git` first in the `PATH` and the same witness, once with `--semantic`'s flags and once
with those of `--measure`'s first run (plus `--no-session-persistence`): each git call carried Claude
Code's own `-c core.fsmonitor=` and `-c core.hooksPath=/dev/null`, and the witness did not run. A later
release may differ. To repeat the shorter form of this measurement (no wrapper, so it shows the witness did not
run, not which options git received), in a throwaway repository: set `core.fsmonitor` to a script that
creates a file; run a plain `git status` and check the file exists; delete it; then run `claude -p --model
haiku --no-session-persistence --setting-sources project "Reply with the single word ok."` in that folder
and check it does not exist again. Without the deletion the second check proves nothing. This gave
"created", then "not created" on Claude Code 2.1.309, 2026-10-23. In a real repository
`--setting-sources project` would load that project's own settings and hooks, which is why the repository
must be a throwaway one. It is a billed model call, and it is not one of
`probes/run_probes.py`'s probes, which replay what `evidence.json` records for a check.

## What it reads

- **The audit** (`audit.py`, the `deadweight` command, the session-start hook) reads, in the project:
  `CLAUDE.md`, `.claude/CLAUDE.md`, `CLAUDE.local.md`, `AGENTS.md`, `.claude/` (the overlay
  `.claude/audit.local.json` included), `.mcp.json`, `evals/`, plugin manifests and the files they name,
  `.vscode/settings.json` (one key), the `package.json`, `Makefile`, `*.mk` and `justfile` files git
  tracks (their script, target and recipe names), `.cursor/rules/` (the frontmatter), and the names of
  other agents' files (`.cursorrules`, `.github/copilot-instructions.md`, `.github/instructions/`,
  `AGENTS.override.md`). It asks `git` which files the repository tracks and ignores.
- **Outside the project**, the audit reads: the targets of symbolic links under the folders it reads,
  wherever they point; the files of `@path` imports where Claude Code follows them, up to four hops,
  including a relative path that leaves the project (`@../shared.md`), not `@~/` or absolute imports;
  the existence of a file a hook or status line command names in your home folder or by absolute path;
  and, only with `--runtime LOG`, that log file.
- **The status line** reads the cached report (below), `.claude/audit/floor.json`, the modification times
  of the files under `.claude/` and of `CLAUDE.md`, the JSON Claude Code sends it on standard input, and,
  to say that an update is available, Claude Code's plugin bookkeeping under `$CLAUDE_CONFIG_DIR/plugins/`
  or `~/.claude/plugins/` (`installed_plugins.json`, `known_marketplaces.json`, and the `marketplace.json`
  at the `installLocation` it names), or Copilot CLI's `installed-plugins/` folder. The `deadweight`
  command reads the same files and the plugin's own `precision.json`.
- **`deadweight --environment`** (estimate, no model) reads your user configuration in `CLAUDE_CONFIG_DIR`
  or `~/.claude`: `CLAUDE.md`, the rules and the files they import (`~/` and absolute imports included),
  `settings.json`, skills, agents, output styles, `plugins/installed_plugins.json`, synced plugins, and the
  folders of the installed plugins enabled for the project (their `.mcp.json` server names and the source
  of their mods' hooks modules, read as text, never run); and, in the project, its memory files, skills,
  agents, `.claude/settings.json` and `.claude/settings.local.json`, and the server names of `.mcp.json`
  (only the names are kept). It refuses a file named exactly `.claude.json`, `.credentials.json` or
  `.env`, or reached through a symbolic link to one, or a hard link to the configuration's `.claude.json`
  or `.credentials.json`. Any other name a memory file imports, `.env.local` included, is read and counted.
- **Environment variables read**: `CLAUDE_PROJECT_DIR`, `CLAUDE_PLUGIN_ROOT`, `CLAUDE_CONFIG_DIR`,
  `COPILOT_HOME`, `XDG_CACHE_HOME`; `DEADWEIGHT_SEMANTIC_NO_CACHE` (turns a cache off) and
  `DEADWEIGHT_SEMANTIC_RESPONSE` (a file whose content replaces the model's answer: a test hook that reads
  whatever file it names). Set by the plugin, for its own child processes only: `CLAUDE_PROJECT_DIR` and
  `CLAUDE_PLUGIN_ROOT` for the hook that `deadweight --fresh` runs, `LC_ALL=C` and `LANGUAGE=C` for one
  `git` call.

A finding's message quotes paths, line numbers, key names and some values of your configuration: the
file a hook command runs, permission rules, `additionalDirectories` entries, MCP server names, the URL of
a plain-http MCP server without its query string, the `@path` written at an import. For a value that
looks like a credential it names the key (`env.<NAME>`, `headers.<NAME>`), never the value. A finding
about an imported file outside the project gives its path, never its content.

## What it writes

- **The audit** writes nothing, unless you ask it to (`--set-floor` writes `.claude/audit/floor.json`).
- **The session-start hook** creates `${XDG_CACHE_HOME:-~/.cache}/claude-audit/` if needed and writes one
  file there: `<project folder name>-<first 8 hex digits of the md5 of its path>.json`, through a temporary
  `*.tmp` file in the same folder that a failed write can leave behind. It holds the project folder name,
  the counts, the auditor's sha, the plugin version, the layout, the time, and every finding with its
  message and location. `deadweight` and `deadweight --fresh` (which runs the hook again) show that file.
- **`deadweight --setup-statusline`**, only when you run it, writes in each host it finds:
  - Claude Code (`CLAUDE_CONFIG_DIR` or `~/.claude` exists): the `statusLine` key of
    `.claude/settings.json`, then the launcher `.claude/statusline.py`, in your project.
  - Copilot CLI (`$COPILOT_HOME` or `~/.copilot` exists): the `statusLine` key of `settings.json`, then
    the launcher `deadweight-statusline.py`, in that folder - a user setting, for every project.

  A settings file that already has another `statusLine`, or is not plain JSON, is left untouched, and so
  is a file already at the launcher's path (until 0.27.0 the launcher was written first and replaced it).
  Otherwise the whole settings file is written back as `json.dumps(indent=2)`, so its formatting changes,
  and the launcher is written, replacing a regular file already there. The launcher is first written to a
  `.statusline-*` temporary file in the same folder (the project's `.claude/`, or the Copilot folder),
  made executable, then moved over its destination; the temporary file is removed on any failure or
  interruption, and only a kill or a power cut can leave it. In a folder that takes no new file the launcher
  is written in place, and the launcher that was there is put back if that fails. If the launcher cannot be written (its path is a folder, a symbolic link or a
  read-only file), the settings file is put back as it was (removed if there was none) and the command
  exits 3; the other host is still set up. A settings file that cannot be written (read-only, or the
  folder being a file) is left untouched and the command exits 2; if the write failed after the file was
  opened, or was interrupted, its bytes are put back, and the message says whether that worked.
- **`semantic.py --method claims`** writes its cache (see "Retention").

## What it sends (only with `--semantic` or `--measure`)

Both run `claude` with **your own login**. Neither reads a token nor sets an environment variable for it;
what is sent to Anthropic goes through your account, under Anthropic's terms. `--semantic` passes
`--no-session-persistence` since 0.28.0: no session file is kept (measured on Claude Code 2.1.306: no
folder appeared under `~/.claude/projects/` for the run). Until 0.27.0 it did not, and `--measure` still
does not: Claude Code keeps each run as a session file, prompt included, under
`~/.claude/projects/<the folder's path, / replaced by ->/<session id>.jsonl` (measured on Claude Code
2.1.302, `CLAUDE_CONFIG_DIR` unset: the prompt was in that file; with `--no-session-persistence` no file
was written).

- **`deadweight --semantic`** (opt-in) runs `claude -p` (model `claude-sonnet-5-5`; `semantic.py --model`
  picks another) with no tools, no MCP server, no settings source and no session file (`--tools ""
  --strict-mcp-config --setting-sources "" --no-session-persistence`), in the folder you run the command from. With those flags, a `CLAUDE.md` in that
  folder is not loaded by Claude Code itself (measured on 2.1.302: a marker phrase in it was not seen;
  with `--setting-sources project` it was). It sends the project `CLAUDE.md` (block-level HTML comments
  removed, as Claude Code does), the rules, every `SKILL.md` and agent file - taken by name, whatever a
  symbolic link among them points to - and the Markdown files they point to, one hop away, whose
  real path is inside the repository; as found on disk, **files git ignores included**, each cut at
  20,000 characters. A request can also carry the path and `description` of every skill. `--json` lists
  the files sent under `files_sent`; that skill listing is not in it. `semantic.py --method claims`, an
  option of the script itself, sends every collected file for extraction while `files_sent` lists only
  the files of its comparison requests. Do not run it on a configuration you may not send. Details and
  cost: [`skills/config-auditor/references/semantic-layer.md`](skills/config-auditor/references/semantic-layer.md).
- **`deadweight --environment --measure`** (opt-in) runs `claude -p` four times (model `claude-haiku-5-5`;
  `environment.py --model` picks another) in the project with the prompt "Reply with the single word OK.",
  to measure what the configuration costs (a few cents), and asks first (or takes `--yes`). The tools are
  not turned off: what each session loads - memory files, skill listing, tool and MCP tool definitions -
  is what is sent, and measured. That is opening a Claude Code session in the folder without the trust
  dialog: the project's settings hooks run and the enabled plugins' mods load. The first two runs restrict
  settings sources and MCP servers; the third leaves the settings sources unrestricted, so your user and
  local settings apply, their hooks included; the fourth also drops `--strict-mcp-config`, so no MCP
  server configuration is excluded - the project's `.mcp.json` and yours.

`skills/config-auditor/probes/run_probes.py` is a maintainer and contributor tool, never run by the plugin
itself: it replays recorded facts with `claude -p --model haiku --no-session-persistence` in temporary
folders, and `--no-model` skips the runs that call a model.

## Retention

Nothing the plugin writes expires or is purged by it: the hook's file in
`${XDG_CACHE_HOME:-~/.cache}/claude-audit/` is replaced at each session of that project and stays after
it; the claims cache in `${XDG_CACHE_HOME:-~/.cache}/deadweight/claims/` keeps one `<sha>.json` per file
content (the extracted quotes), `topics-<model>.json` (the groupings) and `confirm-<sha>.json` (the
confirmed findings with their quotes, and the rejected ones). Delete those folders to remove them. Claude
Code's session files (above) are Claude Code's to keep or delete, not the plugin's.

## What the repository does on GitHub

The workflows in `.github/workflows/` run on GitHub's servers, not on your machine: the tests and the
portability tests, the release (a GitHub Release cut from this changelog), and a daily watch. The watch
reads the public npm registry, the public Claude Code changelog and the public Claude Code documentation
pages, then opens or edits an issue in this repository. If the repository's `GOOGLE_CHAT_WEBHOOK` secret
is set, it also posts that issue's title and URL to that Google Chat webhook. `.github/dependabot.yml` has
GitHub open a weekly pull request when an action the workflows use has a new version. They handle no
user data.

## The website and contact

The plugin has no account and no server. For the maintainer's website and the contact form, the policy is at
<https://www.e-xode.net/en/privacy-policy>. To ask a question about this page, open an issue at
<https://github.com/e-xode/deadweight/issues> or use <https://www.e-xode.net/en/contact>.

A change to what the plugin reads, writes or sends is a change to this page, in the same commit.

Last reviewed on version 0.28.0, 2026-10-21.
