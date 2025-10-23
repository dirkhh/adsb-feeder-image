#!/bin/bash
#
# Test script for the browser test API endpoint
#
# Usage:
#   ./test-browser-api.sh <api_host> <api_port> <rpi_ip>
#
# Example:
#   ./test-browser-api.sh 127.0.0.1 9457 192.168.77.190

API_HOST="${1:-127.0.0.1}"
API_PORT="${2:-9457}"
RPI_IP="${3:-192.168.77.190}"

echo "Testing browser test API at ${API_HOST}:${API_PORT}"
echo ""

# Test health endpoint
echo "1. Testing health endpoint..."
curl -s "http://${API_HOST}:${API_PORT}/health" | jq .
echo ""

# Test browser test endpoint
echo "2. Running browser test against ${RPI_IP}..."
curl -X POST "http://${API_HOST}:${API_PORT}/api/test-browser" \
     -H "Content-Type: application/json" \
     -d "{\"rpi_ip\": \"${RPI_IP}\", \"timeout\": 90}" \
     -w "\nHTTP Status: %{http_code}\n" | jq .

echo ""
echo "Done!"
