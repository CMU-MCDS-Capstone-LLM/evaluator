#!/bin/bash
# Build the Docker container for the foobar demo

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEMO_DIR="$(dirname "$SCRIPT_DIR")"

echo "Building foobar demo container..."
echo "Demo directory: $DEMO_DIR"

cd "$DEMO_DIR"

docker build -f scripts/Dockerfile -t foobar-demo:latest .

echo ""
echo "✅ Container built successfully!"
echo "   Image: foobar-demo:latest"
echo ""
echo "Next steps:"
echo "  1. Run: ./scripts/start_container.sh"
echo "  2. Run: python scripts/run_utpr_eval.py foobar-container /workspace/foobar"
