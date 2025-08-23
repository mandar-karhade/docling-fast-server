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

# Download EasyOCR models first (blocking)
echo "📥 Downloading EasyOCR models..."
ARTIFACTS_PATH=${ARTIFACTS_PATH:-/workspace}
if [ ! -f "$ARTIFACTS_PATH/craft_mlt_25k.pth" ]; then
    echo "   Models not found, downloading to $ARTIFACTS_PATH..."
    /app/download_models.sh
fi

# Set EasyOCR to use cached models and disable downloads
echo "   🔧 Configuring EasyOCR to use cached models..."
export EASYOCR_MODULE_PATH="$ARTIFACTS_PATH"
export EASYOCR_DOWNLOAD_ENABLED="false"

# Create symbolic link to ensure EasyOCR finds the models
if [ ! -L "/home/appuser/.EasyOCR/model" ]; then
    echo "   🔗 Creating symbolic link for EasyOCR models..."
    ln -sf "$ARTIFACTS_PATH" "/home/appuser/.EasyOCR/model"
fi

echo "   ✅ EasyOCR configured to use models from $ARTIFACTS_PATH"

# Pre-download Docling artifacts if not already cached
echo "📥 Checking Docling artifacts..."
if [ ! -d "$ARTIFACTS_PATH/hub" ] || [ -z "$(ls -A $ARTIFACTS_PATH/hub 2>/dev/null)" ]; then
    echo "   Downloading Docling artifacts to $ARTIFACTS_PATH (this may take several minutes)..."
    python -c "from docling.document_converter import DocumentConverter; from docling.datamodel.base_models import InputFormat; from docling.datamodel.pipeline_options import PdfPipelineOptions; converter = DocumentConverter(format_options={InputFormat.PDF: PdfPipelineOptions(artifacts_path='$ARTIFACTS_PATH')}); print('Docling artifacts pre-downloaded')"
    echo "   ✅ Docling artifacts downloaded successfully to $ARTIFACTS_PATH"
else
    echo "   ✅ Docling artifacts already cached in $ARTIFACTS_PATH"
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
