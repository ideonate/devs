# CLAUDE.md

This file provides guidance to Claude Code when working with the `devs` project - a DevContainer Management Script for managing multiple named devcontainers.

## Project Overview

`devs` is a command-line tool that simplifies managing multiple named devcontainers for any project. It allows developers to run commands like `devs start sally bob` to create multiple development environments with distinct names, then `devs open sally` to launch VS Code connected to specific containers.

## Key Features

- **Multiple Named Containers**: Start multiple devcontainers with custom names (e.g., "sally", "bob", "charlie")
- **VS Code Integration**: Open containers in separate VS Code windows with clear titles
- **Project Isolation**: Containers are prefixed with git repository names (org-repo format) 
- **Shared Authentication**: Claude credentials are shared between containers for the same project
- **Cross-Platform**: Works on any project with devcontainer configuration

## Architecture

### Container Naming
Containers follow the pattern: `dev-<org>-<repo>-<dev-name>`

Example: `dev-ideonate-devs-sally`, `dev-ideonate-devs-bob`

### VS Code Window Management  
Each container gets unique workspace paths to ensure VS Code treats them as separate sessions:
- Host symlinks: `/path/to/project-sally`, `/path/to/project-bob`
- Container workspaces: `/workspace/project-sally`, `/workspace/project-bob`
- VS Code titles: "Sally - Project Name", "Bob - Project Name"

### Claude Authentication Sharing
The tool creates symlinks in `.claude/projects/` so all containers for the same project share Claude authentication:
- Individual paths: `workspace-project-sally-<hash>`, `workspace-project-bob-<hash>`
- Shared target: `workspace-project-shared`
- Result: Login once per project, not per container

## Commands

### Core Commands
- `devs start <name...>` - Start named devcontainers
- `devs open <name...>` - Open devcontainers in VS Code
- `devs stop <name...>` - Stop and remove devcontainers  
- `devs shell <name>` - Open shell in devcontainer
- `devs list` - List active devcontainers for current project
- `devs help` - Show usage information

### Example Workflow
```bash
# Start development environments
devs start frontend backend

# Open both in VS Code (separate windows)
devs open frontend backend

# Work in a specific container
devs shell frontend

# Clean up when done
devs stop frontend backend
```

## Installation

The script is designed to be globally available via symlink:

```bash
# Clone repository
git clone https://github.com/ideonate/devs.git
cd devs

# Make globally available
sudo ln -sf "$(pwd)/devs" /usr/local/bin/devs
```

## Dependencies

- **Docker**: Container runtime
- **VS Code**: With `code` command in PATH
- **DevContainer CLI**: `npm install -g @devcontainers/cli`
- **Project Requirements**: `.devcontainer/devcontainer.json` in target projects

## Key Implementation Details

### Project Detection
The script uses git remote URLs to determine project names:
```bash
# Extract org-repo format from git URL
project_name=$(git remote get-url origin | sed 's/.*github\.com[/:]//' | sed 's/\.git$//' | tr '[:upper:]' '[:lower:]' | tr '/' '-')
```

### Unique Workspace Creation
For each dev container, the script:
1. Creates symlink: `${project_dir}-${dev_name}` → `${project_dir}`
2. Uses symlink as workspace folder for devcontainer CLI
3. Results in unique container workspaces that VS Code can distinguish

### VS Code URI Format
The script uses VS Code's devcontainer URI format:
```bash
code --folder-uri "vscode-remote://dev-container+${hex_path}/workspace/${workspace_name}"
```

Where `hex_path` is the hexadecimal encoding of the unique workspace folder path.

### Claude Configuration Sharing
A post-create script (`setup-claude-symlinks.sh`) runs in each container to:
1. Detect the workspace name and extract base project name
2. Create symlinks from container-specific Claude project paths to shared paths
3. Ensure all containers for the same project use the same Claude authentication

## Troubleshooting

### "Container not found" errors
- Check if container is running: `docker ps`
- Verify project name detection: `devs list`
- Ensure you're in a git repository

### VS Code can't connect
- Verify devcontainer configuration exists: `.devcontainer/devcontainer.json`
- Check container logs: `docker logs <container-name>`
- Try shell access first: `devs shell <name>`

### Claude authentication issues
- Check symlinks: `ls -la ~/.claude/projects/` (inside container)
- Verify shared directory exists: `workspace-<project>-shared`
- Re-run setup: `/usr/local/bin/setup-claude-symlinks.sh`

### Multiple VS Code windows not opening
- This was a complex issue requiring unique workspace paths
- Ensure symlinks are created: `ls -la /path/to/project-*`
- Check devcontainer CLI success in `devs start` output

## Development Notes

### Environment Variable Support
The devcontainer.json supports `DEVCONTAINER_NAME` for custom naming:
```json
{
  "name": "${localEnv:DEVCONTAINER_NAME:Default} - Project Name"
}
```

### GitHub Token Integration
The containers include GitHub token setup for API access, extracted from user shell configuration to bypass sudo restrictions.

### Firewall Configuration
Containers include network filtering via `init-firewall.sh` that:
- Fetches GitHub IP ranges (with authentication)
- Allows specific domains for development tools
- Blocks general internet access for security

## Future Enhancements

- **Multi-project support**: Currently optimized for single project at a time
- **Container persistence**: Add options for persistent vs ephemeral containers  
- **Resource limits**: Add CPU/memory constraints per container
- **Template support**: Custom devcontainer configurations per dev name
- **Backup/restore**: Save and restore container states

## File Structure

```
devs/
├── devs                    # Main script
├── README.md              # User documentation  
├── CLAUDE.md              # This file - Claude Code guidance
└── LICENSE                # MIT license
```

## Important Implementation Decisions

1. **Symlink approach**: Chosen over volume mounts for VS Code compatibility
2. **Git-based naming**: Ensures consistent project identification across machines
3. **Post-create hooks**: Used for Claude configuration sharing
4. **Shell integration**: zsh as default shell with proper environment setup
5. **Permission handling**: Careful sudo configuration for security scripts

This architecture balances VS Code's requirements for unique workspace identification with the need to share authentication and project context between multiple development environments.