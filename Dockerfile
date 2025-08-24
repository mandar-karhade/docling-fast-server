# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for docling and uv
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install uv
RUN pip install uv

# Copy requirements first for better caching
COPY requirements.txt .

# Install CPU-only PyTorch first to avoid CUDA dependencies
RUN uv pip install --system torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cpu

# Install other dependencies
RUN uv pip install --system -r requirements.txt

# Copy application code
COPY . .

# Create non-root user for security
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app

# Create workspace directory for persistent storage
RUN mkdir -p /workspace && chown -R appuser:appuser /workspace

# Set EasyOCR model path to workspace for persistent storage
ENV EASYOCR_MODULE_PATH=/workspace
ENV EASYOCR_HOME=/workspace

# Create symbolic link to ensure EasyOCR uses workspace path
RUN ln -sf /workspace /home/appuser/.EasyOCR

# Ensure warmup_files directory exists and has proper permissions
RUN mkdir -p /app/warmup_files && chown -R appuser:appuser /app/warmup_files

# Note: Models will be downloaded at runtime to /workspace for persistent storage

# Make scripts executable
RUN chmod +x /app/entrypoint.sh

USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Use entrypoint script for better startup control
ENTRYPOINT ["/app/entrypoint.sh"]
