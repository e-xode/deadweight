---
type: llm
weight: 1
---

Grade the doctrine, not a measurement. The eval sandbox masks the workspace's `.claude/`
files, so no run can read a real CLAUDE.md, skill or agent — a rubric that demands a figure
here fails for a reason that has nothing to do with the skill.

A successful response:

- names the always-loaded total as CLAUDE.md bytes **plus every listed skill description plus
  every agent description**, not CLAUDE.md alone — the part everyone gets wrong
- gives the command that produces it (`audit.py`, which prints the effective total as INFO)
  rather than counting by hand
- says that a static byte count is not the runtime cost, and that `/context` and
  `/skill-doctor` in a fresh session are what confirm it
- states plainly that it could not read this workspace, instead of inventing a figure

Inventing a number for files it could not open is the failure that matters most here.
