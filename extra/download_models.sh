#!/bin/bash

# Download EasyOCR models script
# This script downloads EasyOCR models directly from GitHub releases

set -e

echo "🚀 Starting model download process..."

# Set default artifacts path
ARTIFACTS_PATH=${ARTIFACTS_PATH:-/home/appuser/.EasyOCR}

echo "📥 Downloading EasyOCR models to $ARTIFACTS_PATH..."

# Create the directory if it doesn't exist
mkdir -p "$ARTIFACTS_PATH"

# Download detection model (craft_mlt_25k.pth)
echo "   📥 Downloading detection model (craft_mlt_25k.pth)..."
if [ ! -f "$ARTIFACTS_PATH/craft_mlt_25k.pth" ]; then
    curl -L -o "$ARTIFACTS_PATH/craft_mlt_25k.zip" \
        "https://github.com/JaidedAI/EasyOCR/releases/download/pre-v1.1.6/craft_mlt_25k.zip"
    unzip -o "$ARTIFACTS_PATH/craft_mlt_25k.zip" -d "$ARTIFACTS_PATH"
    rm "$ARTIFACTS_PATH/craft_mlt_25k.zip"
    echo "   ✅ Detection model downloaded"
else
    echo "   ✅ Detection model already exists"
fi

# Download recognition models
echo "   📥 Downloading recognition models..."

# English model
if [ ! -f "$ARTIFACTS_PATH/english_g2.pth" ]; then
    echo "   📥 Downloading english_g2.pth..."
    curl -L -o "$ARTIFACTS_PATH/english_g2.zip" \
        "https://github.com/JaidedAI/EasyOCR/releases/download/v1.3/english_g2.zip"
    unzip -o "$ARTIFACTS_PATH/english_g2.zip" -d "$ARTIFACTS_PATH"
    rm "$ARTIFACTS_PATH/english_g2.zip"
    echo "   ✅ English model downloaded"
else
    echo "   ✅ English model already exists"
fi

# Latin model
if [ ! -f "$ARTIFACTS_PATH/latin_g2.pth" ]; then
    echo "   📥 Downloading latin_g2.pth..."
    curl -L -o "$ARTIFACTS_PATH/latin_g2.zip" \
        "https://github.com/JaidedAI/EasyOCR/releases/download/v1.3/latin_g2.zip"
    unzip -o "$ARTIFACTS_PATH/latin_g2.zip" -d "$ARTIFACTS_PATH"
    rm "$ARTIFACTS_PATH/latin_g2.zip"
    echo "   ✅ Latin model downloaded"
else
    echo "   ✅ Latin model already exists"
fi

# Chinese Simplified model (2nd gen)
if [ ! -f "$ARTIFACTS_PATH/zh_sim_g2.pth" ]; then
    echo "   📥 Downloading zh_sim_g2.pth..."
    curl -L -o "$ARTIFACTS_PATH/zh_sim_g2.zip" \
        "https://github.com/JaidedAI/EasyOCR/releases/download/v1.3/zh_sim_g2.zip"
    unzip -o "$ARTIFACTS_PATH/zh_sim_g2.zip" -d "$ARTIFACTS_PATH"
    rm "$ARTIFACTS_PATH/zh_sim_g2.zip"
    echo "   ✅ Chinese Simplified model downloaded"
else
    echo "   ✅ Chinese Simplified model already exists"
fi

# Japanese model (2nd gen)
if [ ! -f "$ARTIFACTS_PATH/japanese_g2.pth" ]; then
    echo "   📥 Downloading japanese_g2.pth..."
    curl -L -o "$ARTIFACTS_PATH/japanese_g2.zip" \
        "https://github.com/JaidedAI/EasyOCR/releases/download/v1.3/japanese_g2.zip"
    unzip -o "$ARTIFACTS_PATH/japanese_g2.zip" -d "$ARTIFACTS_PATH"
    rm "$ARTIFACTS_PATH/japanese_g2.zip"
    echo "   ✅ Japanese model downloaded"
else
    echo "   ✅ Japanese model already exists"
fi

# Korean model (2nd gen)
if [ ! -f "$ARTIFACTS_PATH/korean_g2.pth" ]; then
    echo "   📥 Downloading korean_g2.pth..."
    curl -L -o "$ARTIFACTS_PATH/korean_g2.zip" \
        "https://github.com/JaidedAI/EasyOCR/releases/download/v1.3/korean_g2.zip"
    unzip -o "$ARTIFACTS_PATH/korean_g2.zip" -d "$ARTIFACTS_PATH"
    rm "$ARTIFACTS_PATH/korean_g2.zip"
    echo "   ✅ Korean model downloaded"
else
    echo "   ✅ Korean model already exists"
fi

# Telugu model (2nd gen)
if [ ! -f "$ARTIFACTS_PATH/telugu_g2.pth" ]; then
    echo "   📥 Downloading telugu_g2.pth..."
    curl -L -o "$ARTIFACTS_PATH/telugu.zip" \
        "https://github.com/JaidedAI/EasyOCR/releases/download/v1.2/telugu.zip"
    unzip -o "$ARTIFACTS_PATH/telugu.zip" -d "$ARTIFACTS_PATH"
    rm "$ARTIFACTS_PATH/telugu.zip"
    echo "   ✅ Telugu model downloaded"
else
    echo "   ✅ Telugu model already exists"
fi

# Kannada model (2nd gen)
if [ ! -f "$ARTIFACTS_PATH/kannada_g2.pth" ]; then
    echo "   📥 Downloading kannada_g2.pth..."
    curl -L -o "$ARTIFACTS_PATH/kannada.zip" \
        "https://github.com/JaidedAI/EasyOCR/releases/download/v1.2/kannada.zip"
    unzip -o "$ARTIFACTS_PATH/kannada.zip" -d "$ARTIFACTS_PATH"
    rm "$ARTIFACTS_PATH/kannada.zip"
    echo "   ✅ Kannada model downloaded"
else
    echo "   ✅ Kannada model already exists"
fi

# Additional 1st generation models for broader language support

# Latin model (1st gen)
if [ ! -f "$ARTIFACTS_PATH/latin.pth" ]; then
    echo "   📥 Downloading latin.pth (1st gen)..."
    curl -L -o "$ARTIFACTS_PATH/latin.zip" \
        "https://github.com/JaidedAI/EasyOCR/releases/download/pre-v1.1.6/latin.zip"
    unzip -o "$ARTIFACTS_PATH/latin.zip" -d "$ARTIFACTS_PATH"
    rm "$ARTIFACTS_PATH/latin.zip"
    echo "   ✅ Latin model (1st gen) downloaded"
else
    echo "   ✅ Latin model (1st gen) already exists"
fi

# Chinese Simplified model (1st gen)
if [ ! -f "$ARTIFACTS_PATH/chinese_sim.pth" ]; then
    echo "   📥 Downloading chinese_sim.pth (1st gen)..."
    curl -L -o "$ARTIFACTS_PATH/chinese_sim.zip" \
        "https://github.com/JaidedAI/EasyOCR/releases/download/pre-v1.1.6/chinese_sim.zip"
    unzip -o "$ARTIFACTS_PATH/chinese_sim.zip" -d "$ARTIFACTS_PATH"
    rm "$ARTIFACTS_PATH/chinese_sim.zip"
    echo "   ✅ Chinese Simplified model (1st gen) downloaded"
else
    echo "   ✅ Chinese Simplified model (1st gen) already exists"
fi

# Chinese Traditional model (1st gen)
if [ ! -f "$ARTIFACTS_PATH/chinese.pth" ]; then
    echo "   📥 Downloading chinese.pth (1st gen)..."
    curl -L -o "$ARTIFACTS_PATH/chinese.zip" \
        "https://github.com/JaidedAI/EasyOCR/releases/download/pre-v1.1.6/chinese.zip"
    unzip -o "$ARTIFACTS_PATH/chinese.zip" -d "$ARTIFACTS_PATH"
    rm "$ARTIFACTS_PATH/chinese.zip"
    echo "   ✅ Chinese Traditional model (1st gen) downloaded"
else
    echo "   ✅ Chinese Traditional model (1st gen) already exists"
fi

# Japanese model (1st gen)
if [ ! -f "$ARTIFACTS_PATH/japanese.pth" ]; then
    echo "   📥 Downloading japanese.pth (1st gen)..."
    curl -L -o "$ARTIFACTS_PATH/japanese.zip" \
        "https://github.com/JaidedAI/EasyOCR/releases/download/pre-v1.1.6/japanese.zip"
    unzip -o "$ARTIFACTS_PATH/japanese.zip" -d "$ARTIFACTS_PATH"
    rm "$ARTIFACTS_PATH/japanese.zip"
    echo "   ✅ Japanese model (1st gen) downloaded"
else
    echo "   ✅ Japanese model (1st gen) already exists"
fi

# Korean model (1st gen)
if [ ! -f "$ARTIFACTS_PATH/korean.pth" ]; then
    echo "   📥 Downloading korean.pth (1st gen)..."
    curl -L -o "$ARTIFACTS_PATH/korean.zip" \
        "https://github.com/JaidedAI/EasyOCR/releases/download/pre-v1.1.6/korean.zip"
    unzip -o "$ARTIFACTS_PATH/korean.zip" -d "$ARTIFACTS_PATH"
    rm "$ARTIFACTS_PATH/korean.zip"
    echo "   ✅ Korean model (1st gen) downloaded"
else
    echo "   ✅ Korean model (1st gen) already exists"
fi

# Thai model (1st gen)
if [ ! -f "$ARTIFACTS_PATH/thai.pth" ]; then
    echo "   📥 Downloading thai.pth (1st gen)..."
    curl -L -o "$ARTIFACTS_PATH/thai.zip" \
        "https://github.com/JaidedAI/EasyOCR/releases/download/pre-v1.1.6/thai.zip"
    unzip -o "$ARTIFACTS_PATH/thai.zip" -d "$ARTIFACTS_PATH"
    rm "$ARTIFACTS_PATH/thai.zip"
    echo "   ✅ Thai model (1st gen) downloaded"
else
    echo "   ✅ Thai model (1st gen) already exists"
fi

# Devanagari model (1st gen)
if [ ! -f "$ARTIFACTS_PATH/devanagari.pth" ]; then
    echo "   📥 Downloading devanagari.pth (1st gen)..."
    curl -L -o "$ARTIFACTS_PATH/devanagari.zip" \
        "https://github.com/JaidedAI/EasyOCR/releases/download/pre-v1.1.6/devanagari.zip"
    unzip -o "$ARTIFACTS_PATH/devanagari.zip" -d "$ARTIFACTS_PATH"
    rm "$ARTIFACTS_PATH/devanagari.zip"
    echo "   ✅ Devanagari model (1st gen) downloaded"
else
    echo "   ✅ Devanagari model (1st gen) already exists"
fi

# Cyrillic model (1st gen)
if [ ! -f "$ARTIFACTS_PATH/cyrillic.pth" ]; then
    echo "   📥 Downloading cyrillic.pth (1st gen)..."
    curl -L -o "$ARTIFACTS_PATH/cyrillic.zip" \
        "https://github.com/JaidedAI/EasyOCR/releases/download/pre-v1.1.6/cyrillic.zip"
    unzip -o "$ARTIFACTS_PATH/cyrillic.zip" -d "$ARTIFACTS_PATH"
    rm "$ARTIFACTS_PATH/cyrillic.zip"
    echo "   ✅ Cyrillic model (1st gen) downloaded"
else
    echo "   ✅ Cyrillic model (1st gen) already exists"
fi

# Arabic model (1st gen)
if [ ! -f "$ARTIFACTS_PATH/arabic.pth" ]; then
    echo "   📥 Downloading arabic.pth (1st gen)..."
    curl -L -o "$ARTIFACTS_PATH/arabic.zip" \
        "https://github.com/JaidedAI/EasyOCR/releases/download/pre-v1.1.6/arabic.zip"
    unzip -o "$ARTIFACTS_PATH/arabic.zip" -d "$ARTIFACTS_PATH"
    rm "$ARTIFACTS_PATH/arabic.zip"
    echo "   ✅ Arabic model (1st gen) downloaded"
else
    echo "   ✅ Arabic model (1st gen) already exists"
fi

# Tamil model (1st gen)
if [ ! -f "$ARTIFACTS_PATH/tamil.pth" ]; then
    echo "   📥 Downloading tamil.pth (1st gen)..."
    curl -L -o "$ARTIFACTS_PATH/tamil.zip" \
        "https://github.com/JaidedAI/EasyOCR/releases/download/v1.1.7/tamil.zip"
    unzip -o "$ARTIFACTS_PATH/tamil.zip" -d "$ARTIFACTS_PATH"
    rm "$ARTIFACTS_PATH/tamil.zip"
    echo "   ✅ Tamil model (1st gen) downloaded"
else
    echo "   ✅ Tamil model (1st gen) already exists"
fi

# Bengali model (1st gen)
if [ ! -f "$ARTIFACTS_PATH/bengali.pth" ]; then
    echo "   📥 Downloading bengali.pth (1st gen)..."
    curl -L -o "$ARTIFACTS_PATH/bengali.zip" \
        "https://github.com/JaidedAI/EasyOCR/releases/download/v1.1.8/bengali.zip"
    unzip -o "$ARTIFACTS_PATH/bengali.zip" -d "$ARTIFACTS_PATH"
    rm "$ARTIFACTS_PATH/bengali.zip"
    echo "   ✅ Bengali model (1st gen) downloaded"
else
    echo "   ✅ Bengali model (1st gen) already exists"
fi

# Verify models are present
echo "   🔍 Verifying downloaded models..."
expected_models=(
    "craft_mlt_25k.pth"
    # 2nd generation models
    "english_g2.pth" "latin_g2.pth" "zh_sim_g2.pth" "japanese_g2.pth" "korean_g2.pth" "telugu_g2.pth" "kannada_g2.pth"
    # 1st generation models
    "latin.pth" "chinese_sim.pth" "chinese.pth" "japanese.pth" "korean.pth" "thai.pth" "devanagari.pth" "cyrillic.pth" "arabic.pth" "tamil.pth" "bengali.pth"
)
missing_models=()

for model in "${expected_models[@]}"; do
    if [ ! -f "$ARTIFACTS_PATH/$model" ]; then
        missing_models+=("$model")
    fi
done

if [ ${#missing_models[@]} -eq 0 ]; then
    echo "   ✅ All EasyOCR models verified in $ARTIFACTS_PATH"
    echo "   📊 Model files:"
    ls -lh "$ARTIFACTS_PATH"/*.pth 2>/dev/null || echo "   No .pth files found"
else
    echo "   ⚠️  Some EasyOCR models may not be fully downloaded:"
    printf "   ❌ Missing: %s\n" "${missing_models[@]}"
    echo "   📊 Available model files:"
    ls -la "$ARTIFACTS_PATH"/*.pth 2>/dev/null || echo "   No .pth files found"
fi

echo "🎉 Model download process completed!"
