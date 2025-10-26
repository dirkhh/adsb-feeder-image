#!/usr/bin/env python3
"""
GitHub Reporter Service

Polls metrics database for test results and posts them to GitHub
releases and pull requests.

Configuration via environment variables:
- GITHUB_TOKEN: Personal access token with repo permissions
- GITHUB_REPO: Repository in format "owner/repo"
- METRICS_DB_PATH: Path to metrics database
- POLL_INTERVAL_SECONDS: How often to poll (default 60)
"""

import asyncio
import logging
import os
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from github import Auth, Github, GithubException

# Import metrics module
# In production, metrics.py is copied to the same directory as this script
sys.path.insert(0, str(Path(__file__).parent))
# For development, also check the automated-boot-testing directory
sys.path.insert(0, str(Path(__file__).parent.parent / "automated-boot-testing"))

from metrics import TestMetrics  # type: ignore # noqa: E402

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Configuration from environment
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GITHUB_REPO = os.getenv("GITHUB_REPO")
METRICS_DB_PATH = os.getenv("METRICS_DB_PATH", "/var/lib/adsb-boot-test/metrics.db")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))

# FastAPI app for health endpoint
health_app = FastAPI(title="GitHub Reporter Health")

# Global reporter instance for health endpoint
reporter_instance = None


@health_app.get("/health")
async def health_check():
    """Health check endpoint for monitoring"""
    try:
        # Check GitHub API connectivity
        rate_limit_info = None
        if reporter_instance:
            try:
                rate_limit = reporter_instance.github.get_rate_limit()
                # Handle different PyGithub versions
                if hasattr(rate_limit, "core"):
                    core = getattr(rate_limit, "core")  # type: ignore[attr-defined]
                    rate_limit_info = {"remaining": core.remaining, "limit": core.limit}
                elif hasattr(rate_limit, "rate"):
                    rate = getattr(rate_limit, "rate")  # type: ignore[attr-defined]
                    rate_limit_info = {"remaining": rate.remaining, "limit": rate.limit}
            except Exception:
                pass  # Ignore rate limit errors in health check

        health_status = {
            "status": "healthy",
            "github_token_valid": reporter_instance is not None,
            "github_rate_limit": rate_limit_info,
            "last_poll": (
                reporter_instance.last_poll_time if reporter_instance and hasattr(reporter_instance, "last_poll_time") else None
            ),
            "metrics_db": METRICS_DB_PATH,
        }

        return JSONResponse(content=health_status)

    except Exception as e:
        return JSONResponse(content={"status": "unhealthy", "error": str(e)}, status_code=503)


class GitHubReporter:
    """Reports test results to GitHub releases and PRs"""

    def __init__(self, github_token: str, repo_name: str, metrics_db: str, poll_interval: int = 60):
        auth = Auth.Token(github_token)
        self.github = Github(auth=auth)
        self.repo = self.github.get_repo(repo_name)
        self.metrics = TestMetrics(metrics_db)
        self.poll_interval = poll_interval
        self.repo_name = repo_name
        self.last_poll_time: Optional[str] = None

        logger.info(f"GitHub Reporter initialized for repository: {repo_name}")

        # Validate token on startup
        self._validate_token()

    def _validate_token(self):
        """Check token validity and warn about expiration"""
        try:
            user = self.github.get_user()
            logger.info(f"✓ GitHub token valid for user: {user.login}")

            # Check rate limit
            try:
                rate_limit = self.github.get_rate_limit()
                # Try to access core rate limit (API may vary by version)
                if hasattr(rate_limit, "core"):
                    core = getattr(rate_limit, "core")  # type: ignore[attr-defined]
                    remaining = core.remaining
                    limit = core.limit
                elif hasattr(rate_limit, "rate"):
                    rate = getattr(rate_limit, "rate")  # type: ignore[attr-defined]
                    remaining = rate.remaining
                    limit = rate.limit
                else:
                    # Fallback if structure is different
                    remaining = getattr(rate_limit, "remaining", None)
                    limit = getattr(rate_limit, "limit", None)

                if remaining is not None and limit is not None:
                    logger.info(f"✓ Rate limit: {remaining}/{limit}")
                    if remaining < 100:
                        logger.warning(f"⚠️  Low rate limit: {remaining} remaining")
            except Exception as e:
                logger.warning(f"Could not check rate limit: {e}")

        except GithubException as e:
            logger.error(f"✗ GitHub token validation failed: {e}")
            logger.error("Generate new token at: https://github.com/settings/tokens")
            raise RuntimeError("Invalid GitHub token")

    async def run(self):
        """Main polling loop"""
        logger.info(f"GitHub Reporter Service started (poll interval: {self.poll_interval}s)")

        while True:
            try:
                self.last_poll_time = datetime.utcnow().isoformat()
                await self._process_unreported_tests()
            except Exception as e:
                logger.error(f"Error processing tests: {e}", exc_info=True)

            await asyncio.sleep(self.poll_interval)

    def _format_results(self, tests: List[Dict[str, Any]]) -> str:
        """
        Format test results as markdown.

        Returns markdown section with test results table.
        """
        lines = ["## Hardware Test Results\n"]

        if not tests:
            lines.append("No tests found.\n")
            return "\n".join(lines)

        for test in tests:
            # Extract image name from URL
            image_name = test["image_url"].split("/")[-1]

            # Determine icon and status text based on test status
            if test["status"] == "queued":
                icon = "⏳"
                status_text = "Queued"
            elif test["status"] == "running":
                icon = "🔄"
                status_text = "Testing..."
            elif test["status"] == "passed":
                icon = "✅"
                if test["duration_seconds"]:
                    minutes = test["duration_seconds"] // 60
                    seconds = test["duration_seconds"] % 60
                    status_text = f"Passed (boot: {minutes}m {seconds}s)"
                else:
                    status_text = "Passed"
            elif test["status"] == "failed":
                icon = "❌"
                failed_stage = test.get("error_stage", "unknown")
                status_text = f"Failed at {failed_stage} stage"
            else:  # error or unknown
                icon = "❌"
                status_text = f"Error: {test['status']}"

            lines.append(f"- {icon} `{image_name}` - {status_text}")

        # Add timestamp
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        lines.append(f"\n_Last updated: {timestamp}_")

        return "\n".join(lines)

    def _group_tests_by_target(self, tests: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
        """
        Group tests by their GitHub target (release or PR).

        Returns dict with keys like "release-123" or "pr-45" mapping to list of tests.
        """
        grouped = {}

        for test in tests:
            event_type = test.get("github_event_type")

            if event_type == "release":
                release_id = test.get("github_release_id")
                if release_id:
                    key = f"release-{release_id}"
                    if key not in grouped:
                        grouped[key] = {"type": "release", "id": release_id, "tests": []}
                    grouped[key]["tests"].append(test)

            elif event_type == "pull_request":
                pr_number = test.get("github_pr_number")
                if pr_number:
                    key = f"pr-{pr_number}"
                    if key not in grouped:
                        grouped[key] = {"type": "pull_request", "number": pr_number, "tests": []}
                    grouped[key]["tests"].append(test)

        return {k: v["tests"] for k, v in grouped.items()}

    async def _update_release(self, release_id: int, tests: List[Dict[str, Any]]):
        """
        Update or create release body with test results.

        Appends test results section to release description.
        """
        try:
            # Find release by ID
            release = None
            for rel in self.repo.get_releases():
                if rel.id == release_id:
                    release = rel
                    break

            if not release:
                logger.error(f"Release {release_id} not found")
                return False

            # Format test results
            results_markdown = self._format_results(tests)

            # Get current body
            current_body = release.body or ""

            # Check if we already have a test results section
            marker = "## Hardware Test Results"
            if marker in current_body:
                # Replace existing section
                parts = current_body.split(marker)
                # Keep everything before marker, replace from marker onwards
                new_body = parts[0].rstrip() + "\n\n" + results_markdown
            else:
                # Append new section
                new_body = current_body.rstrip() + "\n\n" + results_markdown

            # Update release
            release.update_release(name=release.title, message=new_body)

            logger.info(f"✓ Updated release {release.title} with test results ({len(tests)} tests)")
            logger.info(f"Test results: {results_markdown}")

            # Mark tests as reported ONLY if in final state
            # Tests still queued or running will be updated again on next poll
            final_states = {"passed", "failed", "error"}
            for test in tests:
                if test["status"] in final_states:
                    self.metrics.mark_reported(test["id"], "posted")
                    logger.info(f"  Marked test {test['id']} as posted (final state: {test['status']})")
                else:
                    logger.info(f"  Test {test['id']} still in progress ({test['status']}), will update again")

            return True

        except GithubException as e:
            logger.error(f"Failed to update release {release_id}: {e}")
            return False
        except Exception as e:
            logger.error(f"Error updating release {release_id}: {e}", exc_info=True)
            return False

    async def _update_pr(self, pr_number: int, tests: List[Dict[str, Any]]):
        """
        Post or update PR comment with test results.

        Uses HTML comment marker to find and update existing comment.
        """
        try:
            # Get pull request
            pr = self.repo.get_pull(pr_number)
            logger.info(f"Updating PR #{pr_number}: {pr.title}")

            # Format results
            results_section = self._format_results(tests)

            # Comment marker for finding our comment
            comment_marker = "<!-- boot-test-results -->"
            comment_body = f"{comment_marker}\n{results_section}"

            # Find existing comment
            existing_comment = None
            for comment in pr.get_issue_comments():
                if comment_marker in comment.body:
                    existing_comment = comment
                    break

            if existing_comment:
                # Update existing comment
                existing_comment.edit(comment_body)
                logger.info(f"✓ Updated PR #{pr_number} comment with {len(tests)} test results")
            else:
                # Create new comment
                pr.create_issue_comment(comment_body)
                logger.info(f"✓ Created PR #{pr_number} comment with {len(tests)} test results")

            # Mark tests as reported ONLY if in final state
            # Tests still queued or running will be updated again on next poll
            final_states = {"passed", "failed", "error"}
            for test in tests:
                if test["status"] in final_states:
                    self.metrics.mark_reported(test["id"], "posted")
                    logger.info(f"  Marked test {test['id']} as posted (final state: {test['status']})")
                else:
                    logger.info(f"  Test {test['id']} still in progress ({test['status']}), will update again")

        except GithubException as e:
            logger.error(f"✗ Failed to update PR #{pr_number}: {e}")
            # Mark tests as failed for retry
            for test in tests:
                self.metrics.mark_reported(test["id"], "failed")
            raise

        except Exception as e:
            logger.error(f"✗ Error updating PR #{pr_number}: {e}")
            for test in tests:
                self.metrics.mark_reported(test["id"], "failed")
            raise

    async def _process_unreported_tests(self):
        """
        Find unreported tests and post to GitHub.

        Groups tests by target (release or PR) and posts batch updates.
        """
        try:
            # Get tests needing reporting
            tests = self.metrics.get_unreported_tests()

            if not tests:
                logger.debug("No unreported tests found")
                return

            logger.info(f"Found {len(tests)} unreported test(s)")

            # Group by GitHub target
            grouped = self._group_tests_by_target(tests)

            logger.info(f"Grouped into {len(grouped)} target(s)")

            # Process each group
            for target_key, test_list in grouped.items():
                try:
                    # Parse target key
                    if target_key.startswith("release-"):
                        release_id = int(target_key.split("-")[1])
                        logger.info(f"Processing release {release_id} with {len(test_list)} test(s)")
                        await self._update_release(release_id, test_list)

                    elif target_key.startswith("pr-"):
                        pr_number = int(target_key.split("-")[1])
                        logger.info(f"Processing PR #{pr_number} with {len(test_list)} test(s)")
                        await self._update_pr(pr_number, test_list)

                except Exception as e:
                    logger.error(f"Failed to process {target_key}: {e}", exc_info=True)
                    # Tests already marked as failed in update methods

        except Exception as e:
            logger.error(f"Error in process_unreported_tests: {e}", exc_info=True)


def main():
    """Main entry point"""
    global reporter_instance

    # Validate configuration
    if not GITHUB_TOKEN:
        logger.error("GITHUB_TOKEN environment variable not set")
        logger.error("Generate token at: https://github.com/settings/tokens")
        sys.exit(1)

    if not GITHUB_REPO:
        logger.error("GITHUB_REPO environment variable not set (format: owner/repo)")
        sys.exit(1)

    logger.info("=" * 70)
    logger.info("GitHub Reporter Service Configuration")
    logger.info("=" * 70)
    logger.info(f"Repository: {GITHUB_REPO}")
    logger.info(f"Metrics DB: {METRICS_DB_PATH}")
    logger.info(f"Poll Interval: {POLL_INTERVAL}s")
    logger.info("=" * 70)

    # Create reporter
    reporter_instance = GitHubReporter(GITHUB_TOKEN, GITHUB_REPO, METRICS_DB_PATH, POLL_INTERVAL)

    # Start health endpoint in background thread
    health_port = int(os.getenv("HEALTH_PORT", "9457"))
    logger.info(f"Starting health endpoint on port {health_port}")

    def run_health_server():
        uvicorn.run(health_app, host="127.0.0.1", port=health_port, log_level="warning")

    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()

    # Run main reporter loop
    asyncio.run(reporter_instance.run())


if __name__ == "__main__":
    main()
