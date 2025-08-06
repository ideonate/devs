#!/usr/bin/env python3
"""Test script to verify async conversion works correctly."""

import asyncio
import sys
from pathlib import Path

# Add packages to path
sys.path.insert(0, str(Path(__file__).parent / "packages" / "common"))
sys.path.insert(0, str(Path(__file__).parent / "packages" / "cli"))

async def test_async_imports():
    """Test that all async modules can be imported."""
    print("Testing async imports...")
    
    try:
        from devs_common.utils import (
            AsyncDockerClient,
            AsyncDevContainerCLI,
            get_tracked_files_async,
            is_git_repository_async,
            copy_file_list_async,
        )
        from devs_common.core import AsyncContainerManager, AsyncWorkspaceManager
        print("✅ Common package async imports successful")
    except ImportError as e:
        print(f"❌ Common package import error: {e}")
        return False
    
    try:
        from devs.core.async_wrappers import SyncContainerManager, SyncWorkspaceManager
        print("✅ CLI package wrapper imports successful")
    except ImportError as e:
        print(f"❌ CLI package import error: {e}")
        return False
    
    return True


async def test_async_docker_client():
    """Test AsyncDockerClient basic functionality."""
    print("\nTesting AsyncDockerClient...")
    
    from devs_common.utils import AsyncDockerClient
    
    try:
        async with AsyncDockerClient() as docker:
            # Test ping
            print("✅ Docker client connected successfully")
            
            # Test finding containers
            containers = await docker.find_containers_by_labels({})
            print(f"✅ Found {len(containers)} containers")
            
    except Exception as e:
        print(f"❌ Docker client error: {e}")
        return False
    
    return True


async def test_git_utils():
    """Test async git utilities."""
    print("\nTesting async git utilities...")
    
    from devs_common.utils import is_git_repository_async, get_git_root_async
    
    try:
        # Test current directory
        current_dir = Path.cwd()
        is_git = await is_git_repository_async(current_dir)
        print(f"✅ Current directory is{'a git repository' if is_git else 'not a git repository'}")
        
        if is_git:
            git_root = await get_git_root_async(current_dir)
            print(f"✅ Git root: {git_root}")
    except Exception as e:
        print(f"❌ Git utils error: {e}")
        return False
    
    return True


async def test_sync_wrappers():
    """Test sync wrappers for CLI package."""
    print("\nTesting sync wrappers...")
    
    try:
        from devs_common.core import Project
        from devs.core.async_wrappers import SyncWorkspaceManager
        
        # Create a project
        project = Project()
        print(f"✅ Created project: {project.info.name}")
        
        # Create sync workspace manager
        workspace_manager = SyncWorkspaceManager(project)
        
        # Test workspace directory generation
        workspace_dir = workspace_manager.get_workspace_dir("test")
        print(f"✅ Generated workspace path: {workspace_dir}")
        
        # List workspaces
        workspaces = workspace_manager.list_workspaces()
        print(f"✅ Found {len(workspaces)} workspaces")
        
    except Exception as e:
        print(f"❌ Sync wrapper error: {e}")
        return False
    
    return True


async def main():
    """Run all tests."""
    print("=" * 60)
    print("ASYNC CONVERSION TEST SUITE")
    print("=" * 60)
    
    results = []
    
    # Run tests
    results.append(await test_async_imports())
    results.append(await test_async_docker_client())
    results.append(await test_git_utils())
    results.append(await test_sync_wrappers())
    
    # Summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    
    passed = sum(results)
    total = len(results)
    
    if passed == total:
        print(f"✅ All {total} tests passed!")
        return 0
    else:
        print(f"❌ {passed}/{total} tests passed")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)