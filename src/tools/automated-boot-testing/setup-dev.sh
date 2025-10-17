#!/bin/bash
# Development setup script for ADS-B Test Service
#
# This script helps set up a development environment by installing
# dependencies from requirements.txt into the project's virtual environment.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$(dirname "$(dirname "$SCRIPT_DIR")")")"

echo "🔧 Setting up development environment for ADS-B Test Service..."

# Check if we're in the right directory
if [[ ! -f "$PROJECT_ROOT/.venv/bin/pip" ]]; then
    echo "❌ Virtual environment not found at $PROJECT_ROOT/.venv/"
    echo "   Please run the main project setup first"
    exit 1
fi

# Install dependencies
echo "📦 Installing Python dependencies..."
cd "$PROJECT_ROOT"
.venv/bin/pip install -r "$SCRIPT_DIR/requirements.txt"

echo ""
echo "✅ Development environment setup complete!"
echo ""
echo "You can now run:"
echo "  .venv/bin/python src/tools/automated-boot-testing/adsb-test-service.py --help"
echo "  .venv/bin/python src/tools/automated-boot-testing/test-feeder-image.py --help"
echo "  .venv/bin/python src/tools/automated-boot-testing/test-api.py"
echo ""
echo "For production installation, use:"
echo "  sudo ./src/tools/automated-boot-testing/install-service.sh"
echo ""
