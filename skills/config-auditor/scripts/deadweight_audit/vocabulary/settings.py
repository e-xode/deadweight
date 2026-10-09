"""Settings keys, by the scope that honours them."""
from __future__ import annotations



# Settings keys by the files that may set them. Source: the Scope column of
# code.claude.com/docs/en/settings-reference, read 2026-09-27 (234 keys; 242 on 2026-09-30, gate 10). "Claude
# Code ignores the key in a repository file" - silently - when its scope excludes
# the project file (settings, 'Why a setting doesn't apply').
SETTINGS_KEYS_ANY = frozenset({
    "advisorModel", "agent", "agentPushNotifEnabled", "allowedHttpHookUrls",
    "allowedMcpServers", "alwaysThinkingEnabled", "apiKeyHelper", "attribution",
    "attribution.commit", "attribution.pr", "attribution.sessionUrl", "autoCompactEnabled",
    "autoCompactWindow", "autoMemoryDirectory", "autoMemoryEnabled", "autoScrollEnabled",
    "autoUpdatesChannel", "availableModels", "awaySummaryEnabled", "awsAuthRefresh",
    "awsCredentialExport", "axScreenReader", "bashOutputMaxChars", "claudeMdExcludes",
    "cleanupPeriodDays", "companyAnnouncements", "crossSessionInbound", "defaultShell",
    "deniedMcpServers", "disableAgentView", "disableAllHooks", "disableArtifact",
    "disableAutoMode", "disableBundledSkills", "disableClaudeAiConnectors",
    "disableDeepLinkRegistration", "disableRemoteControl", "disableSkillShellExecution",
    "disableWorkflows", "disabledMcpjsonServers", "editorMode", "effortLevel",
    "emojiCompletionEnabled", "enableAllProjectMcpServers", "enableArtifact", "enableWorkflows",
    "enabledMcpjsonServers", "enabledPlugins", "enforceAvailableModels", "env",
    "extraKnownMarketplaces", "additionalMarketplaces", "fallbackModel", "fastMode", "fastModePerSessionOptIn",
    "feedbackSurveyRate", "fileCheckpointingEnabled", "fileSuggestion", "forceLoginMethod",
    "forceLoginOrgUUID", "gcpAuthRefresh", "hooks", "httpHookAllowedEnvVars",
    "includeCoAuthoredBy", "includeGitInstructions", "inputNeededNotifEnabled",
    "isolatePeerMachines", "keybindingFlavor", "language", "maxEffortLevel", "maxProseWidth", "minimumVersion",
    "model", "modelOverrides", "modelSettings", "otelHeadersHelper", "outputStyle",
    "permissions", "permissions.additionalDirectories", "permissions.allow", "permissions.ask",
    "permissions.blockReadsOutsideWorkingDirectories", "permissions.defaultMode",
    "permissions.deny", "permissions.disableBypassPermissionsMode", "plansDirectory",
    "prUrlTemplate", "preferredNotifChannel", "prefersReducedMotion", "promptCacheTtl",
    "promptSuggestionEnabled", "remote.defaultEnvironmentId", "remoteControlAtStartup",
    "respectGitignore", "respondToBashCommands", "sandbox", "sandbox.allowUnsandboxedCommands",
    "sandbox.autoAllowBashIfSandboxed", "sandbox.credentials", "sandbox.credentials.envVars",
    "sandbox.credentials.files", "sandbox.enableWeakerNestedSandbox",
    "sandbox.enableWeakerNetworkIsolation", "sandbox.enabled", "sandbox.excludedCommands",
    "sandbox.failIfUnavailable", "sandbox.filesystem", "sandbox.filesystem.allowRead",
    "sandbox.filesystem.allowWrite", "sandbox.filesystem.denyRead",
    "sandbox.filesystem.denyWrite", "sandbox.ignoreViolations", "sandbox.network",
    "sandbox.network.allowAllUnixSockets", "sandbox.network.allowLocalBinding",
    "sandbox.network.allowMachLookup", "sandbox.network.allowUnixSockets",
    "sandbox.network.allowedDomains", "sandbox.network.deniedDomains",
    "sandbox.network.httpProxyPort", "sandbox.network.socksProxyPort",
    "showClearContextOnPlanAccept", "showThinkingSummaries", "showTurnDuration",
    "skillListingBudgetFraction", "skillListingMaxDescChars", "skillOverrides",
    "skipWebFetchPreflight", "spinnerTipsEnabled", "spinnerTipsOverride", "spinnerVerbs",
    "statusLine", "subagentPromptCacheTtl", "subagentStatusLine", "switchModelsOnFlag",
    "syntaxHighlightingDisabled", "taskOutputMaxChars", "teammateMode",
    "terminalProgressBarEnabled", "terminalTitleFromRename", "theme", "timeFormat", "timeZone",
    "tui", "ultracode", "verbose", "viewMode", "voice", "voiceEnabled",
    "wheelScrollAccelerationEnabled", "workflowKeywordTriggerEnabled", "workflowSizeGuideline",
    "worktree", "worktree.baseRef", "worktree.bgIsolation", "worktree.sparsePaths",
    "worktree.symlinkDirectories"
})


SETTINGS_KEYS_USER_LOCAL_MANAGED = frozenset({
    "skipDangerousModePermissionPrompt", "syncClaudeAiPlugins", "syncClaudeAiSkills",
    "useAutoModeDuringPlan"
})


SETTINGS_KEYS_USER_MANAGED = frozenset({
    "appendPlugins", "askUserQuestionTimeout", "autoContinueAtUsageLimit", "autoMode", "prependPlugins",
    "autoMode.classifyAllShell", "bashEditDiffEnabled", "desktopSessionCleanupPeriodDays",
    "dialogExpiry", "feedbackDrafts", "footerLinksRegexes", "modelPicker", "pluginConfigs",
    "processWrapper", "sandbox.allowAppleEvents", "sandbox.credentials.allowPlaintextInject",
    "sandbox.credentials.awsPairs", "sandbox.credentials.sigv4", "sandbox.filesystem.disabled",
    "sandbox.network.strictAllowlist", "sandbox.network.tlsTerminate", "sandbox.ripgrep",
    "skipAutoPermissionPrompt", "spellcheck", "sshConfigs", "vimInsertModeRemaps"
})


SETTINGS_KEYS_MANAGED = frozenset({
    "allowAllClaudeAiMcps", "allowClaudeInChromeWithManagedMcp", "allowManagedHooksOnly", "allowManagedMcpServersOnly",
    "allowManagedPermissionRulesOnly", "allowedChannelPlugins", "allowedProviders", "availableModelsMatch",
    "blockedMarketplaces", "browserExternalPageTools", "channelsEnabled", "claudeMd",
    "deniedModels",
    "disableBrowserExternalNavigation", "disableCommandPluginSources",
    "disableDesktopLocalSessions", "disableMobileSimulatorTools", "disableSideloadFlags",
    "forceLoginGatewayUrl", "forceRemoteSettingsRefresh", "gatewayInternalNetworks",
    "managedMcpServers", "managedSourcesBehavior", "modelPricing", "parentSettingsBehavior",
    "pluginSuggestionMarketplaces", "pluginTrustMessage", "policyHelper", "policyHelper.path",
    "policyHelper.refreshIntervalMs", "policyHelper.timeoutMs", "requiredMaximumVersion",
    "requiredMinimumVersion", "sandbox.bwrapPath",
    "sandbox.filesystem.allowManagedReadPathsOnly", "sandbox.network.allowManagedDomainsOnly",
    "sandbox.socatPath", "sshHostAllowlist", "strictKnownMarketplaces", "allowedMarketplaces",
    "strictPluginOnlyCustomization", "strictPluginOnlyCustomization.agents",
    "strictPluginOnlyCustomization.hooks", "strictPluginOnlyCustomization.mcp",
    "strictPluginOnlyCustomization.skills", "wslInheritsWindowsSettings"
})


SETTINGS_KEYS_GLOBAL = frozenset({
    "autoConnectIde", "autoInstallIdeExtension", "copyOnSelect", "diffTool",
    "externalEditorContext", "permissionExplainerEnabled", "teammateDefaultModel",
    # settings-reference, Scope "Global config", 2026-09-29 (derive.py, gate 10)
    "claudeInChromeDefaultEnabled", "copyFullResponse", "defaultToAgentsView",
    "leftArrowOpensAgents", "prStatusFooterEnabled",
})


SETTINGS_KNOWN_KEYS = (SETTINGS_KEYS_ANY | SETTINGS_KEYS_USER_LOCAL_MANAGED
                       | SETTINGS_KEYS_USER_MANAGED | SETTINGS_KEYS_MANAGED | SETTINGS_KEYS_GLOBAL)


# Objects whose fields the settings reference lists as a closed set ("Type: object
# with ..."), 2026-09-24. A misspelt field is ignored without a word, exactly like a
# misspelt key - `attribution.coAuthoredBy` looks like configuration and turns nothing
# off. Objects keyed freely (`env`, `enabledPlugins`, `hooks`, `skillOverrides`) are not
# here: every key they hold is legitimate.
SETTINGS_OBJECT_FIELDS = {
    "attribution": {"commit", "pr", "sessionUrl"},
    "autoMode": {"allow", "classifyAllShell", "environment", "hard_deny", "soft_deny"},
    "permissions": {"additionalDirectories", "allow", "ask", "blockReadsOutsideWorkingDirectories",
                    "defaultMode", "deny", "disableAutoMode", "disableBypassPermissionsMode"},
    "policyHelper": {"path", "refreshIntervalMs", "timeoutMs"},
    "worktree": {"baseRef", "bgIsolation", "sparsePaths", "symlinkDirectories"},
    "sandbox": {"allowAppleEvents", "allowUnsandboxedCommands", "autoAllowBashIfSandboxed",
                "bwrapPath", "credentials", "enableWeakerNestedSandbox",
                "enableWeakerNetworkIsolation", "enabled", "excludedCommands",
                "failIfUnavailable", "filesystem", "ignoreViolations", "network", "ripgrep",
                "socatPath"},
    "statusLine": {"command", "hideVimModeIndicator", "padding", "refreshInterval", "type"},
    "subagentStatusLine": {"command", "type"},
    "fileSuggestion": {"command", "type"},
    "spinnerVerbs": {"mode", "verbs"},
    "modelSettings": {"effortLevel", "maxEffortLevel"},
    "voice": {"autoSubmit", "enabled", "mode"},
}


# Keys whose Scope line says Claude Code ignores them outside managed settings "with a
# warning" (availableModelsMatch, deniedModels) or "drops the key with a warning"
# (managedMcpServers): settings-reference, read 2026-10-08. The others are not said silent
# or loud, except requiredMinimumVersion / requiredMaximumVersion ("gives no warning").
SETTINGS_KEYS_IGNORED_WITH_WARNING = frozenset({"availableModelsMatch", "deniedModels",
                                                "managedMcpServers"})
# "Claude Code gives no warning when it ignores the key elsewhere" (settings-reference,
# Scope of each, read 2026-10-08). For every other barred key the docs say neither, and
# the message says neither (audit 3, g6-01).
SETTINGS_KEYS_IGNORED_SILENTLY = frozenset({"requiredMinimumVersion", "requiredMaximumVersion"})


# "a `false` in .claude/settings.json is ignored" for these opt-outs (settings).
SETTINGS_PROJECT_IGNORED_FALSE = {"useAutoModeDuringPlan", "syncClaudeAiSkills",
                                  "syncClaudeAiPlugins"}

# User-or-managed keys that a project or local file is not silent about (settings-reference,
# Scope): any value of `autoContinueAtUsageLimit` there "turns the feature off rather than
# being ignored" while user settings, `--settings` and managed settings leave it unset, and a
# `false` `bashEditDiffEnabled` there "still turns it off". The value is the one that acts
# (None: any value). External audit 4, se-03.
SETTINGS_PROJECT_TURNS_OFF = {"autoContinueAtUsageLimit": None, "bashEditDiffEnabled": False}


BUILTIN_OUTPUT_STYLES = {"Default", "Explanatory", "Learning", "Proactive", "Concise"}


PROJECT_SCOPE_IGNORED_MODES = {"bypassPermissions", "auto"}
