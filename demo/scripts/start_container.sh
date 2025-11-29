#!/bin/bash
# Start the foobar demo container

set -e

CONTAINER_NAME="foobar-container"
IMAGE_NAME="foobar-demo:latest"

echo "Starting foobar demo container..."

# Check if container already exists
if docker ps -a --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
    echo "Container '${CONTAINER_NAME}' already exists."

    # Check if it's running
    if docker ps --format '{{.Names}}' | grep -q "^${CONTAINER_NAME}$"; then
        echo "✅ Container is already running!"
    else
        echo "Starting existing container..."
        docker start "${CONTAINER_NAME}"
        echo "✅ Container started!"
    fi
else
    echo "Creating and starting new container..."
    docker run -d \
        --name "${CONTAINER_NAME}" \
        "${IMAGE_NAME}"
    echo "✅ Container created and started!"
fi

echo ""
echo "Container details:"
echo "  Name: ${CONTAINER_NAME}"
echo "  Image: ${IMAGE_NAME}"
echo "  Repo path (in container): /workspace/foobar"
echo ""
echo "To run the evaluation:"
echo "  python scripts/run_utpr_eval.py ${CONTAINER_NAME} /workspace/foobar"
echo ""
echo "To stop the container:"
echo "  docker stop ${CONTAINER_NAME}"
echo ""
echo "To remove the container:"
echo "  docker rm ${CONTAINER_NAME}"
