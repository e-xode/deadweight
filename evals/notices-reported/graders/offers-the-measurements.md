---
type: llm
weight: 1
---

Judge the reply against the audit output it received, not against numbers stated here: the eval
sandbox can hide files from the audit, so its counts may differ from a run on a workstation.

Until 0.12.0 the findings of this fixture were INFO, the run printed "All checks passed.", and the
reply was "0 errors, 0 warnings" - findings that each name a file were dropped on the way to the
user.

Pass only if the reply does all three:

- it does NOT present the configuration as clean, passed or with nothing to report;
- it reports the findings the audit raised above INFO - here the skill pair `shop-refunds` /
  `shop-payouts` separated only by their descriptions, and the angle bracket in a description;
- it mentions the remaining measurement (INFO) lines by count and offers to show them, instead of
  either listing all of them or leaving them unmentioned.

Findings the reply adds from its own reading of the files do not count against it.
