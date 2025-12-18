#!/usr/bin/env python3
"""
Script to bump version numbers of all three devs packages and publish to PyPI.

Usage:
    python scripts/bump-and-publish.py [patch|minor|major]

Default is 'patch' if no argument provided.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import Tuple

# Package directories
PACKAGES = [
    "packages/common",
    "packages/cli", 
    "packages/webhook"
]

def parse_version(version_str: str) -> Tuple[int, int, int]:
    """Parse semantic version string into tuple."""
    match = re.match(r"(\d+)\.(\d+)\.(\d+)", version_str)
    if not match:
        raise ValueError(f"Invalid version format: {version_str}")
    return tuple(map(int, match.groups()))

def bump_version(version_str: str, bump_type: str) -> str:
    """Bump version according to type (patch, minor, major)."""
    major, minor, patch = parse_version(version_str)
    
    if bump_type == "patch":
        patch += 1
    elif bump_type == "minor":
        minor += 1
        patch = 0
    elif bump_type == "major":
        major += 1
        minor = 0
        patch = 0
    else:
        raise ValueError(f"Invalid bump type: {bump_type}")
    
    return f"{major}.{minor}.{patch}"

def get_current_version(pyproject_path: Path) -> str:
    """Extract current version from pyproject.toml."""
    content = pyproject_path.read_text()
    match = re.search(r'version = "([^"]+)"', content)
    if not match:
        raise ValueError(f"Could not find version in {pyproject_path}")
    return match.group(1)

def update_version_in_file(pyproject_path: Path, new_version: str) -> None:
    """Update version in pyproject.toml file - only in [project] section."""
    content = pyproject_path.read_text()
    lines = content.split('\n')
    
    in_project_section = False
    updated_lines = []
    
    for line in lines:
        # Check if we're entering the [project] section
        if line.strip() == '[project]':
            in_project_section = True
        # Check if we're leaving the [project] section (entering another section)
        elif line.strip().startswith('[') and line.strip().endswith(']'):
            in_project_section = False
        
        # Update version line only if we're in the [project] section
        if in_project_section and line.strip().startswith('version = "'):
            updated_lines.append(f'version = "{new_version}"')
        else:
            updated_lines.append(line)
    
    updated_content = '\n'.join(updated_lines)
    pyproject_path.write_text(updated_content)

def run_command(cmd: list, cwd: Path = None) -> None:
    """Run command and handle errors."""
    print(f"Running: {' '.join(cmd)}" + (f" in {cwd}" if cwd else ""))
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    
    if result.returncode != 0:
        print(f"Error running command: {' '.join(cmd)}")
        print(f"stdout: {result.stdout}")
        print(f"stderr: {result.stderr}")
        sys.exit(1)
    
    if result.stdout.strip():
        print(f"Output: {result.stdout}")

def main():
    parser = argparse.ArgumentParser(description="Bump versions and publish packages")
    parser.add_argument("bump_type", nargs="?", default="patch", 
                       choices=["patch", "minor", "major"],
                       help="Version bump type (default: patch)")
    
    args = parser.parse_args()
    
    project_root = Path(__file__).parent.parent
    
    print(f"Bumping versions ({args.bump_type}) and publishing packages...")
    
    # Step 1: Check all packages exist and get current versions
    package_info = []
    for package_dir in PACKAGES:
        pkg_path = project_root / package_dir
        pyproject_path = pkg_path / "pyproject.toml"
        
        if not pyproject_path.exists():
            print(f"Error: {pyproject_path} not found")
            sys.exit(1)
        
        current_version = get_current_version(pyproject_path)
        new_version = bump_version(current_version, args.bump_type)
        
        package_info.append({
            "dir": pkg_path,
            "pyproject": pyproject_path,
            "current": current_version,
            "new": new_version
        })
        
        print(f"{package_dir}: {current_version} -> {new_version}")
    
    # Step 2: Update all versions
    print("\nUpdating version numbers...")
    for info in package_info:
        update_version_in_file(info["pyproject"], info["new"])
        print(f"Updated {info['pyproject']}")
    
    # Step 3: Build and upload packages in dependency order (common first)
    upload_order = ["packages/common", "packages/cli", "packages/webhook"]
    
    for package_dir in upload_order:
        pkg_path = project_root / package_dir
        package_name = pkg_path.name
        
        print(f"\n{'='*50}")
        print(f"Building and uploading {package_name}")
        print(f"{'='*50}")
        
        # Clean previous builds
        dist_dir = pkg_path / "dist"
        if dist_dir.exists():
            run_command(["rm", "-rf", "dist"], cwd=pkg_path)
        
        # Build package
        print(f"Building {package_name}...")
        run_command(["python", "-m", "build"], cwd=pkg_path)
        
        # Upload to PyPI
        print(f"Uploading {package_name} to PyPI...")
        run_command(["twine", "upload", "dist/*"], cwd=pkg_path)
        
        print(f"✓ {package_name} published successfully")
    
    print(f"\n{'='*50}")
    print("All packages published successfully!")
    print(f"{'='*50}")
    
    # Print summary
    print("\nVersion summary:")
    for info in package_info:
        pkg_name = info["dir"].name
        print(f"  {pkg_name}: {info['current']} -> {info['new']}")

if __name__ == "__main__":
    main()