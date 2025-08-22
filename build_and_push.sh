#!/bin/bash

# Build and Push Script for Docling API
# Usage: ./build_and_push.sh [version] [tag]
# Example: ./build_and_push.sh 1.0.0 latest

set -e  # Exit on any error

# Configuration
DOCKER_USERNAME="legendofmk"  # Your Docker Hub username
IMAGE_NAME="docling-cpu-api"
DEFAULT_VERSION="1.0.0"
DEFAULT_TAG="latest"

# Get version and tag from command line arguments
VERSION=${1:-$DEFAULT_VERSION}
TAG=${2:-$DEFAULT_TAG}

echo "🐳 Building and pushing Docling API Docker image"
echo "📦 Version: $VERSION"
echo "🏷️  Tag: $TAG"
echo "👤 Docker Hub: $DOCKER_USERNAME/$IMAGE_NAME"
echo ""

# Check if Docker is running
if ! docker info > /dev/null 2>&1; then
    echo "❌ Docker is not running. Please start Docker and try again."
    exit 1
fi

# Check if logged into Docker Hub
if ! docker info | grep -q "Username"; then
    echo "❌ Not logged into Docker Hub. Please run 'docker login' first."
    exit 1
fi

echo "🔨 Building Docker image..."
docker compose build --no-cache

echo "🏷️  Tagging image..."
docker tag docling-custom-docling-api:latest $DOCKER_USERNAME/$IMAGE_NAME:$TAG
docker tag docling-custom-docling-api:latest $DOCKER_USERNAME/$IMAGE_NAME:$VERSION

echo "📤 Pushing to Docker Hub..."
docker push $DOCKER_USERNAME/$IMAGE_NAME:$TAG
docker push $DOCKER_USERNAME/$IMAGE_NAME:$VERSION

echo ""
echo "✅ Successfully pushed image:"
echo "   $DOCKER_USERNAME/$IMAGE_NAME:$TAG"
echo "   $DOCKER_USERNAME/$IMAGE_NAME:$VERSION"
echo ""
echo "🚀 To pull and run:"
echo "   docker pull $DOCKER_USERNAME/$IMAGE_NAME:$TAG"
echo "   docker run -p 8001:8000 -e OPENAI_API_KEY=your_key $DOCKER_USERNAME/$IMAGE_NAME:$TAG"
echo ""
echo "📋 Image details:"
docker images $DOCKER_USERNAME/$IMAGE_NAME --format "table {{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
