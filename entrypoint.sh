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

# Validate Redis URL
if [ -z "$UPSTASH_REDIS_URL" ]; then
    echo "❌ Error: UPSTASH_REDIS_URL environment variable is required"
    exit 1
fi

echo "📊 Configuration:"
echo "   OMP_NUM_THREADS: $OMP_NUM_THREADS"
echo "   UVICORN_WORKERS: $UVICORN_WORKERS"
echo "   RQ_WORKERS: $RQ_WORKERS"
echo "   OpenAI API Key: ${OPENAI_API_KEY:0:10}..."
echo "   Redis URL: ${UPSTASH_REDIS_URL:0:20}..."
echo ""

echo "✅ Models will be downloaded automatically by Docling"
echo "🔧 Starting services..."
echo "   - RQ workers (pdf_processing queue)"
echo "   - API server (0.0.0.0:8000)"
echo ""

# Start RQ workers in background
echo "🚀 Starting RQ workers..."
for i in $(seq 1 $RQ_WORKERS); do
    echo "   Starting RQ worker $i..."
    rq worker --url "$UPSTASH_REDIS_URL" pdf_processing &
done

# Wait a moment for workers to start
sleep 2

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
