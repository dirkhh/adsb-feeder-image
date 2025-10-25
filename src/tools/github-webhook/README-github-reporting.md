# GitHub Test Results Reporting

Automatically posts hardware boot test results back to GitHub releases and pull requests.

## Overview

When a release is published on GitHub:
1. GitHub sends webhook to webhook service
2. Webhook triggers boot tests with GitHub context (release ID, commit SHA)
3. Boot test service queues tests in database
4. Tests execute on actual hardware
5. Reporter service polls database for completed tests
6. Reporter posts formatted results to GitHub release description

Results are posted progressively as each image completes testing.

## Architecture

```
GitHub Release Event
        ↓
Webhook Service (extracts GitHub context)
        ↓
Boot Test API (queues test with context)
        ↓
Test Executor (runs hardware tests)
        ↓
Metrics Database (stores results)
        ↓
Reporter Service (polls for unreported tests)
        ↓
GitHub API (posts formatted results)
```

## Components

### 1. Enhanced Metrics Database

Stores GitHub context with each test:
- Event type (release or pull_request)
- Release ID / PR number
- Commit SHA
- Reporting status

### 2. Enhanced Webhook Service

Extracts GitHub context from webhooks and passes to boot test API.

**File:** `src/tools/github-webhook/webhook_service.py`

### 3. Enhanced Boot Test Service

Accepts GitHub context and creates tests in "queued" state. Persistent queue survives service restarts.

**File:** `src/tools/automated-boot-testing/adsb-boot-test-service.py`

### 4. GitHub Reporter Service (NEW)

Polls metrics database every 60 seconds, finds unreported tests, posts formatted results to GitHub.

**File:** `src/tools/github-webhook/github_reporter.py`

## Result Format

### Release Description

```markdown
## Hardware Test Results

- ✅ `adsb-im-raspberrypi64-pi-2-3-4-v3.0.6.img.xz` - Passed (boot: 2m 15s)
- ✅ `adsb-im-dietpi-raspberrypi64-pi-5-v3.0.6.img.xz` - Passed (boot: 1m 48s)
- ❌ `adsb-im-raspberrypi64-pi-4-v3.0.6.img.xz` - Failed at boot stage
- 🔄 `adsb-im-raspberrypi64-pi-3-v3.0.6.img.xz` - Testing...
- ⏳ `adsb-im-raspberrypi64-pi-2-v3.0.6.img.xz` - Queued

_Last updated: 2025-10-25 14:32 UTC_
```

The section is appended to the release description and updated as tests progress.

### PR Comments

Same format, posted as a comment on the pull request with an HTML marker for finding and updating.

## Configuration

### Reporter Service Environment Variables

```bash
GITHUB_TOKEN=ghp_xxxxx              # Fine-grained token with repo permissions
GITHUB_REPO=owner/repo-name         # Repository in owner/repo format
METRICS_DB_PATH=/var/lib/adsb-boot-test/metrics.db
POLL_INTERVAL_SECONDS=60            # How often to check for new results
HEALTH_PORT=9457                    # Port for health endpoint
```

### GitHub Token Permissions

Required permissions for fine-grained token:
- **Pull requests:** Read and Write (to post comments)
- **Contents:** Read and Write (to update release descriptions)
- **Metadata:** Read (automatic)

**Token Setup:** https://github.com/settings/tokens?type=beta

## Deployment

See [README-reporter-setup.md](README-reporter-setup.md) for detailed setup instructions.

Quick start:
```bash
# Install dependencies
pip install -r requirements-reporter.txt

# Configure environment
export GITHUB_TOKEN=ghp_your_token
export GITHUB_REPO=owner/repo

# Run reporter
python3 github_reporter.py
```

Or use systemd service (see README-reporter-setup.md).

## Monitoring

### Health Endpoint

```bash
curl http://localhost:9457/health
```

Response:
```json
{
  "status": "healthy",
  "github_token_valid": true,
  "github_rate_limit": {
    "remaining": 4950,
    "limit": 5000
  },
  "last_poll": "2025-10-25T14:32:00Z",
  "metrics_db": "/var/lib/adsb-boot-test/metrics.db"
}
```

### Logs

```bash
# Systemd service
sudo journalctl -u github-reporter -f

# Direct run
# Logs to stdout
```

### Token Expiration

Fine-grained tokens expire (max 1 year). Monitor logs for:
- `✓ GitHub token valid` - healthy
- `⚠️  Low rate limit` - approaching limit
- `✗ GitHub token validation failed` - token expired or invalid

When token expires, generate new one and update `GITHUB_TOKEN` environment variable.

## Troubleshooting

### Results not appearing in GitHub

1. Check reporter service is running:
   ```bash
   sudo systemctl status github-reporter
   ```

2. Check for unreported tests:
   ```bash
   sqlite3 /var/lib/adsb-boot-test/metrics.db \
     "SELECT id, image_url, status, github_event_type, github_report_status FROM test_runs WHERE github_event_type IS NOT NULL"
   ```

3. Check reporter logs:
   ```bash
   sudo journalctl -u github-reporter -n 100
   ```

4. Verify GitHub token permissions:
   ```bash
   curl -H "Authorization: token $GITHUB_TOKEN" https://api.github.com/user
   ```

### Tests stuck in "queued"

1. Check boot test service is running:
   ```bash
   sudo systemctl status adsb-boot-test
   ```

2. Check queue:
   ```bash
   sqlite3 /var/lib/adsb-boot-test/metrics.db \
     "SELECT * FROM test_runs WHERE status = 'queued'"
   ```

### Webhook not triggering tests

1. Check webhook delivery in GitHub settings
2. Check webhook service logs:
   ```bash
   sudo journalctl -u github-webhook -n 100
   ```

## Testing

Run integration tests:
```bash
python3 src/tools/github-webhook/test_reporter_integration.py
```

## Future Enhancements

- Support for PR workflow_run events (test PR artifacts)
- Attach serial console logs to GitHub
- Commit status checks (green/red badges)
- Slack/email notifications on failures
- Metrics dashboard
