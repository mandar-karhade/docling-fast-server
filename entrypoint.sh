#!/bin/bash

# Entrypoint script for Docling CPU API with managed Redis and RQ workers
set -e

echo "🚀 Starting Docling CPU API with managed Redis and RQ workers..."

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

# Test Redis connection
echo "🔍 Testing Redis connection..."
if python3 -c "
from upstash_redis import Redis
import os
try:
    r = Redis(url=os.environ['UPSTASH_REDIS_REST_URL'], token=os.environ['UPSTASH_REDIS_REST_TOKEN'])
    r.ping()
    print('✅ Redis connection successful')
except Exception as e:
    print(f'❌ Redis connection failed: {e}')
    exit(1)
"; then
    echo "✅ Redis connection verified"
else
    echo "❌ Redis connection failed"
    echo "   Some features may not be available"
fi

echo "🚀 Starting API server..."
echo "   Host: 0.0.0.0"
echo "   Port: 8000"
echo "   Workers: $UVICORN_WORKERS"
echo ""

# Start the API server
exec uvicorn main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers $UVICORN_WORKERS \
    --log-level info
