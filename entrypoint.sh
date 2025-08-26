#!/bin/bash

# Entrypoint script for Docling CPU API with managed Redis and RQ workers
set -e

echo "🚀 Starting Docling CPU API with managed Redis and RQ workers..."

# No configurable environment variables needed

# Validate OpenAI API key
if [ -z "$OPENAI_API_KEY" ]; then
    echo "❌ Error: OPENAI_API_KEY environment variable is required"
    exit 1
fi

# Validate Redis REST API credentials (optional - only needed for persistence)
if [ -z "$UPSTASH_REDIS_REST_URL" ] || [ -z "$UPSTASH_REDIS_REST_TOKEN" ]; then
    echo "⚠️  Warning: UPSTASH_REDIS_REST_URL and UPSTASH_REDIS_REST_TOKEN not set"
    echo "   Job queue will use in-memory storage (jobs lost on restart)"
fi

echo "📊 Configuration:"
echo "   OpenAI API Key: ${OPENAI_API_KEY:0:10}..."
echo "   Redis REST URL: ${UPSTASH_REDIS_REST_URL:0:30}..."
echo ""

echo "✅ Models will be downloaded automatically by Docling"
echo "🔧 Starting services..."
echo "   - API server (0.0.0.0:8000) with Upstash Redis support"
echo ""

# Test Redis connection (optional for job persistence)
echo "🔍 Testing Redis connection..."
if python3 -c "
from upstash_redis import Redis
import os
try:
    r = Redis(url=os.environ.get('UPSTASH_REDIS_REST_URL', ''), token=os.environ.get('UPSTASH_REDIS_REST_TOKEN', ''))
    r.ping()
    print('✅ Redis connection successful')
except Exception as e:
    print('⚠️ Redis connection failed - using in-memory job storage')
" 2>/dev/null; then
    echo "✅ Redis connection verified"
else
    echo "⚠️ Redis connection failed - continuing with in-memory job storage"
fi

echo ""
echo "🔥 Running container-level warmup process..."
echo "   This ensures models are downloaded and endpoints tested once before workers start"

# Run warmup synchronously before starting any workers
python3 -c "
import sys
import os

# Set up environment
sys.path.insert(0, '/app')
os.chdir('/app')

try:
    from src.services.warmup_service import WarmupService
    
    print('🔥 Starting container warmup...')
    
    # Create warmup service in container-level mode (no Redis coordination)
    warmup = WarmupService(use_redis_coordination=False)
    
    # Run warmup synchronously (blocking)
    warmup.run_warmup_sync()
    
    print('✅ Container warmup completed successfully')
    
except Exception as e:
    print(f'❌ Warmup failed: {e}')
    import traceback
    traceback.print_exc()
    sys.exit(1)
"

echo ""
echo "🚀 Starting API server with pre-warmed container..."
echo "   Host: 0.0.0.0"
echo "   Port: 8000"
echo "   Workers: 4"
echo ""

# Start the API server (warmup already completed)
# Set OpenMP threads for optimal performance
export OMP_NUM_THREADS=4

exec uvicorn main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers 4 \
    --log-level info
