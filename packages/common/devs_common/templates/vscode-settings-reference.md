# VS Code Settings Reference

This document lists all VS Code settings configured for consistent behavior between host and devcontainer environments.

## Python/Pylance Settings

- **`python.analysis.typeCheckingMode`**: `"off"` - Disables type checking
- **`python.analysis.diagnosticMode`**: `"openFilesOnly"` - Only shows problems for currently open files
- **`python.analysis.diagnosticSeverityOverrides`**: `{"reportUnusedImport": "information", "reportUnusedVariable": "information"}` - Downgrades unused imports/variables from warnings to info
- **`[python].editor.codeActionsOnSave.source.organizeImports`**: `"never"` - Disables automatic import sorting on save

## Extension Management Settings

- **`extensions.ignoreRecommendations`**: `true` - Prevents auto-installing recommended extensions
- **`extensions.showRecommendationsOnlyOnDemand`**: `true` - Only shows recommendations when explicitly requested
- **`extensions.autoCheckUpdates`**: `false` - Disables automatic extension update checks
- **`extensions.autoUpdate`**: `false` - Disables automatic extension updates

## Settings Sync

- **`settingsSync.ignoredExtensions`**: `[]` - Controls which extensions are ignored during sync
- **`settingsSync.keybindingsPerPlatform`**: `false` - Disables platform-specific keybinding sync

## Tool-Specific Settings

- **`pylint.enabled`**: `false` - Disables Pylint linter
- **`gitlens.mode`**: `"zen"` - Minimizes GitLens functionality

## Other Settings

- **`dev.containers.cacheVolume`**: `false` - Disables VS Code's cache volume for containers (in host settings)