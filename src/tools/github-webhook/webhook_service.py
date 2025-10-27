#!/usr/bin/env python3
"""
GitHub Webhook Service for Release Binary Processing

This service listens for GitHub release webhooks and filters binaries
based on naming patterns to determine which ones qualify for additional tests.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import aiohttp
from fastapi import FastAPI, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Configure rate limiting
limiter = Limiter(key_func=get_remote_address)

app = FastAPI(
    title="GitHub Webhook Service",
    description="Service for processing GitHub release webhooks and filtering binaries",
    version="1.0.0",
)

# Add rate limiting to FastAPI
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)  # type: ignore[arg-type]

# Configuration
WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")
PORT = int(os.getenv("PORT", "9111"))
HOST = os.getenv("HOST", "127.0.0.1")
BOOT_TEST_API_URL = os.getenv("BOOT_TEST_API_URL", "http://localhost:9456/api/trigger-boot-test")
BOOT_TEST_API_KEY = os.getenv("BOOT_TEST_API_KEY")
BOOT_TEST_TIMEOUT = int(os.getenv("BOOT_TEST_TIMEOUT", "30"))


def verify_webhook_signature(payload_body: bytes, signature_header: str, secret: str) -> bool:
    """
    Verify GitHub webhook signature for security.

    Args:
        payload_body: Raw request body
        signature_header: X-Hub-Signature-256 header value
        secret: Webhook secret from GitHub

    Returns:
        True if signature is valid, False otherwise
    """
    if not signature_header or not secret:
        logger.warning("Missing signature or secret for webhook verification")
        return False

    # GitHub sends signature as "sha256=<hash>"
    if not signature_header.startswith("sha256="):
        logger.warning("Invalid signature format")
        return False

    expected_signature = signature_header[7:]  # Remove 'sha256=' prefix

    # Calculate expected signature
    calculated_signature = hmac.new(secret.encode("utf-8"), payload_body, hashlib.sha256).hexdigest()

    # Use constant-time comparison to prevent timing attacks
    return hmac.compare_digest(calculated_signature, expected_signature)


def validate_github_url(url: str) -> bool:
    """
    Validate that URL is a valid GitHub release URL.

    Args:
        url: URL to validate

    Returns:
        True if URL is valid, False otherwise
    """
    try:
        parsed = urlparse(url)
        return parsed.scheme == "https" and "github.com" in parsed.netloc and "/releases/download/" in parsed.path
    except Exception:
        return False


def matches_binary_filter(binary_name: str, release_name: str) -> bool:
    # if this is a testbuild, the assets can contain older versions from previous builds
    match = re.search(r"testbuild-(g-[0-9a-f]{8})", release_name)
    if match:
        # logger.info(f"Test build found: {match.group(1)}")
        testfilter = match.group(1)
        if testfilter not in binary_name:
            # logger.info(f"Test build {testfilter} not found in {binary_name}")
            return False

    # Must contain raspberrypi64 and release name must contain the word "beta"
    if "raspberrypi64" not in binary_name:
        # logger.info(f"Raspberry Pi 64 not found in {binary_name}")
        return False

    # Look for pi-* pattern with numbers
    # Pattern: pi- followed by numbers separated by dashes, then version
    pi_pattern = r"pi-([0-9-]+)-"
    match = re.search(pi_pattern, binary_name)

    if not match:
        return False

    # Extract the numbers part (e.g., "2-3-4" or "2-3-4-5" or "5")
    numbers_part = match.group(1)

    # Check if '4' is in the numbers part
    # This will match "2-3-4", "2-3-4-5" but not "5"
    return "4" in numbers_part


def extract_qualifying_binaries(release_data: Dict[str, Any]) -> List[Dict[str, str]]:
    qualifying_binaries = []

    # Get assets from the release
    assets = release_data.get("release", {}).get("assets", [])
    name = release_data.get("changes", {}).get("name", {}).get("from", "")
    if name == "":
        name = release_data.get("release", {}).get("name", "")

    for asset in assets:
        asset_name = asset.get("name", "")
        download_url = asset.get("browser_download_url", "")

        # Validate URL before adding
        if not validate_github_url(download_url):
            logger.warning(f"Invalid or suspicious URL: {download_url}")
            continue

        if matches_binary_filter(asset_name, name):
            created_at = asset.get("created_at", "")
            # compare that timestamp with the current time and if it is more than half an hour old,
            # ignore the asset as it definitely hasn't been submitted already
            if created_at:
                # Parse ISO timestamp (may include 'Z' for UTC or timezone info)
                asset_time = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
                current_time = datetime.now(asset_time.tzinfo) if asset_time.tzinfo else datetime.now()

                # Check if timestamp is more than half an hour old
                time_diff = current_time - asset_time
                if time_diff > timedelta(minutes=30):
                    logger.info(f"Ignoring {asset_name} because it was created more than half an hour ago")
                    continue
            qualifying_binaries.append({"name": asset_name, "url": download_url})
            logger.info(f"Found qualifying binary: {asset_name}")

    return qualifying_binaries


async def trigger_boot_test(binary_url: str, github_context: Optional[dict] = None) -> bool:
    """
    Trigger boot test for a qualifying binary URL.

    Args:
        binary_url: URL of the binary to test
        github_context: Optional dict with GitHub event info (release_id, pr_number, commit_sha, etc.)

    Returns:
        True if boot test was triggered successfully, False otherwise
    """
    if not BOOT_TEST_API_URL:
        logger.error("BOOT_TEST_API_URL not configured")
        return False

    if not BOOT_TEST_API_KEY:
        logger.error("BOOT_TEST_API_KEY not configured - cannot authenticate with boot test API")
        return False

    # Warn if using HTTP instead of HTTPS (unless localhost or Tailscale)
    # Tailscale uses 100.64.0.0/10 range (100.64.0.0 to 100.127.255.255)
    parsed_url = urlparse(BOOT_TEST_API_URL)
    is_localhost = parsed_url.hostname in ("localhost", "127.0.0.1", "::1")

    # Check if hostname is in Tailscale 100.64.0.0/10 range
    is_tailscale = False
    if parsed_url.hostname:
        try:
            parts = parsed_url.hostname.split(".")
            if len(parts) == 4 and parts[0] == "100":
                second_octet = int(parts[1])
                # 100.64.0.0/10 means second octet must be 64-127 (64 + 0-63)
                is_tailscale = 64 <= second_octet <= 127
        except (ValueError, IndexError):
            pass

    if BOOT_TEST_API_URL.startswith("http://") and not is_localhost and not is_tailscale:
        logger.warning(f"Boot test API URL uses HTTP (not HTTPS): {BOOT_TEST_API_URL}")
        logger.warning("API keys will be transmitted in plaintext - use HTTPS or Tailscale/VPN")

    payload = {"url": binary_url, "github_context": github_context}
    headers = {"Content-Type": "application/json", "X-API-Key": BOOT_TEST_API_KEY}

    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=BOOT_TEST_TIMEOUT)) as session:
            async with session.post(BOOT_TEST_API_URL, json=payload, headers=headers) as response:
                if response.status == 200:
                    logger.info(f"Successfully triggered boot test for: {binary_url}")
                    return True
                elif response.status == 401:
                    logger.error(f"Authentication failed with boot test API - check BOOT_TEST_API_KEY")
                    return False
                else:
                    response_text = await response.text()
                    logger.error(f"Boot test API returned status {response.status}: {response_text}")
                    return False

    except asyncio.TimeoutError:
        logger.error(f"Timeout calling boot test API for: {binary_url}")
        return False
    except Exception as e:
        logger.error(f"Error calling boot test API for {binary_url}: {e}")
        return False


@app.post("/cicd-webhook/binary-test")
@limiter.limit("10/minute")
async def handle_webhook(
    request: Request,
    x_github_event: str = Header(..., alias="X-GitHub-Event"),
    x_hub_signature_256: Optional[str] = Header(None, alias="X-Hub-Signature-256"),
):
    """
    Handle GitHub webhook POST requests for release binary processing.

    Rate limit: 10 requests per minute per IP address.
    Max payload size: 1 MB.
    """
    try:
        # Check request size (1 MB limit)
        content_length = request.headers.get("content-length")
        if content_length and int(content_length) > 1_000_000:
            logger.warning(f"Request payload too large: {content_length} bytes")
            raise HTTPException(status_code=413, detail="Payload too large (max 1 MB)")

        # Get raw payload for signature verification
        payload_body = await request.body()

        # Verify webhook signature (require if secret is configured)
        if not WEBHOOK_SECRET:
            logger.warning("GITHUB_WEBHOOK_SECRET not configured - webhook requests are NOT authenticated!")
        else:
            if not x_hub_signature_256:
                logger.warning("Missing X-Hub-Signature-256 header")
                raise HTTPException(status_code=401, detail="Missing signature header")

            if not verify_webhook_signature(payload_body, x_hub_signature_256, WEBHOOK_SECRET):
                logger.warning("Invalid webhook signature")
                raise HTTPException(status_code=401, detail="Invalid signature")

        # Parse JSON payload
        try:
            payload = json.loads(payload_body.decode("utf-8"))
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON payload: {e}")
            raise HTTPException(status_code=400, detail="Invalid JSON")

        # Check if this is a release event
        if x_github_event != "release":
            logger.info(f"Ignoring non-release event: {x_github_event}")
            return JSONResponse(content={"message": "Event ignored"}, status_code=200)

        # Check the action (created, published, etc.)
        action = payload.get("action", "")
        logger.info(f"Processing release event: {action}")

        # Extract GitHub context from release event
        release = payload.get("release", {})
        github_context = {
            "event_type": "release",
            "release_id": release.get("id"),
            "commit_sha": release.get("target_commitish"),
            "pr_number": None,
            "workflow_run_id": None,
        }

        name = release.get("name", "")
        logger.info(f"Processing release: {name}, ID: {github_context['release_id']}")

        # Extract qualifying binaries
        qualifying_binaries = extract_qualifying_binaries(payload)

        if qualifying_binaries:
            logger.info(f"Found {len(qualifying_binaries)} qualifying binaries")

            # Trigger boot tests for each qualifying binary with GitHub context
            boot_test_results = []
            for binary in qualifying_binaries:
                print(f"QUALIFYING BINARY: {binary['url']}")

                # Trigger boot test with GitHub context
                success = await trigger_boot_test(binary["url"], github_context)
                boot_test_results.append({"url": binary["url"], "name": binary["name"], "boot_test_triggered": success})

            # Log summary
            successful_triggers = sum(1 for result in boot_test_results if result["boot_test_triggered"])
            logger.info(f"Triggered boot tests for {successful_triggers}/{len(qualifying_binaries)} binaries")

        else:
            logger.info("No qualifying binaries found in this release")
            boot_test_results = []

        return JSONResponse(
            content={
                "message": "Webhook processed successfully",
                "action": action,
                "qualifying_binaries": len(qualifying_binaries),
                "boot_test_results": boot_test_results,
                "github_context": github_context,
            },
            status_code=200,
        )

    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.error(f"Error processing webhook: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return JSONResponse(content={"status": "healthy"})


@app.get("/")
async def root():
    """Root endpoint with service information."""
    return JSONResponse(
        content={
            "service": "GitHub Webhook Service",
            "version": "1.0.0",
            "endpoints": {"webhook": "/cicd-webhook/binary-test", "health": "/health", "docs": "/docs"},
        }
    )


if __name__ == "__main__":
    import uvicorn

    # Validate configuration on startup
    logger.info("=" * 70)
    logger.info("GitHub Webhook Service Configuration")
    logger.info("=" * 70)

    # Check webhook secret
    if not WEBHOOK_SECRET:
        logger.warning("⚠️  GITHUB_WEBHOOK_SECRET not set - webhook signature verification DISABLED")
        logger.warning("⚠️  Anyone can trigger webhooks - this is insecure!")
    else:
        logger.info("✓ GITHUB_WEBHOOK_SECRET configured")

    # Check boot test API configuration
    if not BOOT_TEST_API_URL:
        logger.warning("⚠️  BOOT_TEST_API_URL not configured - boot tests will not be triggered")
    else:
        logger.info(f"✓ Boot test API: {BOOT_TEST_API_URL}")

    if not BOOT_TEST_API_KEY:
        logger.warning("⚠️  BOOT_TEST_API_KEY not configured - boot test triggers will fail")
        logger.warning("⚠️  Generate a key with: python3 generate-api-key.py")
    else:
        logger.info("✓ BOOT_TEST_API_KEY configured")

    logger.info("=" * 70)
    logger.info(f"Starting GitHub Webhook Service on {HOST}:{PORT}")
    logger.info(f"Webhook endpoint: http://{HOST}:{PORT}/cicd-webhook/binary-test")
    logger.info(f"API docs: http://{HOST}:{PORT}/docs")
    logger.info("=" * 70)

    uvicorn.run("webhook_service:app", host=HOST, port=PORT, log_level="info", reload=False)
