# Running this suite

```bash
claude plugin eval . --allow-tools Bash -j 3
```

**`--allow-tools Bash` is not optional.** Five of the seven cases expect the model to reach for
`deadweight` rather than read `CLAUDE.md` by hand, and `Bash` is gated behind an operator grant:
without it the runner reports `not granted` and the case fails for a reason that has nothing to do
with the skill.

## Two numbers here are the author's choice, not a measurement

`max_turns` and `allowed_tools` in each `prompt.md` decide what a case *can* do before it decides
whether the skill did it. On 2026-09-22 a first run used `max_turns: 6` and no grant: **four of the
five failures said `Reached maximum number of turns`, and one said `not granted: Bash`**. Five cases
out of seven measured the harness configuration instead of the plugin, and the two that passed
happened to be the two that needed neither.

That is the shape to watch for in any eval suite: a failure whose message names the runner rather
than the subject. Read the NOTES column before the SCORE column.

See [PROVENANCE.md](./PROVENANCE.md) for where the cases come from, and what that limits.
