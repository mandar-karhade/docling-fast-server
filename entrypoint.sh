#!/bin/bash

# Entrypoint script for Docling CPU API
set -e

echo "🚀 Starting Docling CPU API..."

# Set default values if not provided
export OMP_NUM_THREADS=${OMP_NUM_THREADS:-4}
export UVICORN_WORKERS=${UVICORN_WORKERS:-2}

# Validate OpenAI API key
if [ -z "$OPENAI_API_KEY" ]; then
    echo "❌ Error: OPENAI_API_KEY environment variable is required"
    exit 1
fi

echo "📊 Configuration:"
echo "   OMP_NUM_THREADS: $OMP_NUM_THREADS"
echo "   UVICORN_WORKERS: $UVICORN_WORKERS"
echo "   OpenAI API Key: ${OPENAI_API_KEY:0:10}..."
echo ""

# Pre-download Docling artifacts if not already cached
echo "📥 Checking Docling artifacts..."
if [ ! -d "/home/appuser/.cache/huggingface/hub" ] || [ -z "$(ls -A /home/appuser/.cache/huggingface/hub 2>/dev/null)" ]; then
    echo "   Downloading Docling artifacts (this may take several minutes)..."
    python -c "from docling.document_converter import DocumentConverter; from docling.datamodel.base_models import InputFormat; from docling.datamodel.pipeline_options import PdfPipelineOptions; converter = DocumentConverter(format_options={InputFormat.PDF: PdfPipelineOptions()}); print('Docling artifacts pre-downloaded')"
    echo "   ✅ Docling artifacts downloaded successfully"
else
    echo "   ✅ Docling artifacts already cached"
fi

echo "🔧 Starting Uvicorn server..."
echo "   Host: 0.0.0.0"
echo "   Port: 8000"
echo "   Workers: $UVICORN_WORKERS"
echo ""

# Start the application
exec uvicorn main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --workers $UVICORN_WORKERS \
    --log-level info
