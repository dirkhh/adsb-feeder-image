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

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

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
