#!/bin/bash

# Entrypoint script for Docling CPU API
set -e

echo "🚀 Starting Docling CPU API..."

# Set default values if not provided
export OMP_NUM_THREADS=${OMP_NUM_THREADS:-4}
export UVICORN_WORKERS=${UVICORN_WORKERS:-4}
export RQ_WORKERS=${RQ_WORKERS:-2}

# Validate OpenAI API key
if [ -z "$OPENAI_API_KEY" ]; then
    echo "❌ Error: OPENAI_API_KEY environment variable is required"
    exit 1
fi

# Validate Redis REST API credentials
if [ -z "$UPSTASH_REDIS_REST_URL" ] || [ -z "$UPSTASH_REDIS_REST_TOKEN" ]; then
    echo "❌ Error: UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN environment variables are required"
    exit 1
fi

echo "📊 Configuration:"
echo "   OMP_NUM_THREADS: $OMP_NUM_THREADS"
echo "   UVICORN_WORKERS: $UVICORN_WORKERS"
echo "   OpenAI API Key: ${OPENAI_API_KEY:0:10}..."
echo "   Redis REST URL: ${UPSTASH_REDIS_REST_URL:0:30}..."
echo ""

echo "✅ Models will be downloaded automatically by Docling"
echo "🔧 Starting services..."
echo "   - API server (0.0.0.0:8000) with Upstash Redis support"
echo ""

# Start the API server and RQ worker
exec /app/run.sh
