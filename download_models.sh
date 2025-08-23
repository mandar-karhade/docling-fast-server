#!/bin/bash

# Download EasyOCR models script
# This script downloads EasyOCR models to ensure they're available before the API starts

set -e

echo "🚀 Starting model download process..."

# Set default artifacts path
ARTIFACTS_PATH=${ARTIFACTS_PATH:-/workspace}

echo "📥 Downloading EasyOCR models to $ARTIFACTS_PATH..."

# Create the directory if it doesn't exist
mkdir -p "$ARTIFACTS_PATH"

# Create a tiny test image for EasyOCR
echo "   Creating test image for EasyOCR..."
cat > /tmp/test_image.png << 'EOF'
iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==
EOF

# Decode base64 to create a 1x1 pixel PNG
echo "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==" | base64 -d > /tmp/test_image.png

# Download EasyOCR models with proper error handling
echo "   Downloading detection and recognition models..."
if easyocr --model_storage_directory "$ARTIFACTS_PATH" -l en -f /tmp/test_image.png; then
    echo "   ✅ EasyOCR models downloaded successfully"
else
    echo "   ⚠️  EasyOCR download had issues, but continuing..."
fi

# Clean up the test image
rm -f /tmp/test_image.png

# Verify models are present
if [ -f "$ARTIFACTS_PATH/craft_mlt_25k.pth" ] && [ -f "$ARTIFACTS_PATH/english_g2.pth" ]; then
    echo "   ✅ EasyOCR models verified in $ARTIFACTS_PATH"
    echo "   📊 Model files:"
    ls -lh "$ARTIFACTS_PATH"/*.pth 2>/dev/null || echo "   No .pth files found"
else
    echo "   ⚠️  EasyOCR models may not be fully downloaded"
fi

echo "🎉 Model download process completed!"
