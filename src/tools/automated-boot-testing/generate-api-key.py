#!/usr/bin/env python3
"""
Generate API keys for the ADS-B Test Service.

This utility creates cryptographically secure API keys that can be added
to the service configuration file.

Usage:
    python3 generate-api-key.py [user_identifier]

Example:
    python3 generate-api-key.py github-ci
    python3 generate-api-key.py developer1
"""

import argparse
import json
import secrets
import sys
from pathlib import Path


def generate_api_key() -> str:
    """Generate a cryptographically secure API key."""
    # Generate 32 bytes (256 bits) of random data
    # url_safe variant uses base64 encoding safe for URLs
    return secrets.token_urlsafe(32)


def main():
    parser = argparse.ArgumentParser(
        description="Generate API keys for ADS-B Test Service",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Generate a key for GitHub CI:
    python3 generate-api-key.py github-ci

  Generate a key for a developer:
    python3 generate-api-key.py developer1

  Interactive mode (no arguments):
    python3 generate-api-key.py
        """
    )
    parser.add_argument(
        "user_id",
        nargs="?",
        help="User identifier for this API key (e.g., 'github-ci', 'developer1')"
    )
    parser.add_argument(
        "--count",
        type=int,
        default=1,
        help="Number of keys to generate (default: 1)"
    )

    args = parser.parse_args()

    # Get user identifier
    if args.user_id:
        user_id = args.user_id
    else:
        user_id = input("Enter user identifier for this key (e.g., 'github-ci', 'developer1'): ").strip()
        if not user_id:
            print("Error: User identifier is required")
            sys.exit(1)

    # Validate user_id
    if not user_id.replace("-", "").replace("_", "").isalnum():
        print(f"Warning: User identifier '{user_id}' contains special characters")
        confirm = input("Continue? (y/n): ").strip().lower()
        if confirm != 'y':
            sys.exit(0)

    print(f"\n{'='*70}")
    print(f"Generating {args.count} API key(s) for user: {user_id}")
    print(f"{'='*70}\n")

    keys = []
    for i in range(args.count):
        api_key = generate_api_key()
        keys.append((api_key, user_id if args.count == 1 else f"{user_id}-{i+1}"))

        current_user_id = user_id if args.count == 1 else f"{user_id}-{i+1}"

        print(f"Key {i+1}:")
        print(f"  API Key: {api_key}")
        print(f"  User ID: {current_user_id}")
        print()

    # Show configuration example
    print(f"{'='*70}")
    print("Configuration")
    print(f"{'='*70}\n")

    print("Add the following to your config.json file:")
    print()
    print('"api_keys": {')
    for api_key, uid in keys:
        print(f'  "{api_key}": "{uid}"{" " if (api_key, uid) == keys[-1] else ","} ')
    print('}')
    print()

    # Show usage example
    print(f"{'='*70}")
    print("Usage")
    print(f"{'='*70}\n")

    print("Test the API with curl:")
    print()
    example_key, example_user = keys[0]
    print(f'curl -X POST http://localhost:8080/api/trigger-boot-test \\')
    print(f'  -H "X-API-Key: {example_key}" \\')
    print(f'  -H "Content-Type: application/json" \\')
    print(f'  -d \'{{"url": "https://github.com/dirkhh/adsb-feeder-image/releases/download/v1.0/test.img.xz"}}\'')
    print()

    # Security reminder
    print(f"{'='*70}")
    print("Security Reminders")
    print(f"{'='*70}\n")

    print("• Store API keys securely (e.g., in environment variables or secrets manager)")
    print("• Never commit API keys to version control")
    print("• Rotate keys periodically")
    print("• Use HTTPS in production to protect keys in transit")
    print("• Each user/system should have its own unique key")
    print()


if __name__ == "__main__":
    main()
