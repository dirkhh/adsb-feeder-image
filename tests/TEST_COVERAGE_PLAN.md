# Test Coverage Implementation Plan

## Overview

This document outlines the test coverage analysis and implementation plan for the adsb-feeder-image project.

## Current Test Coverage Status

### Existing Tests (Main Application)
- **Unit Tests**: 12 test files covering utilities, Flask app, configuration
- **Integration Tests**: 1 comprehensive system integration test
- **Coverage**: Estimated ~40-50% line coverage
- **Quality**: Good mocking strategy, but some gaps in security and edge cases

### New Tests Created (Tools)
- ✅ `src/tools/github-webhook/test_webhook_security.py` - **CREATED & VERIFIED**
  - 20 passing tests, 2 skipped (documented security improvements)
- ✅ `src/tools/automated-boot-testing/test_boot_service_security.py` - **CREATED & VERIFIED**
  - 16 passing tests, 1 skipped (documented security improvement)

## Test Coverage Analysis Summary

### Critical Security Gaps (Priority 1)

#### 1. System Operations (MISSING)
**File**: `tests/unit/test_system.py` (needs creation)

**Missing Coverage**:
- Command injection prevention in shutdown/reboot actions
- Docker container operations security
- Lock mechanism thread safety
- DNS/network check error handling
- Resource cleanup on exceptions

**Impact**: High - Command injection could allow arbitrary code execution

#### 2. Background Task Management (MISSING)
**File**: `tests/unit/test_background.py` (needs creation)

**Missing Coverage**:
- Task exception handling
- Resource cleanup on task failure
- Task cancellation safety
- Concurrent task execution

**Impact**: Medium - Could cause resource leaks or service instability

#### 3. Aggregator Status Tracking (MISSING)
**File**: `tests/unit/test_agg_status.py` (needs creation)

**Missing Coverage**:
- Health check timeout handling
- Error state transitions
- Status inconsistency scenarios
- Network failure recovery

**Impact**: Medium - Failed aggregator detection could hide issues

### Feature Coverage Gaps (Priority 2)

#### 1. Other Aggregators (PARTIAL)
**File**: `tests/unit/test_aggregators.py` (extend existing)

**Missing Coverage**:
- Network timeout scenarios
- Malformed API responses
- Rate limiting
- Error recovery mechanisms

**Tests to Add**:
```python
test_aggregator_network_timeout_recovery()
test_aggregator_malformed_api_response()
test_aggregator_rate_limit_handling()
test_aggregator_connection_retry_logic()
```

#### 2. Flask Application (PARTIAL)
**File**: `tests/unit/test_app.py` (extend existing)

**Missing Coverage**:
- POST data injection prevention
- File upload validation
- Session security
- Error page information disclosure
- CSRF protection

**Tests to Add**:
```python
test_app_post_sql_injection_prevention()
test_app_file_upload_path_traversal()
test_app_session_fixation_prevention()
test_app_error_page_no_stack_traces()
```

#### 3. Multi-outline Functionality (UNKNOWN)
**File**: `tests/unit/test_multioutline.py` (needs creation)

**Status**: Requires code review to determine critical paths

### Integration Coverage Gaps (Priority 2)

#### 1. End-to-End Workflows (MISSING)
**File**: `tests/integration/test_e2e_workflows.py` (needs creation)

**Missing Scenarios**:
- Complete setup workflow (initial config → SDR detection → aggregator setup)
- Multi-SDR configuration
- Aggregator fail-over
- Configuration backup/restore

#### 2. Security Integration (MISSING)
**File**: `tests/integration/test_security_integration.py` (needs creation)

**Missing Scenarios**:
- Config injection across components
- File upload security (backup restore)
- Concurrent configuration changes
- Authentication flow security

## Detailed Test Specifications

### Created Tests

#### test_webhook_security.py

**Coverage**:
- ✅ HMAC signature verification (timing-safe)
- ✅ URL validation and injection prevention
- ✅ Binary filtering logic
- ✅ Malicious payload handling

**Test Classes**:
1. `TestWebhookSignatureVerification` (8 tests)
2. `TestURLValidation` (5 tests + 2 skipped security improvements)
3. `TestBinaryFiltering` (3 tests)
4. `TestExtractQualifyingBinaries` (4 tests)

**Total**: 20 passing tests, 2 skipped (documenting security improvements)

#### test_boot_service_security.py

**Coverage**:
- ✅ API key authentication (timing-safe)
- ✅ GitHub URL validation
- ✅ Input validation and injection prevention
- ✅ Queue management security
- ✅ Thread safety

**Test Classes**:
1. `TestAPIKeyAuthentication` (5 tests)
2. `TestGitHubURLValidation` (3 tests + 1 skipped security improvement)
3. `TestInputValidation` (3 tests)
4. `TestQueueSecurity` (5 tests)

**Total**: 16 passing tests, 1 skipped (documenting security improvement)

### Recommended Test Additions

#### Priority 1: Security-Critical (Week 1)

```python
# tests/unit/test_system.py (NEW)
class TestSystemSecurity:
    test_shutdown_action_validation()
    test_docker_command_injection_prevention()
    test_lock_thread_safety()
    test_restart_lock_cleanup_on_exception()

class TestSystemDocker:
    test_list_containers_malformed_output()
    test_refresh_docker_ps_timeout()

class TestSystemNetwork:
    test_check_dns_exception_handling()
    test_check_gpsd_socket_error_handling()
```

```python
# tests/unit/test_background.py (NEW)
class TestBackgroundTasks:
    test_task_exception_handling()
    test_task_cleanup_on_failure()
    test_task_cancellation()
    test_concurrent_task_execution()
```

```python
# tests/unit/test_agg_status.py (NEW)
class TestAggregatorStatus:
    test_healthcheck_timeout()
    test_error_state_transitions()
    test_status_consistency()
    test_network_failure_recovery()
```

#### Priority 2: Features & Reliability (Week 2)

```python
# tests/unit/test_aggregators.py (EXTEND)
class TestAggregatorErrorHandling:
    test_aggregator_network_timeout_recovery()
    test_aggregator_malformed_api_response()
    test_aggregator_rate_limit_handling()
    test_aggregator_connection_retry_logic()
    test_aggregator_partial_data_handling()
```

```python
# tests/unit/test_app.py (EXTEND)
class TestAppSecurity:
    test_app_post_sql_injection_prevention()
    test_app_post_command_injection_prevention()
    test_app_file_upload_path_traversal()
    test_app_file_upload_size_limit()
    test_app_session_security()
    test_app_csrf_protection()
    test_app_error_page_information_disclosure()
```

#### Priority 3: Integration (Week 3)

```python
# tests/integration/test_e2e_workflows.py (NEW)
class TestEndToEndWorkflows:
    test_initial_setup_workflow()
    test_sdr_detection_and_configuration()
    test_aggregator_configuration_workflow()
    test_multi_sdr_setup()
    test_configuration_backup_restore()
    test_aggregator_failover()
```

```python
# tests/integration/test_security_integration.py (NEW)
class TestSecurityIntegration:
    test_config_injection_prevention()
    test_file_upload_security()
    test_concurrent_configuration_safety()
    test_session_management_security()
    test_authentication_flow()
```

## Running the New Tests

### Running Webhook Security Tests

```bash
# From project root
cd src/tools/github-webhook

# Install test dependencies
pip install pytest pytest-asyncio

# Run all security tests
python test_webhook_security.py

# Or with pytest
pytest test_webhook_security.py -v

# Run specific test class
pytest test_webhook_security.py::TestWebhookSignatureVerification -v
```

### Running Boot Service Security Tests

```bash
# From project root
cd src/tools/automated-boot-testing

# Install test dependencies
pip install pytest

# Run all security tests
python test_boot_service_security.py

# Or with pytest
pytest test_boot_service_security.py -v

# Run specific test class
pytest test_boot_service_security.py::TestAPIKeyAuthentication -v
```

### Running All Tests

```bash
# From project root
python tests/run_tests.py --all

# Or with pytest
pytest tests/ src/tools/ -v --cov
```

## Test Quality Improvements

### Current Issues

1. **Excessive Mocking**: Some tests mock too much, testing mocks rather than behavior
2. **Limited Edge Cases**: Need more boundary condition tests
3. **Few Negative Tests**: Need more failure scenario tests
4. **Missing Concurrent Tests**: Need thread safety tests

### Improvements Needed

#### Reduce Over-Mocking

**Before** (testing the mock):
```python
@patch('utils.config.read_file')
def test_config_read(mock_read):
    mock_read.return_value = "test"
    result = config.load()
    assert result == "test"  # Just testing the mock!
```

**After** (testing behavior):
```python
def test_config_read(tmp_path):
    config_file = tmp_path / "config.json"
    config_file.write_text('{"key": "value"}')

    result = config.load(str(config_file))
    assert result["key"] == "value"  # Testing actual behavior
```

#### Add Boundary Tests

```python
class TestInputValidation:
    def test_valid_latitude():
        assert validate_latitude(45.0) == True

    def test_latitude_boundaries():
        # Boundary conditions
        assert validate_latitude(-90.0) == True   # Min
        assert validate_latitude(90.0) == True    # Max
        assert validate_latitude(-90.1) == False  # Just below
        assert validate_latitude(90.1) == False   # Just above
```

#### Add Negative Tests

```python
class TestNetworkOperations:
    def test_connection_success(self):
        # Happy path
        pass

    def test_connection_timeout(self):
        # Timeout scenario
        pass

    def test_connection_refused(self):
        # Connection refused
        pass

    def test_connection_dns_failure(self):
        # DNS resolution failure
        pass

    def test_connection_ssl_error(self):
        # SSL/TLS error
        pass
```

## Coverage Targets

### Current Coverage
- **Estimated**: ~40-50% line coverage
- **Tools**: ~60% (with new security tests)

### Target Coverage
- **Overall**: 75% line coverage
- **Security-Critical Paths**: 100% coverage
- **Public APIs**: 100% coverage
- **Error Handlers**: 90% coverage
- **Integration Points**: 80% coverage

## Implementation Timeline

### Week 1: Security-Critical Tests
- [ ] Create `test_system.py` with security tests
- [ ] Create `test_background.py` with task management tests
- [ ] Create `test_agg_status.py` with status tracking tests
- [ ] Run and verify webhook security tests
- [ ] Run and verify boot service security tests

### Week 2: Feature Coverage
- [ ] Extend `test_aggregators.py` with error handling tests
- [ ] Extend `test_app.py` with security tests
- [ ] Create `test_multioutline.py` (if needed)
- [ ] Run coverage report and identify remaining gaps

### Week 3: Integration Tests
- [ ] Create `test_e2e_workflows.py`
- [ ] Create `test_security_integration.py`
- [ ] Run full integration test suite
- [ ] Fix any failures

### Week 4: Quality & Documentation
- [ ] Reduce over-mocking in existing tests
- [ ] Add property-based tests where appropriate
- [ ] Document test patterns and conventions
- [ ] Update test README with new tests
- [ ] Run full test suite and verify targets met

## Success Metrics

- [x] Webhook security tests created (20 passing, 2 documented improvements)
- [x] Boot service security tests created (16 passing, 1 documented improvement)
- [x] All created tests verified and running successfully
- [ ] System security tests created
- [ ] Background task tests created
- [ ] Aggregator error handling tests extended
- [ ] App security tests extended
- [ ] Integration tests created
- [ ] Coverage target of 75% achieved
- [ ] 100% coverage of security-critical paths
- [ ] All tests passing in CI/CD

## Notes

- **Test Isolation**: Each test must be independent
- **Fast Tests**: Unit tests should run in <1s each
- **Clear Failures**: Test names should describe what failed
- **Mock Judiciously**: Only mock external dependencies
- **Test Behavior**: Test outcomes, not implementation
- **Security First**: Security tests are highest priority

## References

- Test suite README: `tests/README.md`
- Test coverage agent analysis: See above
- Security best practices: OWASP Testing Guide
- Python testing: pytest documentation
