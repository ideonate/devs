# devs - DevContainer Management Script

A simple command-line tool to manage multiple named devcontainers for any project, making it easy to spin up and switch between different development environments.

## Features

- 🚀 **Start multiple devcontainers** with custom names (e.g., "sally", "bob")
- 📂 **Open containers in VS Code** with clear window titles
- 🛑 **Stop and clean up** containers when done
- 📋 **List active containers** for current project
- 🏷️ **Project-aware** using git repository names (org-repo format)
- ⚡ **Works with any project** that has devcontainer configuration

## Installation

### Quick Install

```bash
# Clone and install globally
git clone https://github.com/ideonate/devs.git
cd devs
sudo ./install.sh
```

### Manual Install

```bash
# Clone the repository
git clone https://github.com/ideonate/devs.git
cd devs

# Make executable and add to PATH
chmod +x devs
sudo cp devs /usr/local/bin/devs
```

### Development Install

```bash
# Clone and symlink for development
git clone https://github.com/ideonate/devs.git
cd devs
chmod +x devs
sudo ln -sf "$(pwd)/devs" /usr/local/bin/devs
```

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/)
- [VS Code](https://code.visualstudio.com/) with `code` command in PATH
- [DevContainer CLI](https://github.com/devcontainers/cli): `npm install -g @devcontainers/cli`
- Project with `.devcontainer/devcontainer.json` configuration

## Usage

Run `devs` from any project directory that has devcontainer configuration:

### Basic Commands

```bash
# Start named devcontainers
devs start sally bob charlie

# Open containers in VS Code
devs open sally bob

# List active containers for current project
devs list

# Stop and remove containers
devs stop sally

# Show help
devs help
```

### Example Workflow

```bash
# In your project directory
cd ~/myproject

# Start two development environments
devs start frontend backend

# Open both in VS Code (separate windows)
devs open frontend backend

# Later, stop the backend container
devs stop backend

# List what's still running
devs list
```

## How It Works

### Container Naming

Containers are named using the pattern: `dev-<org>-<repo>-<dev-name>`

For example, with repo `https://github.com/myorg/myproject`:

- `devs start alice` creates container: `dev-myorg-myproject-alice`
- `devs start bob` creates container: `dev-myorg-myproject-bob`

### VS Code Integration

Each container gets a custom name in VS Code:

- Window title shows: `<dev-name> - <workspace>`
- Easy to distinguish between multiple development environments

### Project Isolation

Containers are tagged with project labels for easy management:

- Only shows containers for the current project when listing
- Clean separation between different projects

## Configuration

The script uses your existing `.devcontainer/devcontainer.json` configuration. Make sure your devcontainer config supports the `DEVCONTAINER_NAME` environment variable for custom naming:

```json
{
  "name": "${localEnv:DEVCONTAINER_NAME:Default} - My Project"
  // ... rest of your config
}
```

## Advanced Usage

### Custom Project Names

By default, project names are derived from git repository URLs. For `https://github.com/org/repo`, the project name becomes `org-repo`.

### Multiple Projects

You can use `devs` across multiple projects. Each project's containers are isolated and managed separately.

### Container Lifecycle

- `start` - Creates and starts new containers (removes existing ones with same name)
- `open` - Launches VS Code connected to existing containers
- `stop` - Stops and removes containers completely
- `list` - Shows only containers for current project

## Troubleshooting

### Command not found

Make sure `/usr/local/bin` is in your PATH:

```bash
echo $PATH | grep -q "/usr/local/bin" || echo 'export PATH="/usr/local/bin:$PATH"' >> ~/.zshrc
```

### DevContainer CLI not found

Install the DevContainer CLI:

```bash
npm install -g @devcontainers/cli
```

### No devcontainer.json found

Make sure you're in a project directory with `.devcontainer/devcontainer.json`:

```bash
ls .devcontainer/devcontainer.json
```

### Permission denied

Make sure the script is executable:

```bash
chmod +x /usr/local/bin/devs
```

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature-name`
3. Make changes and test
4. Submit a pull request

## License

MIT License - see [LICENSE](LICENSE) file for details.

## Author

Created by [Ideonate](https://github.com/ideonate) to simplify devcontainer management across projects.
