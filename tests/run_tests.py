#!/usr/bin/env python3
"""
Test runner script for adsb-setup application
"""
import sys
import os
import subprocess
import argparse
from pathlib import Path


def run_command(cmd, description):
    """Run a command and return the result"""
    print(f"\n{'='*60}")
    print(f"Running: {description}")
    print(f"Command: {' '.join(cmd)}")
    print(f"{'='*60}")

    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.stdout:
        print("STDOUT:")
        print(result.stdout)

    if result.stderr:
        print("STDERR:")
        print(result.stderr)

    print(f"Return code: {result.returncode}")
    return result.returncode == 0


def main():
    parser = argparse.ArgumentParser(description="Run tests for adsb-setup application")
    parser.add_argument("--unit", action="store_true", help="Run unit tests only")
    parser.add_argument("--integration", action="store_true", help="Run integration tests only")
    parser.add_argument("--coverage", action="store_true", help="Run with coverage")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--parallel", "-n", type=int, help="Run tests in parallel with n workers")
    parser.add_argument("--markers", "-m", help="Run tests with specific markers")
    parser.add_argument("--skip-slow", action="store_true", help="Skip slow tests")
    parser.add_argument("--lint", action="store_true", help="Run linting checks")
    parser.add_argument("--security", action="store_true", help="Run security checks")
    parser.add_argument("--all", action="store_true", help="Run all checks")

    args = parser.parse_args()

    # Change to project root directory
    project_root = Path(__file__).parent.parent
    os.chdir(project_root)

    success = True

    # Base pytest command
    pytest_cmd = ["python", "-m", "pytest"]

    if args.verbose:
        pytest_cmd.append("-v")

    if args.parallel:
        pytest_cmd.extend(["-n", str(args.parallel)])

    if args.coverage:
        pytest_cmd.extend([
            "--cov=src/modules/adsb-feeder/filesystem/root/opt/adsb/adsb-setup",
            "--cov-report=html",
            "--cov-report=xml",
            "--cov-report=term-missing"
        ])

    if args.skip_slow:
        pytest_cmd.extend(["-m", "not slow"])

    if args.markers:
        pytest_cmd.extend(["-m", args.markers])

    # Run linting
    if args.lint or args.all:
        lint_commands = [
            (["python", "-m", "flake8", "src/modules/adsb-feeder/filesystem/root/opt/adsb/adsb-setup/", "--max-line-length=127"], "Flake8 linting"),
            (["python", "-m", "black", "--check", "src/modules/adsb-feeder/filesystem/root/opt/adsb/adsb-setup/"], "Black formatting check"),
            (["python", "-m", "isort", "--check-only", "src/modules/adsb-feeder/filesystem/root/opt/adsb/adsb-setup/"], "Import sorting check"),
        ]

        for cmd, desc in lint_commands:
            if not run_command(cmd, desc):
                success = False

    # Run security checks
    if args.security or args.all:
        security_commands = [
            (["python", "-m", "bandit", "-r", "src/modules/adsb-feeder/filesystem/root/opt/adsb/adsb-setup/", "-f", "json", "-o", "bandit-report.json"], "Bandit security scan"),
            (["python", "-m", "safety", "check", "--json", "--output", "safety-report.json"], "Safety dependency check"),
        ]

        for cmd, desc in security_commands:
            if not run_command(cmd, desc):
                success = False

    # Run tests
    if args.unit or args.integration or not (args.lint or args.security):
        if args.unit:
            pytest_cmd.append("tests/unit/")
        elif args.integration:
            pytest_cmd.append("tests/integration/")
        else:
            pytest_cmd.append("tests/")

        if not run_command(pytest_cmd, "Running tests"):
            success = False

    # Summary
    print(f"\n{'='*60}")
    if success:
        print("✅ All checks passed!")
    else:
        print("❌ Some checks failed!")
    print(f"{'='*60}")

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
