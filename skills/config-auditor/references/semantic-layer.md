# The semantic layer — what a reader sees and a parser does not

> Examples use a fictional online shop (`shop-api`). Figures are measurements, dated, taken on
> configurations of a private fleet; the method is described so it can be repeated.

## Contents

- What it looks for, and what it does not ask
- Outside the floor, by construction
- Running it
- What it is worth, measured
- What it costs, and what it sends

## What it looks for, and what it does not ask

Every other check reads files mechanically. Two defects need a reader:

| Finding | What it means | Evidence it must carry |
| --- | --- | --- |
| `58-semantic-contradiction` | two instructions that cannot both be followed in the same situation | two verbatim quotes, each with its file, and the situation |
| `59-semantic-duplicate` | the same rule written in two files, in different words — the copies drift | two verbatim quotes from two files |

On request (`--also`), with the reason each is not shown by default:

| Name | Finding | Why on request |
| --- | --- | --- |
| `internal-duplicates` | `59` inside one file | often a rule restated as its anti-pattern, on purpose |
| `untestable` | `61-semantic-untestable` — an instruction nobody could check | mostly design charters ("bold, never noisy"), a deliberate choice |
| `descriptions` | `60-semantic-description-mismatch` | measured below 90 % precision |
| `misplaced` | `62-semantic-misplaced` — method knowledge in `CLAUDE.md` | too few findings to measure |

Every quote is checked character for character (whitespace aside) against the file it names; a
finding with one quote that is not there is rejected and counted. So is a finding whose own
explanation disowns it ("weak, not a real duplicate"), and one whose two sides quote the same
passage — for a duplicate inside one file, a sentence written twice in that file is two passages.

**Not asked: "is this rule beneficial?"** That is a counterfactual — does the project do better with
the rule than without — and it is answered by running the model with and without it
(`claude plugin eval`), not by reading. A model judging a rule finds clear and useful the rule it
would have followed anyway, which is the one rule that is useless.

## Outside the floor, by construction

Semantic findings are never counted: `semantic.py` prints them in their own report
(`=== SEMANTIC … not counted ===`, or JSON with `"counted": false`), writes no floor and always exits
0 once it has run. The reason is measured, not stylistic: two
runs on the same configuration agree on about three findings in four, so a floor taken with
the layer would move with nobody touching anything. So it is a separate command,
`scripts/semantic.py`, over a separate package (`scripts/deadweight_semantic/`): the auditor that
counts (`audit.py` and `deadweight_audit/`) does not import it and is not changed by it, so its sha,
and every floor taken with it, stays as it is — and rewording a prompt invalidates no floor. Its own identity — model, Claude Code
version, layer sha, date — is printed with its findings.

## Running it

```bash
python3 ${CLAUDE_SKILL_DIR}/scripts/semantic.py
python3 ${CLAUDE_SKILL_DIR}/scripts/semantic.py --also internal-duplicates,untestable
python3 ${CLAUDE_SKILL_DIR}/scripts/semantic.py --json --model claude-sonnet-5-5 --max-requests 40
```

Requests go through `claude -p` in a minimal context — no tools, no MCP server, no settings — with
a pinned model id (an alias such as `sonnet` is refused: it changes target between releases). One
request per skill or agent reads it beside the instructions every session loads (`CLAUDE.md` and
`.claude/rules/`): a contradiction usually sits between that "law" and one file, and two texts that
contradict each other share little vocabulary, so pairing files by vocabulary does not find them.
Pairs of skills and agents are added for duplicates, which do share it. The plan is capped
(`--max-requests`, default 100); what the cap leaves out is reported as not reviewed.

## What it is worth, measured

Corpus: 35 configuration defects that maintainers declared fixing in their own commits — a source
no model chose — audited at the commit before each fix, then a precision sample labelled by hand.

| | Default (58 + 59 between files) |
| --- | --- |
| Precision, contradictions | 50 of 50 |
| Precision, duplicates between files | 49 of 50 |
| Recall on declared contradictions and duplicates | 4 of 24 at the declared spot; 6 of 24 counting the same conflict found elsewhere |
| Agreement between two runs | about 3 findings in 4 |

Read it as: **precise and partial**. What it reports is almost always there; most of what is there,
it does not report. It often finds a conflict the maintainer fixed in one file still standing in
another — a recall measured against what maintainers fixed undercounts what it finds.

## What it costs, and what it sends

- **Cost**: about 5 USD for a configuration of 50 skills and agents with the default cap, under a
  minute for a small one. The report prints the cost of the run.
- **What leaves the machine**: the text of `CLAUDE.md`, the rules, every `SKILL.md` and agent file,
  and the in-repository Markdown files they point to (one hop: a Markdown link, an `@` import or a
  backticked `.md` path), is sent to the model through your own Claude Code session; the JSON
  report lists them in `files_sent`. Do not run it on a configuration you may not send.
- **What it does not read**: `.claude/commands/`, `CLAUDE.local.md`, the `CLAUDE.md` of
  subfolders and `AGENTS.md` are reviewed only when a collected file links to them. The report
  names the others (`instruction_files_not_reviewed`). A `CLAUDE.md` symlinked to `AGENTS.md` is
  sent as `CLAUDE.md`, and `AGENTS.md` is not listed as left out.
- **A Claude Code update during a run** replaces the `claude` executable for a few seconds; the
  layer waits and retries, and reports any request that still failed.
