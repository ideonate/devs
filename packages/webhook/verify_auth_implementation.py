#!/usr/bin/env python3
"""Simple verification that authentication code is properly implemented."""

import sys
import os
import importlib.util

def verify_config_changes():
    """Verify config.py has the new auth fields."""
    print("Checking config.py changes...")
    
    with open("devs_webhook/config.py", "r") as f:
        content = f.read()
    
    required_fields = [
        "admin_username",
        "admin_password",
        "ADMIN_PASSWORD) - required in production mode"
    ]
    
    for field in required_fields:
        if field in content:
            print(f"  ✓ Found: {field}")
        else:
            print(f"  ✗ Missing: {field}")
            return False
    
    return True

def verify_app_changes():
    """Verify app.py has authentication implementation."""
    print("\nChecking app.py changes...")
    
    with open("devs_webhook/app.py", "r") as f:
        content = f.read()
    
    required_imports = [
        "import secrets",
        "from fastapi.security import HTTPBasic, HTTPBasicCredentials",
        "security = HTTPBasic()"
    ]
    
    required_functions = [
        "def verify_admin_credentials",
        "Depends(verify_admin_credentials)"
    ]
    
    all_good = True
    
    for item in required_imports + required_functions:
        if item in content:
            print(f"  ✓ Found: {item[:50]}...")
        else:
            print(f"  ✗ Missing: {item}")
            all_good = False
    
    # Check that protected endpoints use the auth dependency
    endpoints_to_check = [
        ("@app.get(\"/status\")", "Depends(verify_admin_credentials)"),
        ("@app.get(\"/containers\")", "Depends(verify_admin_credentials)"),
        ("@app.post(\"/container/{container_name}/stop\")", "Depends(verify_admin_credentials)")
    ]
    
    print("\nChecking endpoint protection...")
    for endpoint, auth_check in endpoints_to_check:
        # Find the endpoint in content
        if endpoint in content:
            # Get the function definition following the decorator
            start_idx = content.find(endpoint)
            end_idx = content.find("\n@app.", start_idx + 1)
            if end_idx == -1:
                end_idx = content.find("\n\n@", start_idx + 1)
            if end_idx == -1:
                end_idx = len(content)
            
            function_content = content[start_idx:end_idx]
            
            if auth_check in function_content:
                print(f"  ✓ {endpoint} is protected")
            else:
                print(f"  ✗ {endpoint} is NOT protected")
                all_good = False
        else:
            print(f"  ? Could not find {endpoint}")
    
    return all_good

def verify_env_example():
    """Verify .env.example has the new fields."""
    print("\nChecking .env.example...")
    
    with open(".env.example", "r") as f:
        content = f.read()
    
    required_entries = [
        "ADMIN_USERNAME",
        "ADMIN_PASSWORD"
    ]
    
    for entry in required_entries:
        if entry in content:
            print(f"  ✓ Found: {entry}")
        else:
            print(f"  ✗ Missing: {entry}")
            return False
    
    return True

def main():
    """Run all verification checks."""
    print("=" * 60)
    print("Authentication Implementation Verification")
    print("=" * 60)
    
    os.chdir("/workspaces/ideonate-devs-kevin/packages/webhook")
    
    all_good = True
    
    # Run checks
    all_good = verify_config_changes() and all_good
    all_good = verify_app_changes() and all_good
    all_good = verify_env_example() and all_good
    
    # Check for test files
    print("\nChecking test files...")
    test_files = [
        "tests/test_authentication.py",
        "test_auth.py",
        "docs/AUTHENTICATION.md"
    ]
    
    for test_file in test_files:
        if os.path.exists(test_file):
            print(f"  ✓ Found: {test_file}")
        else:
            print(f"  ✗ Missing: {test_file}")
            all_good = False
    
    print("\n" + "=" * 60)
    if all_good:
        print("✅ All authentication components are properly implemented!")
        print("\nNext steps:")
        print("1. Set ADMIN_PASSWORD in your .env file")
        print("2. Restart the webhook service")
        print("3. Test with: python3 test_auth.py --password your-password")
    else:
        print("❌ Some authentication components are missing or incorrect.")
        print("Please review the implementation.")
        sys.exit(1)

if __name__ == "__main__":
    main()