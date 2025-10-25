# GitHub Test Results Reporting - Design Document

**Date:** 2025-10-25
**Status:** Approved
**Author:** Design session with user

## Overview

This design adds GitHub integration to the automated boot testing system, enabling test results to be reported back to GitHub releases and pull requests. The system will post pass/fail results for each tested image, with progressive updates as tests complete.

## Problem Statement

Currently, the boot testing system:
- Receives GitHub webhook events for releases
- Downloads and tests images on actual hardware
- Tracks results in a local metrics database

However, **test results are not visible in GitHub**. Users cannot see which images passed testing without checking the local system. For pull requests, there's no feedback on whether the built images work on hardware.

## Requirements

### Functional Requirements
1. Post test results to GitHub releases (update release description)
2. Post test results to PR comments (for PR-triggered tests)
3. Show pass/fail status per image name
4. Progressive updates as each image completes testing
5. Handle both release events and PR workflow events
6. Support multiple images per release/PR

### Non-Functional Requirements
1. Reliable - no lost results even if services restart
2. Decoupled - GitHub reporting independent of test execution
3. Secure - use fine-grained GitHub tokens with expiration monitoring
4. Crash-safe - resume from where it left off after restart

## Architecture

### Component Overview

```
┌──────────────┐
│   GitHub     │
└──────┬───────┘
       │ Webhooks (release, workflow_run)
       ▼
┌──────────────────┐      ┌─────────────────┐
│ Webhook Service  │─────▶│  Metrics DB     │
│ (Enhanced)       │      │  (SQLite)       │
└──────────────────┘      └────────┬────────┘
       │                           │
       │ Trigger test              │ Poll for updates
       ▼                           ▼
┌──────────────────┐      ┌─────────────────┐
│ Boot Test Service│─────▶│ GitHub Reporter │
│ (Enhanced)       │      │ Service (NEW)   │
└──────────────────┘      └────────┬────────┘
                                   │
                                   │ Post results
                                   ▼
                          ┌─────────────────┐
                          │   GitHub API    │
                          └─────────────────┘
```

### Data Flow

1. **Release Event Flow:**
   - GitHub sends release webhook to webhook service
   - Webhook extracts release ID, commit SHA, binary URLs
   - Webhook triggers boot test with GitHub context
   - Boot test creates DB record with `status='queued'` + GitHub metadata
   - Boot test service processes queue, updates status to `running` → `passed`/`failed`
   - Reporter service polls DB, finds completed tests
   - Reporter posts results to release description

2. **Pull Request Event Flow:**
   - GitHub Actions builds images for PR, stores as workflow artifacts
   - GitHub sends workflow_run webhook when artifacts ready
   - Webhook downloads artifacts, extracts binaries
   - Webhook triggers boot tests with PR context (PR number, commit SHA)
   - Rest of flow same as release (queue → test → report)
   - Reporter posts results as PR comment

## Component Details

### 1. Metrics Database Schema Enhancement

**New columns for `test_runs` table:**

```sql
ALTER TABLE test_runs ADD COLUMN github_event_type TEXT;        -- 'release' or 'pull_request' or 'workflow_run'
ALTER TABLE test_runs ADD COLUMN github_release_id INTEGER;     -- GitHub release ID (for releases)
ALTER TABLE test_runs ADD COLUMN github_pr_number INTEGER;      -- PR number (for PRs)
ALTER TABLE test_runs ADD COLUMN github_commit_sha TEXT;        -- Commit SHA being tested
ALTER TABLE test_runs ADD COLUMN github_workflow_run_id INTEGER;-- Workflow run ID (for PR artifacts)
ALTER TABLE test_runs ADD COLUMN github_reported_at TEXT;       -- When results posted to GitHub
ALTER TABLE test_runs ADD COLUMN github_report_status TEXT;     -- 'pending', 'posted', 'failed'
```

**Enhanced status values:**
- `queued` - Test created but not started (NEW)
- `running` - Test currently executing
- `passed` - Test completed successfully
- `failed` - Test failed

**Why these changes:**
- GitHub columns: Track where to post results (release vs PR)
- `github_reported_at`: Prevent duplicate posting
- `github_report_status`: Enable retry logic for failed GitHub API calls
- `queued` status: Persistent queue survives service restarts

### 2. Webhook Service Enhancements

**File:** `src/tools/github-webhook/webhook_service.py`

**New webhook endpoint:**
- `/cicd-webhook/pr-test` - Handle workflow_run events for PRs

**Enhanced release event handler:**
```python
def handle_release_event(payload):
    release_id = payload['release']['id']
    commit_sha = payload['release']['target_commitish']
    binaries = extract_qualifying_binaries(payload)

    for binary in binaries:
        github_context = {
            'event_type': 'release',
            'release_id': release_id,
            'commit_sha': commit_sha
        }
        trigger_boot_test(binary['url'], github_context)
```

**New PR workflow handler:**
```python
def handle_workflow_run_event(payload):
    # Extract PR context from workflow_run event
    pr_number = extract_pr_number(payload)
    commit_sha = payload['workflow_run']['head_sha']
    workflow_run_id = payload['workflow_run']['id']

    # Download artifacts from GitHub Actions
    artifacts = download_workflow_artifacts(workflow_run_id)
    binaries = extract_qualifying_binaries_from_artifacts(artifacts)

    for binary in binaries:
        github_context = {
            'event_type': 'pull_request',
            'pr_number': pr_number,
            'commit_sha': commit_sha,
            'workflow_run_id': workflow_run_id
        }
        trigger_boot_test(binary['url'], github_context)
```

**API contract update:**
```json
POST /api/trigger-boot-test
{
  "url": "https://github.com/.../binary.img.xz",
  "github_context": {
    "event_type": "release",
    "release_id": 12345,
    "commit_sha": "abc123...",
    "pr_number": null,
    "workflow_run_id": null
  }
}
```

### 3. Boot Test Service Enhancements

**File:** `src/tools/automated-boot-testing/adsb-boot-test-service.py`

**Changes:**

1. **Accept GitHub context in API:**
   ```python
   @app.post("/api/trigger-boot-test")
   async def trigger_test(request: BootTestRequest):
       github_context = request.github_context or {}

       # Create queued test in DB
       test_id = metrics.start_test(
           image_url=request.url,
           triggered_by='github_webhook',
           github_event_type=github_context.get('event_type'),
           github_release_id=github_context.get('release_id'),
           github_pr_number=github_context.get('pr_number'),
           github_commit_sha=github_context.get('commit_sha'),
           github_workflow_run_id=github_context.get('workflow_run_id')
       )

       # Add to persistent queue (DB-backed, not in-memory)
       return {"test_id": test_id, "status": "queued"}
   ```

2. **Process queue from database:**
   ```python
   async def process_test_queue():
       while True:
           # Poll DB for queued tests instead of in-memory queue
           queued_tests = metrics.get_queued_tests()

           for test in queued_tests:
               # Mark as running
               metrics.update_test_status(test['id'], 'running')

               # Execute test
               try:
                   result = await run_boot_test(test)
                   metrics.complete_test(test['id'],
                       status='passed' if result.success else 'failed')
               except Exception as e:
                   metrics.complete_test(test['id'],
                       status='failed', error_message=str(e))

           await asyncio.sleep(10)
   ```

### 4. Metrics Enhancement

**File:** `src/tools/automated-boot-testing/metrics.py`

**New methods:**

```python
def start_test(self, image_url, triggered_by='manual',
               github_event_type=None, github_release_id=None,
               github_pr_number=None, github_commit_sha=None,
               github_workflow_run_id=None) -> int:
    """Create test record in 'queued' state with GitHub context"""
    conn = sqlite3.connect(self.db_path)
    cursor = conn.execute("""
        INSERT INTO test_runs
        (image_url, image_version, started_at, status, triggered_by,
         github_event_type, github_release_id, github_pr_number,
         github_commit_sha, github_workflow_run_id, github_report_status)
        VALUES (?, ?, ?, 'queued', ?, ?, ?, ?, ?, ?, 'pending')
    """, (image_url, self._extract_version(image_url),
          datetime.utcnow().isoformat(), triggered_by,
          github_event_type, github_release_id, github_pr_number,
          github_commit_sha, github_workflow_run_id))
    test_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return test_id

def get_queued_tests(self) -> List[Dict[str, Any]]:
    """Get all tests in queued state"""
    conn = sqlite3.connect(self.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("""
        SELECT * FROM test_runs
        WHERE status = 'queued'
        ORDER BY started_at ASC
    """)
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results

def get_unreported_tests(self) -> List[Dict[str, Any]]:
    """Get tests that need GitHub reporting"""
    conn = sqlite3.connect(self.db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.execute("""
        SELECT * FROM test_runs
        WHERE github_event_type IS NOT NULL
        AND (github_reported_at IS NULL
             OR github_report_status = 'failed')
        ORDER BY started_at ASC
    """)
    results = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return results

def mark_reported(self, test_id: int, status: str = 'posted'):
    """Mark test as reported to GitHub"""
    conn = sqlite3.connect(self.db_path)
    conn.execute("""
        UPDATE test_runs
        SET github_reported_at = ?, github_report_status = ?
        WHERE id = ?
    """, (datetime.utcnow().isoformat(), status, test_id))
    conn.commit()
    conn.close()
```

### 5. GitHub Reporter Service (NEW)

**File:** `src/tools/github-webhook/github_reporter.py`

**Core logic:**

```python
class GitHubReporter:
    def __init__(self, github_token: str, repo_name: str,
                 metrics_db: str, poll_interval: int = 60):
        self.github = Github(github_token)
        self.repo = self.github.get_repo(repo_name)
        self.metrics = TestMetrics(metrics_db)
        self.poll_interval = poll_interval

        # Validate token on startup
        self._validate_token()

    def _validate_token(self):
        """Check token validity and expiration"""
        try:
            user = self.github.get_user()
            rate_limit = self.github.get_rate_limit()

            # Check if token is expiring soon (fine-grained tokens)
            # Note: Expiration checking depends on GitHub API response
            logger.info(f"GitHub token valid for user: {user.login}")
            logger.info(f"Rate limit: {rate_limit.core.remaining}/{rate_limit.core.limit}")

        except Exception as e:
            logger.error(f"GitHub token validation failed: {e}")
            raise RuntimeError("Invalid GitHub token - generate new token at https://github.com/settings/tokens")

    async def run(self):
        """Main polling loop"""
        logger.info("GitHub Reporter Service started")

        while True:
            try:
                await self._process_unreported_tests()
            except Exception as e:
                logger.error(f"Error processing tests: {e}")

            await asyncio.sleep(self.poll_interval)

    async def _process_unreported_tests(self):
        """Find and report tests to GitHub"""
        tests = self.metrics.get_unreported_tests()

        # Group tests by release/PR for batched updates
        grouped = self._group_tests_by_target(tests)

        for target, test_list in grouped.items():
            try:
                if target['type'] == 'release':
                    await self._update_release(target['id'], test_list)
                elif target['type'] == 'pull_request':
                    await self._update_pr(target['number'], test_list)

                # Mark all tests as reported
                for test in test_list:
                    self.metrics.mark_reported(test['id'], 'posted')

            except Exception as e:
                logger.error(f"Failed to report to {target}: {e}")
                for test in test_list:
                    self.metrics.mark_reported(test['id'], 'failed')

    def _group_tests_by_target(self, tests):
        """Group tests by release or PR"""
        grouped = {}
        for test in tests:
            if test['github_event_type'] == 'release':
                key = f"release-{test['github_release_id']}"
                grouped.setdefault(key, {
                    'type': 'release',
                    'id': test['github_release_id'],
                    'tests': []
                })['tests'].append(test)
            elif test['github_event_type'] == 'pull_request':
                key = f"pr-{test['github_pr_number']}"
                grouped.setdefault(key, {
                    'type': 'pull_request',
                    'number': test['github_pr_number'],
                    'tests': []
                })['tests'].append(test)

        return {k: v['tests'] for k, v in grouped.items()}

    async def _update_release(self, release_id: int, tests: List[Dict]):
        """Update release description with test results"""
        release = self.repo.get_release(release_id)

        # Format results
        results_section = self._format_results(tests)

        # Append or update results section in release description
        current_body = release.body or ""

        # Remove old test results section if exists
        marker_start = "## Hardware Test Results"
        if marker_start in current_body:
            # Replace existing section
            parts = current_body.split(marker_start)
            # Keep everything before marker, discard old results
            current_body = parts[0].rstrip()

        # Append new results
        new_body = f"{current_body}\n\n{results_section}".strip()
        release.update_release(name=release.title, message=new_body)

        logger.info(f"Updated release {release_id} with {len(tests)} test results")

    async def _update_pr(self, pr_number: int, tests: List[Dict]):
        """Post or update PR comment with test results"""
        pr = self.repo.get_pull(pr_number)

        # Format results
        results_section = self._format_results(tests)

        # Find existing comment or create new one
        comment_marker = "<!-- boot-test-results -->"
        comment_body = f"{comment_marker}\n{results_section}"

        existing_comment = None
        for comment in pr.get_issue_comments():
            if comment_marker in comment.body:
                existing_comment = comment
                break

        if existing_comment:
            existing_comment.edit(comment_body)
            logger.info(f"Updated PR #{pr_number} comment with {len(tests)} test results")
        else:
            pr.create_issue_comment(comment_body)
            logger.info(f"Created PR #{pr_number} comment with {len(tests)} test results")

    def _format_results(self, tests: List[Dict]) -> str:
        """Format test results as markdown"""
        lines = ["## Hardware Test Results\n"]

        for test in tests:
            image_name = test['image_url'].split('/')[-1]

            if test['status'] == 'queued':
                icon = "⏳"
                status_text = "Queued"
            elif test['status'] == 'running':
                icon = "🔄"
                status_text = "Testing..."
            elif test['status'] == 'passed':
                icon = "✅"
                duration = f"{test['duration_seconds'] // 60}m {test['duration_seconds'] % 60}s"
                status_text = f"Passed (boot: {duration})"
            else:  # failed
                icon = "❌"
                failed_stage = test.get('error_stage', 'unknown')
                status_text = f"Failed at {failed_stage} stage"

            lines.append(f"- {icon} `{image_name}` - {status_text}")

        # Add timestamp
        timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M UTC")
        lines.append(f"\n_Last updated: {timestamp}_")

        return "\n".join(lines)
```

**Systemd service file:** `github-reporter.service`

```ini
[Unit]
Description=GitHub Test Results Reporter
After=network.target

[Service]
Type=simple
User=adsb-boot-test
WorkingDirectory=/opt/adsb-boot-test/github-webhook
Environment="GITHUB_TOKEN=ghp_xxxxx"
Environment="GITHUB_REPO=owner/repo-name"
Environment="METRICS_DB_PATH=/var/lib/adsb-boot-test/metrics.db"
Environment="POLL_INTERVAL_SECONDS=60"
ExecStart=/opt/adsb-boot-test/venv/bin/python3 github_reporter.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

## GitHub Token Setup

### Fine-Grained Personal Access Token

1. **Create token:** https://github.com/settings/tokens?type=beta
2. **Repository access:** Select the specific repository
3. **Permissions:**
   - Pull requests: Read and Write
   - Contents: Read and Write
   - Metadata: Read (auto-selected)
4. **Expiration:** Set to maximum allowed (currently 1 year)
5. **Token storage:** Add to environment variables or systemd service config

### Token Expiration Monitoring

The reporter service will:
- Validate token on startup
- Log warnings when token expires in < 7 days
- Expose token status via `/health` endpoint
- Log clear error message when token expires with renewal URL

### Health Endpoint

```
GET /health
{
  "status": "healthy",
  "github_token": {
    "valid": true,
    "expires_in_days": 45,
    "last_api_call": "2025-10-25T14:32:00Z"
  },
  "last_poll": "2025-10-25T14:35:00Z",
  "tests_reported_today": 12
}
```

## Result Formatting

### Release Description Format

```markdown
## Hardware Test Results

- ✅ `adsb-im-raspberrypi64-pi-2-3-4-v3.0.6-beta.6.img.xz` - Passed (boot: 2m 15s)
- ✅ `adsb-im-dietpi-raspberrypi64-pi-5-v3.0.6-beta.6.img.xz` - Passed (boot: 1m 48s)
- ❌ `adsb-im-raspberrypi64-pi-4-v3.0.6-beta.6.img.xz` - Failed at boot stage
- 🔄 `adsb-im-raspberrypi64-pi-3-v3.0.6-beta.6.img.xz` - Testing...
- ⏳ `adsb-im-raspberrypi64-pi-2-v3.0.6-beta.6.img.xz` - Queued

_Last updated: 2025-10-25 14:32 UTC_
```

### PR Comment Format

Same format as release, with HTML comment marker for finding/updating:
```html
<!-- boot-test-results -->
## Hardware Test Results
...
```

## Deployment Plan

### Phase 1: Database Migration
1. Add new columns to `test_runs` table
2. Deploy schema migration script
3. Verify backward compatibility with existing records

### Phase 2: Boot Test Service Update
1. Update to accept GitHub context in API
2. Implement persistent queue (DB-backed)
3. Test queue persistence across restarts

### Phase 3: Webhook Service Update
1. Add PR workflow event handler
2. Update release handler to pass GitHub context
3. Test both event types

### Phase 4: Reporter Service Deployment
1. Create GitHub token with appropriate permissions
2. Deploy reporter service
3. Configure systemd service
4. Monitor logs for token validation and first reports

### Phase 5: Verification
1. Trigger test release, verify results appear
2. Trigger test PR, verify comment appears
3. Test service restarts (queue persistence, reporter resilience)
4. Verify progressive updates work correctly

## Error Handling

### Boot Test Service
- Queue persistence survives crashes
- Failed tests marked in DB, not lost
- Service restart picks up queued tests

### Reporter Service
- Failed GitHub API calls → `github_report_status='failed'` for retry
- Invalid token → fail fast on startup with clear error
- Rate limiting → exponential backoff
- Network errors → log and retry next poll cycle

### Webhook Service
- Failed boot test trigger → log error, continue processing other binaries
- GitHub webhook validation failures → reject with 401

## Security Considerations

1. **GitHub Token:**
   - Use fine-grained token (repo-scoped only)
   - Store in environment variables, not code
   - Monitor expiration and alert
   - Rotate periodically

2. **Webhook Validation:**
   - Continue using HMAC signature verification
   - Validate event types before processing

3. **Database Access:**
   - Reporter service read/write to metrics DB
   - Proper file permissions on SQLite file

## Future Enhancements

1. **Detailed logs:** Link to serial console logs from GitHub comments
2. **Artifacts:** Upload test logs as GitHub release assets
3. **Commit status checks:** Set commit status (green/red) in addition to comments
4. **Notifications:** Slack/email on test failures
5. **Metrics dashboard:** Web UI showing test history and trends
6. **Parallel testing:** Queue multiple tests, run in parallel on different hardware

## Open Questions (for Implementation)

1. Exact webhook payload structure for workflow_run events (verify during implementation)
2. GitHub API pagination if release has many test results
3. Rate limiting thresholds and backoff strategy
4. Log retention policy for test results in DB
5. Maximum PR comment length (GitHub limit ~65536 chars)

## Success Criteria

1. ✅ Test results visible in GitHub releases
2. ✅ Test results posted as PR comments
3. ✅ Progressive updates work (queued → testing → passed/failed)
4. ✅ System survives service restarts without losing tests
5. ✅ Token expiration warnings appear in logs
6. ✅ Both release and PR workflows supported
