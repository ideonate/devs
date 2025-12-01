"""DEVS.yml configuration loading and management.

This module provides shared configuration handling for DEVS.yml files
across the CLI and webhook packages.
"""

from pathlib import Path
from typing import Dict, Optional, List, Any
from pydantic import BaseModel, Field
import yaml
import logging

logger = logging.getLogger(__name__)


class DevsOptions(BaseModel):
    """DEVS.yml configuration options."""
    default_branch: str = "main"
    prompt_extra: str = ""
    prompt_override: Optional[str] = None
    direct_commit: bool = False
    single_queue: bool = False  # Restrict repo to single queue processing
    ci_enabled: bool = False  # Enable CI mode for this repository
    ci_test_command: str = "./runtests.sh"  # Command to run for CI tests
    ci_branches: List[str] = ["main", "master"]  # Branches to run CI on for push events
    env_vars: Dict[str, Dict[str, str]] = Field(default_factory=dict)  # Environment variables
    
    def get_env_vars(self, container_name: Optional[str] = None) -> Dict[str, str]:
        """Get environment variables for a specific container or defaults.
        
        Args:
            container_name: Container/dev environment name. If None, returns only defaults.
            
        Returns:
            Dictionary of environment variables with container-specific overrides applied.
        """
        env = self.env_vars.get('default', {}).copy()
        if container_name and container_name in self.env_vars:
            env.update(self.env_vars[container_name])
        return env


class DevsConfigLoader:
    """Loads DEVS.yml configuration from multiple sources with priority ordering."""
    
    @staticmethod
    def _load_file(file_path: Path) -> Dict[str, Any]:
        """Load a single DEVS.yml file.
        
        Args:
            file_path: Path to DEVS.yml file
            
        Returns:
            Dictionary with file contents or empty dict if file doesn't exist
        """
        if not file_path.exists():
            return {}
        
        try:
            with open(file_path, 'r') as f:
                data = yaml.safe_load(f)
            
            return data or {}
            
        except Exception as e:
            logger.warning(f"Failed to parse {file_path}: {e}")
            return {}
    
    @staticmethod
    def _merge_configs(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Merge two configurations with override taking priority.
        
        Special handling for env_vars to merge nested dictionaries properly.
        
        Args:
            base: Base configuration
            override: Configuration to override with
            
        Returns:
            Merged configuration
        """
        result = base.copy()
        
        for key, value in override.items():
            if key == 'env_vars' and key in result:
                # Special handling for env_vars - merge the nested dictionaries
                merged_env_vars = result[key].copy()
                for env_key, env_value in value.items():
                    if env_key in merged_env_vars:
                        merged_env_vars[env_key].update(env_value)
                    else:
                        merged_env_vars[env_key] = env_value.copy()
                result[key] = merged_env_vars
            else:
                # For all other fields, simple override
                result[key] = value
        
        return result
    
    @staticmethod
    def load(project_name: Optional[str] = None, repo_path: Optional[Path] = None) -> DevsOptions:
        """Load DEVS.yml configuration from multiple sources.
        
        Priority order (highest to lowest):
        1. ~/.devs/envs/{org-repo}/DEVS.yml (user-specific project overrides)
        2. ~/.devs/envs/default/DEVS.yml (user defaults)
        3. {repo_path}/DEVS.yml (repository configuration)
        
        Args:
            project_name: Project name in org-repo format. If None, only loads repo and default configs.
            repo_path: Path to repository (defaults to cwd if not provided)
            
        Returns:
            DevsOptions with merged configuration
        """
        if repo_path is None:
            repo_path = Path.cwd()
        
        merged_config = {}
        
        # 1. Load repository DEVS.yml (lowest priority)
        repo_devs_yml = repo_path / "DEVS.yml"
        merged_config = DevsConfigLoader._merge_configs(
            merged_config, 
            DevsConfigLoader._load_file(repo_devs_yml)
        )
        
        # 2. Load user default DEVS.yml
        user_envs_dir = Path.home() / ".devs" / "envs"
        default_devs_yml = user_envs_dir / "default" / "DEVS.yml"
        merged_config = DevsConfigLoader._merge_configs(
            merged_config,
            DevsConfigLoader._load_file(default_devs_yml)
        )
        
        # 3. Load user project-specific DEVS.yml (highest priority)
        if project_name:
            project_devs_yml = user_envs_dir / project_name / "DEVS.yml"
            merged_config = DevsConfigLoader._merge_configs(
                merged_config,
                DevsConfigLoader._load_file(project_devs_yml)
            )
        
        # Create DevsOptions from merged config
        return DevsOptions(**merged_config)
    
    @staticmethod
    def load_env_vars(dev_name: str, project_name: Optional[str] = None, 
                      repo_path: Optional[Path] = None) -> Dict[str, str]:
        """Load only environment variables for a specific dev environment.
        
        This is a convenience method for CLI usage.
        
        Args:
            dev_name: Development environment/container name
            project_name: Project name in org-repo format
            repo_path: Path to repository (defaults to cwd if not provided)
            
        Returns:
            Dictionary of environment variables with all overrides applied
        """
        options = DevsConfigLoader.load(project_name, repo_path)
        return options.get_env_vars(dev_name)