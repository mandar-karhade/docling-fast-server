#!/bin/bash

# Entrypoint script for Docling CPU API with in-memory job storage
set -e

echo "🚀 Starting Docling CPU API with in-memory job storage..."

# Environment variables (some optional, some required)

# Set defaults for optional environment variables
export UVICORN_WORKERS=${UVICORN_WORKERS:-4}
export OMP_NUM_THREADS=${OMP_NUM_THREADS:-1}

# OPENAI_API_KEY is optional but recommended for enhanced processing
if [ -z "$OPENAI_API_KEY" ]; then
    echo "ℹ️  Note: OPENAI_API_KEY not set - some features may be limited"
else
    echo "✅ OpenAI API Key configured"
fi

echo "📊 Configuration:"
echo "   OMP_NUM_THREADS: $OMP_NUM_THREADS"
echo "   OPENBLAS_NUM_THREADS: $OPENBLAS_NUM_THREADS"
echo "   MKL_NUM_THREADS: $MKL_NUM_THREADS"
echo "   UVICORN_WORKERS: $UVICORN_WORKERS"
echo "   CPU_LIMIT: ${CPU_LIMIT:-not set}"
echo "   MEMORY_LIMIT: ${MEMORY_LIMIT:-not set}"
if [ -n "$OPENAI_API_KEY" ]; then
    echo "   OpenAI API Key: ${OPENAI_API_KEY:0:10}***"
fi
echo ""

echo "✅ Models will be downloaded automatically by Docling"
echo "🔧 Starting services..."
echo "   - API server (0.0.0.0:8000) with in-memory job storage"
echo ""

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
echo "   Workers: $UVICORN_WORKERS"
echo ""

# Start the API server (warmup already completed)
exec uvicorn main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers $UVICORN_WORKERS \
    --log-level info
