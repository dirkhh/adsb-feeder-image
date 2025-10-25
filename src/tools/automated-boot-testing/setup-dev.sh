#!/bin/bash
# Development environment setup for automated-boot-testing

set -e

echo "Setting up development environment..."
echo

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "Error: python3 not found. Please install Python 3.11 or later."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | awk '{print $2}')
echo "Found Python $PYTHON_VERSION"

# Create virtual environment
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "✓ Virtual environment created"
else
    echo "✓ Virtual environment already exists"
fi

# Activate and upgrade pip
echo "Upgrading pip, setuptools, and wheel..."
./venv/bin/pip install --upgrade pip setuptools wheel > /dev/null
echo "✓ Package tools upgraded"

# Install dependencies
echo "Installing dependencies from requirements.txt..."
./venv/bin/pip install -r requirements.txt > /dev/null
echo "✓ Dependencies installed"

echo
echo "================================"
echo "Setup complete!"
echo "================================"
echo
echo "To activate the virtual environment:"
echo "  source venv/bin/activate"
echo
echo "To run tests:"
echo "  ./venv/bin/python test-auth-logic.py"
echo "  ./venv/bin/python test-authentication.py"
echo
echo "To generate API keys:"
echo "  ./venv/bin/python generate-api-key.py <user-id>"
echo
echo "To run the service:"
echo "  ./venv/bin/python adsb-boot-test-service.py --config config.json"
echo
