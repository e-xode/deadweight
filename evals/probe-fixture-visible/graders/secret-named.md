---
type: regex
pattern: "(literal|hard-?coded|plain ?text|in clear|committed).{0,80}(token|credential|secret|bearer)|(token|credential|secret|bearer).{0,80}(literal|hard-?coded|plain ?text|committed)|\\$\\{[A-Z_]+\\}"
flags: "is"
weight: 1
---
