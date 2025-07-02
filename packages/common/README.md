# devs-common

Shared utilities and core classes for the devs package ecosystem.

## Components

- **Core Classes**: Project, WorkspaceManager, ContainerManager
- **Configuration**: Base configuration classes  
- **Exceptions**: Common exception hierarchy
- **Utilities**: Docker, Git, and file operation utilities

## Usage

```python
from devs_common.core import Project, WorkspaceManager, ContainerManager
from devs_common.config import BaseConfig
```

This package provides the shared foundation for both the devs CLI and webhook packages.