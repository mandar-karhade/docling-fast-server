# Use Python 3.11 slim image as base
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies for docling and uv
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
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

# Create EasyOCR cache directory for the user with proper structure
RUN mkdir -p /home/appuser/.EasyOCR/model && chown -R appuser:appuser /home/appuser/.EasyOCR

# Make entrypoint script executable
RUN chmod +x /app/entrypoint.sh

USER appuser

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Use entrypoint script for better startup control
ENTRYPOINT ["/app/entrypoint.sh"]
