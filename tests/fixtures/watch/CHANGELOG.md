# Changelog

## 7.4.13

- Added `"quietRetries": false` in settings.json to stop the retry banner in shop-api sessions
- Added `onStall: "pause"` for HTTP hooks: a hook that stops answering pauses the action
- Added `SHOP_WATCH_DEPTH` to change how many folders the file watcher descends
- Fixed `toString` in a skill name crashing the skills list
- Fixed a permission prompt drawn twice after resizing the terminal

## 7.4.12

- Removed the legacy `cartPreview` setting; use `previewMode` instead
- Changed subagent frontmatter to accept `autoCompactWindow`, as settings already did
- Added `agentId` to the `tool.check` event payload of plugin hooks
- Improved the startup time of `/shop-report` by 20%

## 7.4.11

- Deprecated the `basketLimit` key in plugin.json
- Changed the default limit on tool descriptions from 2,048 to 4,096 characters
- Fixed the marketplace list scrolling past the last entry

## 7.4.10

- Added `orderTimeout` to agent definitions
- Fixed a crash when `~/.shop/state.json` was empty
