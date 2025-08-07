#!/usr/bin/env python3
"""Test script for webhook authentication."""

import requests
from requests.auth import HTTPBasicAuth
import sys

def test_endpoints(base_url="http://localhost:8000", username="admin", password="testpass"):
    """Test authentication on various endpoints."""
    
    print(f"Testing endpoints at {base_url}")
    print(f"Using credentials: {username} / {'*' * len(password)}")
    print("-" * 50)
    
    # Test public endpoints
    public_endpoints = [
        ("/", "GET", "Health check"),
        ("/health", "GET", "Detailed health"),
    ]
    
    for endpoint, method, description in public_endpoints:
        url = f"{base_url}{endpoint}"
        print(f"\n{description} ({method} {endpoint}):")
        try:
            if method == "GET":
                resp = requests.get(url, timeout=5)
            print(f"  Status: {resp.status_code} - Public endpoint, no auth required")
        except Exception as e:
            print(f"  Error: {e}")
    
    # Test protected endpoints
    protected_endpoints = [
        ("/status", "GET", "Status"),
        ("/containers", "GET", "List containers"),
    ]
    
    for endpoint, method, description in protected_endpoints:
        url = f"{base_url}{endpoint}"
        print(f"\n{description} ({method} {endpoint}):")
        
        # Test without auth
        try:
            if method == "GET":
                resp = requests.get(url, timeout=5)
            print(f"  Without auth: {resp.status_code} - {'FAIL: Should be 401' if resp.status_code != 401 else 'OK (401 as expected)'}")
        except Exception as e:
            print(f"  Without auth error: {e}")
        
        # Test with auth
        try:
            auth = HTTPBasicAuth(username, password)
            if method == "GET":
                resp = requests.get(url, auth=auth, timeout=5)
            print(f"  With auth: {resp.status_code} - {'OK' if resp.status_code in [200, 201, 202] else 'FAIL'}")
            if resp.status_code == 200:
                print(f"    Response preview: {str(resp.json())[:100]}...")
        except Exception as e:
            print(f"  With auth error: {e}")
    
    print("\n" + "-" * 50)
    print("Test complete!")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Test webhook authentication")
    parser.add_argument("--url", default="http://localhost:8000", help="Base URL")
    parser.add_argument("--username", default="admin", help="Admin username")
    parser.add_argument("--password", default="testpass", help="Admin password")
    
    args = parser.parse_args()
    test_endpoints(args.url, args.username, args.password)