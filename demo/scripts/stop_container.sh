#!/bin/bash
# Stop and optionally remove the foobar demo container

CONTAINER_NAME="foobar-container"

echo "Stopping foobar demo container..."

# Check if container exists
if ! docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "Container '${CONTAINER_NAME}' does not exist."
    exit 0
fi

# Stop the container if running
if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "Stopping container..."
    docker stop "${CONTAINER_NAME}"
    echo "✅ Container stopped!"
else
    echo "Container is not running."
fi

# Ask if user wants to remove
if [ "$1" == "--remove" ] || [ "$1" == "-r" ]; then
    echo "Removing container..."
    docker rm "${CONTAINER_NAME}"
    echo "✅ Container removed!"
else
    echo ""
    echo "Container stopped but not removed."
    echo "To remove the container, run:"
    echo "  ./scripts/stop_container.sh --remove"
    echo ""
    echo "To start it again, run:"
    echo "  ./scripts/start_container.sh"
fi
