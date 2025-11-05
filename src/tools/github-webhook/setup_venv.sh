#!/bin/bash
# Setup script for local development with virtual environment

set -e

echo "Setting up GitHub Webhook Service development environment..."

# Check if Python 3 is available
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed."
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python3 -m venv venv
else
    echo "Virtual environment already exists."
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
if command -v uv &> /dev/null; then
    echo "Using uv (fast installer)..."
    uv pip install -r requirements.txt
else
    echo "Using pip (uv not available - consider installing it for faster deploys)..."
    pip install --upgrade pip
    pip install -r requirements.txt
fi

echo "✅ Development environment setup complete!"
echo ""
echo "To activate the virtual environment in the future, run:"
echo "  source venv/bin/activate"
echo ""
echo "To run the service locally:"
echo "  source venv/bin/activate"
echo "  export GITHUB_WEBHOOK_SECRET='your_secret_here'"
echo "  python webhook_service.py"
echo ""
echo "To test the filtering logic:"
echo "  source venv/bin/activate"
echo "  python test_filter.py"
