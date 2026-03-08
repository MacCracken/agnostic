#!/usr/bin/env python3
"""
Test runner script for the Agentic QA Team System.
Provides different test execution modes and environments.
"""

import os
import sys
import argparse
import subprocess
from pathlib import Path


def run_command(cmd, description):
    """Run a command and handle errors"""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'='*60}")
    
    try:
        result = subprocess.run(cmd, check=False, capture_output=True, text=True)
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        # Exit code 0 = passed, 5 = no tests collected (all skipped) — both OK
        if result.returncode in (0, 5):
            return True
        print(f"Error running {description} (exit code {result.returncode})")
        return False
    except Exception as e:
        print(f"Error running {description}: {e}")
        return False


def setup_test_environment():
    """Setup test environment by starting test services"""
    print("Setting up test environment...")
    
    # Start test services
    if not run_command([
        "docker", "compose", "-f", "docker-compose.test.yml", 
        "up", "-d", "redis-test", "rabbitmq-test"
    ], "Start test services"):
        return False
    
    # Wait for services to be ready
    import time
    time.sleep(10)
    
    return True


def teardown_test_environment():
    """Tear down test environment"""
    print("Tearing down test environment...")
    run_command([
        "docker", "compose", "-f", "docker-compose.test.yml", 
        "down", "-v"
    ], "Stop test services")


def run_unit_tests():
    """Run unit tests only"""
    return run_command([
        "python", "-m", "pytest", 
        "tests/unit/",
        "-v",
        "--tb=short",
        "--disable-warnings"
    ], "Unit Tests")


def run_integration_tests():
    """Run integration tests"""
    return run_command([
        "python", "-m", "pytest", 
        "tests/integration/",
        "-v",
        "--tb=short",
        "-m", "not slow",
        "--disable-warnings"
    ], "Integration Tests")


def run_all_tests():
    """Run all tests"""
    return run_command([
        "python", "-m", "pytest", 
        "tests/",
        "-v",
        "--tb=short",
        "-m", "not slow",
        "--disable-warnings"
    ], "All Tests")


def run_coverage():
    """Run tests with coverage report"""
    return run_command([
        "python", "-m", "pytest", 
        "tests/",
        "--cov=agents",
        "--cov=config", 
        "--cov=webgui",
        "--cov-report=term-missing",
        "--cov-report=html:htmlcov",
        "--cov-report=xml",
        "-v",
        "--disable-warnings"
    ], "Tests with Coverage")


def run_slow_tests():
    """Run slow integration tests"""
    return run_command([
        "python", "-m", "pytest", 
        "tests/integration/",
        "-v",
        "-m", "slow",
        "--tb=short",
        "--disable-warnings"
    ], "Slow Integration Tests")


def main():
    parser = argparse.ArgumentParser(description="Test runner for Agentic QA System")
    parser.add_argument("--mode", choices=[
        "unit", "integration", "all", "coverage", "slow"
    ], default="all", help="Test mode to run")
    parser.add_argument("--env", choices=["mock", "docker"], default="mock",
                       help="Test environment setup")
    parser.add_argument("--setup", action="store_true", 
                       help="Setup test environment")
    parser.add_argument("--teardown", action="store_true",
                       help="Teardown test environment")
    
    args = parser.parse_args()
    
    # Change to project root
    project_root = Path(__file__).parent
    os.chdir(project_root)
    
    success = True
    
    if args.setup:
        if args.env == "docker":
            success = setup_test_environment()
    
    if success:
        # Run tests based on mode
        if args.mode == "unit":
            success = run_unit_tests()
        elif args.mode == "integration":
            if args.env == "docker":
                success = setup_test_environment()
            if success:
                success = run_integration_tests()
        elif args.mode == "all":
            success = run_all_tests()
        elif args.mode == "coverage":
            success = run_coverage()
        elif args.mode == "slow":
            if args.env == "docker":
                success = setup_test_environment()
            if success:
                success = run_slow_tests()
    
    if args.teardown or (args.env == "docker" and not success):
        teardown_test_environment()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()