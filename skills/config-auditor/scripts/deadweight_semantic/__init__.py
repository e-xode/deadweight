"""The semantic layer of the auditor, behind `--semantic`: what a reader sees and a parser does not.

Kept OUT of the auditor proper on purpose. Its findings come from a model, so two runs do not
agree; they are never counted, never reach the floor, and this package is not part of the
instrument's identity (`deadweight_audit.identity`). It is imported only when `--semantic` is
given - an import at load time would make it part of every audit.
"""
