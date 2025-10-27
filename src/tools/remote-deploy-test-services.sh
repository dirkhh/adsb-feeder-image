#!/bin/bash
#
# Remote Deployment Script for Test Services
#
# Deploys github-webhook, adsb-boot-test, and github-reporter to remote servers.
# Reads target hosts from .env file in the same directory.
#
# Usage:
#   ./remote-deploy-test-services.sh [webhook|boot-test|reporter|all]
#
# .env format:
#   WEBHOOK_HOST=[user@]hostname
#   BOOT_TEST_HOST=[user@]hostname
#
# Note: github-reporter always deploys to BOOT_TEST_HOST (same server as boot-test)
#
# Examples:
#   WEBHOOK_HOST=root@webhook.example.com
#   BOOT_TEST_HOST=admin@192.168.1.100
#   WEBHOOK_HOST=webhook.example.com  # defaults to root@

set -e  # Exit on error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENV_FILE="${SCRIPT_DIR}/.env"

# Service directories
WEBHOOK_DIR="${SCRIPT_DIR}/github-webhook"
BOOT_TEST_DIR="${SCRIPT_DIR}/automated-boot-testing"
REPORTER_DIR="${SCRIPT_DIR}/github-reporter"

# Remote staging directory
REMOTE_STAGE_DIR="/tmp/adsb-deploy-$(date +%s)"

# Function to print colored output
log_info() {
    echo -e "${BLUE}ℹ${NC} $1"
}

log_success() {
    echo -e "${GREEN}✓${NC} $1"
}

log_error() {
    echo -e "${RED}✗${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# Function to load .env file
load_env() {
    if [[ ! -f "$ENV_FILE" ]]; then
        log_error ".env file not found at: $ENV_FILE"
        log_info "Create a .env file with:"
        echo "  WEBHOOK_HOST=[user@]hostname"
        echo "  BOOT_TEST_HOST=[user@]hostname"
        exit 1
    fi

    # Source the .env file
    set -a
    source "$ENV_FILE"
    set +a

    log_success "Loaded configuration from .env"
}

# Function to check ssh-agent status
check_ssh_agent() {
    # Check if ssh-agent is running
    if [[ -z "$SSH_AUTH_SOCK" ]]; then
        log_error "ssh-agent is not running"
        echo
        log_info "Start ssh-agent and add your keys:"
        echo "  eval \"\$(ssh-agent -s)\""
        echo "  ssh-add ~/.ssh/id_ed25519  # or your key path"
        echo
        log_info "Or start it for this session:"
        echo "  eval \"\$(ssh-agent -s)\" && ssh-add && ./remote-deploy-test-services.sh"
        exit 1
    fi

    # Check if any keys are loaded
    if ! ssh-add -l &>/dev/null; then
        local exit_code=$?
        if [[ $exit_code -eq 1 ]]; then
            log_error "No SSH keys are loaded in ssh-agent"
            echo
            log_info "Add your SSH key(s):"
            echo "  ssh-add ~/.ssh/id_ed25519  # or your key path"
            echo "  ssh-add ~/.ssh/id_rsa"
            echo
            log_info "Then run deployment again"
            exit 1
        elif [[ $exit_code -eq 2 ]]; then
            log_error "Cannot connect to ssh-agent"
            exit 1
        fi
    fi

    # Show loaded keys
    log_success "ssh-agent is running with loaded keys:"
    ssh-add -l | sed 's/^/  /'
    echo
}

# Function to parse host (add default user if not specified)
parse_host() {
    local host="$1"
    if [[ "$host" == *"@"* ]]; then
        echo "$host"
    else
        echo "root@$host"
    fi
}

# Function to test SSH connection
test_ssh() {
    local host="$1"
    if ssh -o ConnectTimeout=5 -o BatchMode=yes "$host" "echo 'SSH connection successful'" &>/dev/null; then
        return 0
    else
        return 1
    fi
}

# Function to deploy github-webhook service
deploy_webhook() {
    local host=$(parse_host "$WEBHOOK_HOST")

    log_info "Deploying github-webhook service to $host"

    # Test SSH connection
    if ! test_ssh "$host"; then
        log_error "Cannot connect to $host via SSH"
        log_warning "Ensure SSH key authentication is configured"
        return 1
    fi

    log_success "SSH connection to $host verified"

    # Create staging directory on remote
    log_info "Creating staging directory on remote..."
    ssh "$host" "mkdir -p $REMOTE_STAGE_DIR/github-webhook"

    # Copy files to remote staging directory
    log_info "Copying files to remote..."
    scp -r "$WEBHOOK_DIR"/* "$host:$REMOTE_STAGE_DIR/github-webhook/" > /dev/null

    log_success "Files copied to remote staging directory"

    # Run deployment script on remote
    log_info "Running deployment script on remote..."
    ssh "$host" "cd $REMOTE_STAGE_DIR/github-webhook && bash deploy.sh"

    # Restart service
    log_info "Restarting github-webhook service..."
    ssh "$host" "systemctl restart github-webhook"

    # Check service status
    if ssh "$host" "systemctl is-active --quiet github-webhook"; then
        log_success "github-webhook service is running"
    else
        log_error "github-webhook service failed to start"
        ssh "$host" "journalctl -u github-webhook -n 20 --no-pager"
        return 1
    fi

    # Cleanup staging directory
    log_info "Cleaning up remote staging directory..."
    ssh "$host" "rm -rf $REMOTE_STAGE_DIR"

    log_success "github-webhook deployment completed successfully"
}

# Function to deploy adsb-boot-test
deploy_boot_test() {
    local host=$(parse_host "$BOOT_TEST_HOST")

    log_info "Deploying adsb-boot-test to $host"

    # Test SSH connection
    if ! test_ssh "$host"; then
        log_error "Cannot connect to $host via SSH"
        log_warning "Ensure SSH key authentication is configured"
        return 1
    fi

    log_success "SSH connection to $host verified"

    # Create staging directory on remote
    log_info "Creating staging directory on remote..."
    ssh "$host" "mkdir -p $REMOTE_STAGE_DIR/automated-boot-testing"

    # Copy files to remote staging directory
    log_info "Copying files to remote..."
    scp -r "$BOOT_TEST_DIR"/* "$host:$REMOTE_STAGE_DIR/automated-boot-testing/" > /dev/null

    log_success "Files copied to remote staging directory"

    # Run deployment script on remote
    log_info "Running deployment script on remote..."
    ssh "$host" "cd $REMOTE_STAGE_DIR/automated-boot-testing && bash install-service.sh"

    # Restart service
    log_info "Restarting adsb-boot-test..."
    ssh "$host" "systemctl restart adsb-boot-test"

    # Check service status
    if ssh "$host" "systemctl is-active --quiet adsb-boot-test"; then
        log_success "adsb-boot-test is running"
    else
        log_error "adsb-boot-test failed to start"
        ssh "$host" "journalctl -u adsb-boot-test -n 20 --no-pager"
        return 1
    fi

    # Cleanup staging directory
    log_info "Cleaning up remote staging directory..."
    ssh "$host" "rm -rf $REMOTE_STAGE_DIR"

    log_success "adsb-boot-test deployment completed successfully"
}

# Function to deploy github-reporter
deploy_reporter() {
    # Reporter always runs on same host as boot-test service
    local host=$(parse_host "$BOOT_TEST_HOST")

    log_info "Deploying github-reporter to $host (same as boot-test)"

    # Test SSH connection
    if ! test_ssh "$host"; then
        log_error "Cannot connect to $host via SSH"
        log_warning "Ensure SSH key authentication is configured"
        return 1
    fi

    log_success "SSH connection to $host verified"

    # Create staging directory on remote
    log_info "Creating staging directory on remote..."
    ssh "$host" "mkdir -p $REMOTE_STAGE_DIR/github-reporter"

    # Copy files to remote staging directory
    log_info "Copying files to remote..."
    scp -r "$REPORTER_DIR"/* "$host:$REMOTE_STAGE_DIR/github-reporter/" > /dev/null

    log_success "Files copied to remote staging directory"

    # Run deployment script on remote
    log_info "Running deployment script on remote..."
    ssh "$host" "cd $REMOTE_STAGE_DIR/github-reporter && bash deploy-reporter.sh"

    # Restart service
    log_info "Restarting github-reporter..."
    ssh "$host" "systemctl restart github-reporter"

    # Check service status
    if ssh "$host" "systemctl is-active --quiet github-reporter"; then
        log_success "github-reporter is running"
    else
        log_error "github-reporter failed to start"
        ssh "$host" "journalctl -u github-reporter -n 20 --no-pager"
        return 1
    fi

    # Cleanup staging directory
    log_info "Cleaning up remote staging directory..."
    ssh "$host" "rm -rf $REMOTE_STAGE_DIR"

    log_success "github-reporter deployment completed successfully"
}

# Main function
main() {
    local target="${1:-all}"

    echo "=========================================="
    echo "  Remote Deployment for Test Services"
    echo "=========================================="
    echo

    # Load environment
    load_env

    # Check ssh-agent is running with keys loaded
    check_ssh_agent

    # Deploy based on target
    case "$target" in
        webhook)
            if [[ -z "$WEBHOOK_HOST" ]]; then
                log_error "WEBHOOK_HOST not set in .env file"
                exit 1
            fi
            deploy_webhook
            ;;
        boot-test)
            if [[ -z "$BOOT_TEST_HOST" ]]; then
                log_error "BOOT_TEST_HOST not set in .env file"
                exit 1
            fi
            deploy_boot_test
            ;;
        reporter)
            if [[ -z "$BOOT_TEST_HOST" ]]; then
                log_error "BOOT_TEST_HOST not set in .env file (reporter uses same host as boot-test)"
                exit 1
            fi
            deploy_reporter
            ;;
        all)
            local failed=0

            if [[ -n "$WEBHOOK_HOST" ]]; then
                if ! deploy_webhook; then
                    failed=1
                fi
                echo
            else
                log_warning "WEBHOOK_HOST not set in .env - skipping github-webhook deployment"
                echo
            fi

            if [[ -n "$BOOT_TEST_HOST" ]]; then
                if ! deploy_boot_test; then
                    failed=1
                fi
                echo

                # Deploy reporter to same host as boot-test
                if ! deploy_reporter; then
                    failed=1
                fi
            else
                log_warning "BOOT_TEST_HOST not set in .env - skipping adsb-boot-test and github-reporter deployment"
            fi

            if [[ $failed -eq 1 ]]; then
                echo
                log_error "Some deployments failed"
                exit 1
            fi
            ;;
        *)
            log_error "Invalid target: $target"
            echo
            echo "Usage: $0 [webhook|boot-test|reporter|all]"
            echo
            echo "  webhook    - Deploy github-webhook service only"
            echo "  boot-test  - Deploy adsb-boot-test only"
            echo "  reporter   - Deploy github-reporter only (runs on same host as boot-test)"
            echo "  all        - Deploy all services (default)"
            exit 1
            ;;
    esac

    echo
    echo "=========================================="
    log_success "Deployment completed successfully"
    echo "=========================================="
}

# Run main function
main "$@"
