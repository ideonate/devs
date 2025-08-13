#!/usr/bin/env python3
"""
Visual webapp testing script using Playwright.
Takes screenshots of running webapps for development purposes.
"""

import argparse
import asyncio
import os
import sys
import time
import subprocess
import signal
from datetime import datetime, timezone
from playwright.async_api import async_playwright
from pathlib import Path

class WebappScreenshotter:
    def __init__(self, output_dir="webapp-screenshots"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)
        self.servers = []
        
    def start_server(self, command, cwd=None, wait_time=5):
        """Start a server process and wait for it to be ready."""
        print(f"Starting server: {command}")
        if cwd:
            print(f"Working directory: {cwd}")
            
        process = subprocess.Popen(
            command,
            shell=True,
            cwd=cwd,
            preexec_fn=os.setsid,  # Create new process group
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        self.servers.append(process)
        
        print(f"Waiting {wait_time} seconds for server to start...")
        time.sleep(wait_time)
        
        if process.poll() is not None:
            stdout, stderr = process.communicate()
            print(f"Server failed to start!")
            print(f"STDOUT: {stdout}")
            print(f"STDERR: {stderr}")
            return False
            
        return True
    
    def cleanup_servers(self):
        """Clean up all started servers."""
        for process in self.servers:
            if process.poll() is None:
                print(f"Terminating server process {process.pid}")
                try:
                    # Kill the entire process group
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                    process.wait(timeout=5)
                except (ProcessLookupError, subprocess.TimeoutExpired):
                    try:
                        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                    except ProcessLookupError:
                        pass
    
    async def screenshot_page(self, page, url, name, viewport_width=1280, viewport_height=720):
        """Take a screenshot of a specific page."""
        try:
            print(f"Navigating to {url}")
            await page.set_viewport_size({"width": viewport_width, "height": viewport_height})
            await page.goto(url, timeout=10000)
            
            # Wait for page to be ready
            await page.wait_for_load_state("networkidle", timeout=5000)
            
            # Take full page screenshot
            timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
            filename = f"{name}_{timestamp}.png"
            filepath = self.output_dir / filename
            
            await page.screenshot(path=str(filepath), full_page=True)
            print(f"Screenshot saved: {filepath}")
            
            return str(filepath)
            
        except Exception as e:
            print(f"Error taking screenshot of {url}: {e}")
            return None
    
    async def run_screenshots(self, urls, headless=True):
        """Run screenshot collection for multiple URLs."""
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=headless)
            context = await browser.new_context()
            page = await context.new_page()
            
            screenshots = []
            for url_config in urls:
                if isinstance(url_config, str):
                    url = url_config
                    name = url.replace("http://", "").replace("https://", "").replace("/", "_").replace(":", "_")
                else:
                    url = url_config["url"]
                    name = url_config.get("name", "page")
                
                screenshot_path = await self.screenshot_page(page, url, name)
                if screenshot_path:
                    screenshots.append(screenshot_path)
            
            await browser.close()
            return screenshots

def main():
    parser = argparse.ArgumentParser(description="Take screenshots of running webapps")
    parser.add_argument("--urls", nargs="+", help="URLs to screenshot", 
                       default=["http://localhost:3000", "http://localhost:8000", "http://localhost:8082"])
    parser.add_argument("--output-dir", default="webapp-screenshots", help="Output directory for screenshots")
    parser.add_argument("--start-servers", action="store_true", help="Auto-start common servers")
    parser.add_argument("--headless", action="store_true", default=True, help="Run browser in headless mode (default in containers)")
    
    args = parser.parse_args()
    
    screenshotter = WebappScreenshotter(args.output_dir)
    
    try:
        if args.start_servers:
            print("Auto-starting servers...")
            
            # Start frontend (React)
            if os.path.exists("frontend/package.json"):
                screenshotter.start_server("npm run dev", cwd="frontend", wait_time=10)
            
            # Start portal (React)  
            if os.path.exists("portal/package.json"):
                screenshotter.start_server("npm run dev", cwd="portal", wait_time=10)
            
            # Start webserver (Python)
            if os.path.exists("webserver/main.py"):
                # Try to activate venv and run
                if os.path.exists("webserver/venv"):
                    screenshotter.start_server("source venv/bin/activate && python main.py", cwd="webserver", wait_time=5)
                else:
                    screenshotter.start_server("python main.py", cwd="webserver", wait_time=5)
        
        # Take screenshots
        print(f"Taking screenshots of: {args.urls}")
        screenshots = asyncio.run(screenshotter.run_screenshots(args.urls, headless=args.headless))
        
        print(f"\nScreenshots completed!")
        print(f"Saved {len(screenshots)} screenshots to {args.output_dir}/")
        for screenshot in screenshots:
            print(f"  - {screenshot}")
            
    except KeyboardInterrupt:
        print("\nInterrupted by user")
    finally:
        screenshotter.cleanup_servers()

if __name__ == "__main__":
    main()