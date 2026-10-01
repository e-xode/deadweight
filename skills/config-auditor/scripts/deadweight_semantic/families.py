"""The closed list of defects the semantic layer looks for, and the evidence each one must carry.

A finding without its evidence is rejected, not shown: a reader can check a quote, not an opinion.
"Is this rule beneficial?" is not on the list - that is a counterfactual question, answered by
running the model with and without the rule (`claude plugin eval`), not by reading it.
"""
from __future__ import annotations

FAMILIES = {
    "58": ("58-semantic-contradiction",
           "two instructions that cannot both be followed in the same situation",
           "two verbatim quotes, each with its file, and the situation where they collide", 2),
    "59": ("59-semantic-duplicate",
           "the same rule or fact written twice, in different words - the copies will drift",
           "two verbatim quotes, from two files or two sections", 2),
    "60": ("60-semantic-description-mismatch",
           "a skill or agent description that promises what the body does not do, or hides what it mostly does",
           "the description sentence and the body passage (or the statement that no passage does it)", 1),
    "61": ("61-semantic-untestable",
           "an instruction with no criterion anyone could check (\"be rigorous\", \"clean code\")",
           "the quoted instruction", 1),
    "62": ("62-semantic-misplaced",
           "method or reference knowledge in CLAUDE.md that belongs in a skill, or a hard rule buried "
           "in a skill reference that every session needs",
           "the quoted passage and where it belongs", 1),
}

NOT_DEFECTS = (
    "a general rule and a path-scoped rule that narrows it",
    "a pointer to another file (\"see X.md\")",
    "a safety instruction deliberately repeated in an agent",
    "a description shorter than its body",
    "instructions for different situations that only look alike",
)

# Shown by default: the two families measured at 90 % precision or more on defects of real
# repositories (2026-10-01: contradictions 47/50, duplicates 50/50). The others answer a
# narrower question or did not reach the bar, and are added on request (--semantic-also).
DEFAULT = ("58", "59")
ON_REQUEST = {
    "internal-duplicates": "59",   # the same rule twice in ONE file - often a rule and its anti-pattern
    "descriptions": "60",          # 26/34 measured: below the bar
    "untestable": "61",            # true by definition, often a deliberate charter ("Bold, never noisy")
    "misplaced": "62",             # 4 findings: not measured enough
}
