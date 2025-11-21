# Environment Variables - Example Usage Guide

This document demonstrates the enhanced environment variable support in devs with real-world examples.

## Overview

devs supports layered environment variable configuration with the following priority order:

1. **CLI `--env` flags** (highest priority)
2. **`~/.devs/envs/{org-repo}/DEVS.yml`** (user-specific project overrides)  
3. **`~/.devs/envs/default/DEVS.yml`** (user defaults)
4. **`{project-root}/DEVS.yml`** (repository configuration)

## Scenario 1: Development Team with Shared Defaults

### Repository Configuration (`project-root/DEVS.yml`)
```yaml
# Team shared configuration
env_vars:
  default:
    NODE_ENV: development
    API_URL: https://api.example.com
    LOG_LEVEL: info
    DEBUG: "false"
  
  frontend:
    NODE_ENV: development
    PORT: "3000"
    DEBUG: "true"
    
  backend:
    NODE_ENV: development  
    PORT: "8080"
    DATABASE_URL: postgres://localhost/myapp_dev
```

### User Global Defaults (`~/.devs/envs/default/DEVS.yml`)
```yaml
# Personal preferences across all projects
env_vars:
  default:
    EDITOR: vim
    TIMEZONE: "America/New_York"
    LOG_LEVEL: debug  # I prefer more verbose logging
  
  frontend:
    BROWSER: firefox  # My preferred browser for frontend dev
```

### Usage
```bash
# Basic usage - gets team defaults + user preferences
devs start frontend backend

# Quick override for testing
devs start frontend --env API_URL=http://localhost:3001 --env DEBUG=false
```

**Result for 'frontend' container:**
```
API_URL=http://localhost:3001  # CLI override
BROWSER=firefox               # User default  
DEBUG=false                   # CLI override
EDITOR=vim                    # User default
LOG_LEVEL=debug               # User default (overrides team)
NODE_ENV=development          # Repository
PORT=3000                     # Repository
TIMEZONE=America/New_York     # User default
```

## Scenario 2: Multi-Environment Setup

### User Project-Specific Config (`~/.devs/envs/mycompany-webapp/DEVS.yml`)
```yaml
# Project-specific secrets and overrides
env_vars:
  default:
    API_URL: https://mycompany-dev-api.internal  # Internal dev API
    FEATURE_FLAGS: "experimental,beta"
  
  staging:
    API_URL: https://mycompany-staging-api.internal
    NODE_ENV: staging
    FEATURE_FLAGS: "beta"
    
  production:
    API_URL: https://api.mycompany.com
    NODE_ENV: production
    FEATURE_FLAGS: ""
    SECRET_KEY: "${PROD_SECRET_KEY}"  # Reference to environment variable
```

### Usage
```bash
# Development environment
devs start dev

# Staging-like environment locally
devs start staging

# Production simulation (be careful!)
export PROD_SECRET_KEY="your-secret"
devs start production --env LOG_LEVEL=debug  # Add debug for troubleshooting
```

## Scenario 3: Webhook CI Configuration

### Repository CI Setup (`project-root/DEVS.yml`)
```yaml
# Enable CI and set environment variables
ci_enabled: true
ci_test_command: npm run test:ci
ci_branches:
  - main
  - develop
  - release/*

env_vars:
  default:
    NODE_ENV: test
    CI: "true"
    DISABLE_NOTIFICATIONS: "true"
  
  eamonn:  # First CI container
    TEST_PARALLEL: "4"
    COVERAGE_ENABLED: "true"
    
  harry:   # Second CI container
    TEST_PARALLEL: "2" 
    INTEGRATION_TESTS: "true"
    
  darren:  # Third CI container  
    TEST_PARALLEL: "1"
    E2E_TESTS: "true"
```

### User CI Overrides (`~/.devs/envs/default/DEVS.yml`)
```yaml
# Personal CI preferences
env_vars:
  default:
    PLAYWRIGHT_BROWSER: firefox  # I prefer testing with Firefox
    
  eamonn:
    TEST_TIMEOUT: "30000"        # I need longer timeouts
```

**When webhook runs tests:** Environment variables are automatically applied based on which container (eamonn/harry/darren) handles the CI task.

## Scenario 4: Security-Sensitive Configuration

### Repository (Public) - No Secrets (`project-root/DEVS.yml`)
```yaml
# Only non-sensitive defaults in public repo
env_vars:
  default:
    NODE_ENV: development
    LOG_LEVEL: info
    FEATURE_BETA: "false"
```

### User Secrets (`~/.devs/envs/sensitive-client-project/DEVS.yml`)
```yaml
# Sensitive configuration only on developer's machine
env_vars:
  default:
    DATABASE_URL: "postgres://user:pass@localhost/client_db"
    STRIPE_SECRET_KEY: "sk_test_..."
    JWT_SECRET: "super-secret-key"
    EXTERNAL_API_KEY: "api-key-123"
  
  production-test:
    DATABASE_URL: "postgres://user:pass@staging-db.internal/client_db"
    STRIPE_SECRET_KEY: "sk_live_..."
    NODE_ENV: production
```

### Usage
```bash
# Development with secrets
devs start dev

# Test against production-like environment
devs start production-test

# Override specific secret for testing
devs start dev --env STRIPE_SECRET_KEY=sk_test_different_key
```

**Benefits:**
- Secrets never committed to repository
- Each developer can have their own keys
- Easy to test different configurations
- Webhook won't have access to sensitive user configs unless explicitly shared

## Scenario 5: CLI Testing and Debugging

### Quick Override Examples
```bash
# Debug mode for troubleshooting
devs claude frontend "Fix the login bug" --env DEBUG=true --env LOG_LEVEL=trace

# Test with different API endpoint
devs start api --env API_URL=http://localhost:3001 --env CORS_ORIGIN=*

# Simulate production environment
devs start app --env NODE_ENV=production --env CACHE_TTL=3600

# Test with feature flags
devs runtests backend --env FEATURE_NEW_AUTH=true --env FEATURE_CACHING=false

# Multiple environment overrides
devs vscode frontend \
  --env API_URL=https://staging-api.example.com \
  --env DEBUG=true \
  --env FEATURE_BETA=true \
  --env TEST_USER=developer
```

## Scenario 6: Webhook Optimization (No Repository Cloning)

### User Configuration with CI Enabled (`~/.devs/envs/fastproject-api/DEVS.yml`)
```yaml
# Complete configuration without needing to clone repo
ci_enabled: true
ci_test_command: "docker-compose -f docker-compose.test.yml up --abort-on-container-exit"
ci_branches: ["main", "develop", "staging"]

env_vars:
  default:
    NODE_ENV: test
    DATABASE_URL: "postgres://test:test@localhost:5433/testdb"
    
  eamonn:
    PARALLEL_WORKERS: "4"
    
  harry: 
    INTEGRATION_TESTS: "true"
    
  darren:
    E2E_TESTS: "true"
    HEADLESS: "true"
```

**Result:** When webhook receives events for `fastproject/api`, it immediately uses this configuration without cloning the repository first, making the response much faster.

## Best Practices

### 1. Security
- Keep secrets in user-specific files (`~/.devs/envs/`)
- Use environment variable references for sensitive values
- Never commit secrets to repository DEVS.yml

### 2. Team Collaboration
- Use repository DEVS.yml for team shared defaults
- Document environment variables in README
- Use descriptive variable names

### 3. Development Workflow
- Use CLI `--env` for quick testing
- Set up user defaults for your preferences
- Use project-specific config for different environments

### 4. Container Management
- Use container-specific variables for specialized setups
- Consider resource allocation (parallel workers, memory limits)
- Test CI configuration locally with `devs runtests`

### 5. Webhook Performance
- Set up user-specific configuration for faster webhook responses
- Use CI branch filtering to avoid unnecessary test runs
- Configure appropriate container timeouts

This layered approach provides maximum flexibility while maintaining security and team collaboration benefits.