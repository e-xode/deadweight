# The environment — what a session loads beyond the project's files

> Examples use a fictional online shop (shop-api). Quotes are from the Claude Code documentation;
> figures are measurements, dated, with the version. Sources:
> [plugins reference](https://code.claude.com/docs/en/plugins-reference),
> [mods reference](https://code.claude.com/docs/en/plugins/mods/reference),
> [skills](https://code.claude.com/docs/en/skills), [settings](https://code.claude.com/docs/en/settings),
> [memory](https://code.claude.com/docs/en/memory), [headless](https://code.claude.com/docs/en/headless).

## Contents

- Why a separate command
- What it reads, and what it refuses to open
- The estimate, and how rough it is
- Mods
- Measuring beside the estimate
- What it does not count

## Why a separate command

The audit's budget (check 17) counts what the repository puts in every session: its memory files,
its rules without paths, its skill, command and agent descriptions. A session pays more than that.
The user's own skills, the skills synced with their account, the plugins they enabled and the MCP
servers they connected are loaded too, in every project of that user.

Measured on 2026-10-09 (Claude Code 2.1.295, Haiku, one run per condition), on a project with 44
skills and 12 agents: first-turn input tokens 17,199 with no settings at all, 33,904 with the project's
settings only, 39,147 with every setting but no MCP server, 43,795 with everything. The project added
about 16,700 tokens; the account's synced skills and plugins about 5,200; 17 MCP servers about 4,600.

That second and third share are a property of one person's machine, not of the repository: a
finding about them would differ between two people auditing the same commit, and a floor taken on
one machine would fail on the other. So **deadweight --environment** is information only. It runs a
separate script (scripts/environment.py), raises no ERROR, WARN or NOTICE, is never counted and never
reaches a floor, and leaves the auditor's sha unchanged.

## What it reads, and what it refuses to open

Read-only, no network, nothing written.

| Origin | Read |
| --- | --- |
| project | what check 17 reads, counted the same way (the memory walk is re-done in the script so that every file goes through the refusal below): CLAUDE.md files and their relative imports, rules with no paths, skill descriptions plus when_to_use capped at 1,536 characters per entry, commands, agent descriptions; plus the custom output style the project settings select, the project's hooks, and the server names of its .mcp.json |
| account | in the user configuration directory (CLAUDE_CONFIG_DIR, else the .claude folder of the home directory): its CLAUDE.md and rules with no paths, and what they import (relative, home and absolute paths, up to four hops, outside code spans and blocks), skills (synced skills included), agents, hooks of its settings.json, and the plugins synced with the account |
| plugins | plugins/installed_plugins.json, kept to the installations that apply to this project, filtered by enabledPlugins (user, then project, then local settings); a plugin with no entry counts as enabled unless its manifest sets defaultEnabled to false. For each: skills, commands, agents, MCP server names, hooks, mods |
| MCP | server names only, from the project's .mcp.json and the enabled and synced plugins. Values are never kept or printed: a server's env may hold a token |

**Refused**: the credentials file of the configuration directory and the per-user state file
(.claude.json, in the home directory or in CLAUDE_CONFIG_DIR). The second is where the MCP servers
added with claude mcp add at user or local scope live, beside secrets. Those servers are therefore
not counted, and the report says so.

What is guaranteed, exactly: while the report is built, every file the script opens through Python's
open (its own reads and the auditor's helpers it reuses, which open files through pathlib) first goes
through one check, which opens nothing. A file is refused when its name is .claude.json,
.credentials.json or .env; when the real path it resolves to (a symbolic link, or a linked folder on
the way) has one of those names; or when it is the same file, by device and inode, as the
configuration's .claude.json or credentials file (a hard link under another name). A refused file
reads as empty, is not counted, and is listed under "Refused" in the output. Memory imports are
checked before they are followed. Not covered: a copy of their content in another file, and a
process the script starts (--measure runs claude, which reads its own credentials). Tests plant a
fake .claude.json in a fake home directory and reach it through a symbolic link (as .mcp.json, a
rule and a SKILL.md), a hard link, an @~/.claude.json import and a relative import that climbs to
it; none is opened.

## The estimate, and how rough it is

Tokens are characters divided by 2.85, a ratio measured on this plugin's own skill description.
It is rough: French prose, code and tables tokenise differently. Every token figure the command
prints is labelled an estimate.

On the project measured above (2026-10-09), the estimate gave 15,833 tokens for the project and
the plugin it enables, against 16,705 measured (−5 %), and 5,224 for the account, against 5,243
measured (−0.4 %). One project, one machine: not a precision figure for the ratio in general.

The estimate does not include the listing's own wrapper (skill names, plugin prefixes, list
markup), which is one reason it reads low.

## Mods

A mod is a plugin whose hooks/hooks.json names a hooks module under modules, "as in
"modules": ["./register.js"]", with an extension among .js, .mjs, .cjs, .jsx, .ts, .mts, .cts and
.tsx (mods reference). For each enabled or synced plugin that has one, the command prints the
plugin, the module, the local files it imports (followed, up to 20, inside the plugin only), the
events it listens to and the categories below. Nothing is run, imported or evaluated: the source is
read as text, comments are blanked, and regular expressions find the calls. Every category is printed
with "static reading of the source; not a measurement", and says "may": the code path may never run.

Names come from the [mods reference](https://code.claude.com/docs/en/plugins/mods/reference) (Events,
Mods API methods, Limits), the [mods API page](https://code.claude.com/docs/en/plugins/mods/api),
the [events page](https://code.claude.com/docs/en/plugins/mods/events) and the
[create page](https://code.claude.com/docs/en/plugins/mods/create).

| Category | Detected when the source |
| --- | --- |
| may add tokens to the model's context | listens to prompt.submit, prompt.compose, prompt.section, prompt.context, prompt.attachment, prompt.mention, skill.prompt, session.append, session.receive, tool.describe or command.run; or calls $.session.append, $.session.send, $.tool.register or $.prompt.submit |
| calls a model on the user's plan or API key, outside this session's context | calls $.model.complete, $.model.fork or $.model.classify |
| draws only | listens to ui.* events only, and calls nothing beyond $.ui, $.state, $.store, $.clock and read-only methods ($.session.messages, $.settings.read...) |
| may block or change a tool call | listens to tool.call, tool.check, classic.PreToolUse or classic.PermissionRequest |
| reaches files, processes or the network | calls $.fs, $.process, $.http or $.mcp |
| waits on a model, a process or the network outside the hook's own time limit | writes await or return before $.process.run or spawn, $.model.complete, fork or classify, $.http.fetch, or $.mcp.call or connect |
| unclassified | has no register function, an event name computed at run time or built from a template, a dynamic import(), eval() or new Function(), the mods API destructured or reached by $[...], lines over 2,000 characters, an import of a package other than claude-code, or a module that is missing, unreadable, outside the plugin or over 2 MiB |

Why these lines are drawn:

- **Context.** The events and calls in the first row are the documented ways a mod's text reaches
  Claude: prompt.submit "next({ ...e, context })" adds "text only Claude reads, after the prompt";
  a registered tool has "a description Claude reads"; a command's "text you return prints in the
  transcript and Claude reads it". $.session.send reaches another session or a subagent.
- **Model.** $.model calls do not add to this session's context: "Claude's conversation isn't part
  of the request" (mods API), and they "use the user's plan or API key". They have their own row. The size of what is
  added is computed at run time, so no token figure is given.
- **Draws only.** A mod that only draws (ui.render) added 0 first-request input tokens in a 3-run
  test on Claude Code 2.1.295 (claude -p, against 26,990 with no mod; a mod adding about 1,080
  characters on prompt.submit added 583 in the same test). In claude -p the ui.render hook did not run,
  so the interactive case, and the drawing's own time, are not measured.
- **Guard.** A tool.call hook can return "{ deny: reason }, or { result }", and Claude "reads the deny
  text as the tool's result". It runs on every tool call.
- **Waits.** "A hook's own execution time for one event, not counting time inside next or a mods API
  call other than $.clock.sleep" is limited to 10 seconds. A wait on $.process.run (30 seconds by
  default, 10 minutes at most) or on a model is therefore not cut by that limit. A wait inside a
  timer ($.clock.every) is found too, though it holds no event: the reading does not tell a hook from
  a timer.
- **Unclassified** is printed beside whatever was still found; a mod with it is never "draws only".

Built-in mods (cc-plugin-agents-md, cc-plugin-diff, cc-plugin-plugin-authoring, among others listed
under Built-in in /plugin) are not in the user's files: they are not counted, and the output says so.
The cross-check is the line /plugin prints under its tabs, such as "1 mod active · first-mod", which
"omits built-in mods" (mods overview): its count should equal this one. Mods loaded with --plugin-dir
or CLAUDE_CODE_PLUGIN_DIRS are not read.

### Known limits

- The time cost of a mod is not measured. The only duration source seen (--debug-file log lines,
  "hooks module X tool.call settled in N ms") is undocumented and includes the tool's own run time.
  A ui.render mod's drawing cost is not measured in claude -p.
- Static reading misses what is not written as a literal: a call through an alias (const api = $),
  an event name held in a variable outside on(...), code in a package the module imports, or a
  regular expression literal containing // that hides the rest of its line. Such a module can be
  reported with fewer categories than it has (false negative). The patterns that signal it most often
  turn the module "unclassified"; not all of them are caught.
- A call inside a string literal counts as a call (false positive), and so does a call in a branch
  that never runs.
- The categories are not checked against claude plugin validate, which "runs the same static analysis
  on the hooks module's source that Claude Code runs when it loads a mod"; this command does not
  run claude.

## Measuring beside the estimate

**deadweight --environment --measure** prints the estimate, then runs claude -p four times in the
project, on Haiku (claude-haiku-5-5; another model only by running scripts/environment.py --model
directly), with "Reply with the single word OK.":

| Condition | Options |
| --- | --- |
| bare | --setting-sources "" --strict-mcp-config |
| project | --setting-sources project --strict-mcp-config |
| all settings, no MCP | --strict-mcp-config |
| all settings | none |

It reads the init event (skills, agents, plugins, MCP servers, tools) and the result event (input
tokens + cache creation + cache read), and prints the differences: what the project adds, what the
user's settings add, what MCP adds. It does not print what the model answered.

It costs a few cents and uses the user's own login: the script reads no credential and passes none;
claude authenticates itself. One run per condition: the figures are noisy, and the cache state of a
run is not controlled.

**What it runs.** It is opening a Claude Code session in that folder, without the trust dialog:
"Without --bare, a -p session runs the hooks in a project's .claude/settings.json and connects
the servers in its .mcp.json, even in a folder you've never trusted. A -p session shows no
workspace trust dialog and no per-server approval prompt" (headless). The project condition and
the two after it load the project's settings, so its hooks run; the last one connects its .mcp.json
servers; the mods of the enabled plugins load and run (a mod adding text on prompt.submit was
measured adding 583 tokens under claude -p, above). Use it on a folder you trust. The question,
printed on the terminal's error stream, counts what will run: the hooks of the project's settings,
the servers of its .mcp.json, the mods of the enabled and synced plugins, the user settings' hooks
and the enabled plugins' hooks. The answer is read from the terminal. With no terminal, or with
--json, it runs only with --yes, so the standard output carries nothing but the report.

**What it splits.** The project condition uses --setting-sources project, which does not load the
local source (cli-reference lists user, project and local as separate sources): a plugin enabled in
settings.local.json is therefore estimated on the "user and local settings" side.

## What it does not count

- Claude Code's own system prompt, built-in tools, skills and agents (the bare condition).
- MCP tool definitions: they come from the servers when they connect. Only --measure sees them.
- MCP servers added with claude mcp add, and claude.ai connectors.
- What SessionStart and UserPromptSubmit hooks print: counted as hooks, not estimated.
- Overflow of the skill listing: past its budget, descriptions are dropped (check 29); the estimate
  counts them all.
- A plugin manifest path (skills, commands, agents, an MCP .json file) that resolves outside the
  plugin's root: "a path that resolves outside the plugin root doesn't load" (plugins reference). It
  is named in the output, not counted, and not walked.
- The project's own imports with a home or absolute path: check 17 skips them, and they load only
  after the external-imports approval of that project, which this script does not read.
