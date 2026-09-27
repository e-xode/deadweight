---
max_turns: 15
allowed_tools: [Read, Glob, Grep, Bash, Skill]
---

Every time Claude prepares a pull request in our shop repository it fails at the same step and then improvises. Our CLAUDE.md says:

```markdown
## Before opening a PR
Run `npm run lint` and `npm run test:e2e`.
```

and our `package.json` has:

```json
{ "scripts": { "lint": "eslint .", "test": "vitest", "build": "vite build" } }
```
