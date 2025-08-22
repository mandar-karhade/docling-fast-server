# Docling CPU API

A high-performance FastAPI service for processing PDF documents using Docling with CPU-optimized deployment. This service provides OCR, text extraction, and document conversion capabilities without requiring GPU resources.

## 🚀 Quick Start

### Using Docker Hub (Recommended)

```bash
# Pull the image
docker pull legendofmk/docling-cpu-api:latest

# Run the container
docker run -d \
  --name docling-api \
  -p 8001:8000 \
  -e OPENAI_API_KEY=your_openai_api_key_here \
  -v ./models:/home/appuser/.EasyOCR \
  -v ./output:/app/output \
  legendofmk/docling-cpu-api:latest
```

### Using Docker Compose

```bash
# Clone the repository
git clone <your-repo-url>
cd docling-custom

# Set your OpenAI API key
export OPENAI_API_KEY=your_openai_api_key_here

# Start the service
docker compose up -d
```

## 📋 API Endpoints

### Health Check
```bash
curl http://localhost:8001/health
```

### OCR Processing
```bash
curl -X POST \
  -F "file=@your_document.pdf" \
  http://localhost:8001/ocr
```

### Placeholder Endpoints
- `POST /serialize` - Serialization endpoint (placeholder)
- `POST /chunk` - Chunking endpoint (placeholder)

## 🔧 Features

- **CPU-Optimized**: No GPU required, runs efficiently on CPU-only infrastructure
- **EasyOCR Integration**: Automatic text recognition with persistent model caching
- **Multiple Output Formats**: JSON, Markdown, HTML, and plain text
- **Concurrent Processing**: Supports multiple simultaneous requests
- **Automatic Compression**: Gzip compression for bandwidth optimization
- **Environment Configuration**: Dynamic resource allocation based on hardware

## 📊 Performance

- **Success Rate**: 87.5% - 100% depending on concurrency level
- **Throughput**: ~0.02 requests/second (CPU-intensive OCR processing)
- **Scalability**: Successfully tested up to 12 concurrent requests
- **Compression**: Significant bandwidth savings with automatic gzip compression

## 🏗️ Architecture

- **FastAPI**: Modern, fast web framework
- **Uvicorn**: ASGI server with configurable workers
- **Docling**: PDF processing and OCR engine
- **EasyOCR**: Text recognition with persistent model caching
- **Docker**: Containerized deployment

## 📁 Project Structure

```
docling-custom/
├── main.py                 # FastAPI application
├── Dockerfile             # Docker image definition
├── docker-compose.yml     # Container orchestration
├── requirements.txt       # Production dependencies
├── build_and_push.sh      # Docker build and push script
├── docs/                  # Documentation
│   ├── DEPLOYMENT_GUIDE.md
│   └── DEPLOYMENT_DOCKER_HUB.md
├── tests/                # Test scripts
│   ├── test_ocr.py      # OCR testing script
│   └── test_concurrent.py # Concurrent testing script
└── requirements-local.txt # Local development dependencies
```

## 🔧 Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | Required | Your OpenAI API key |
| `OMP_NUM_THREADS` | 4 | Number of threads per worker |
| `UVICORN_WORKERS` | 2 | Number of Uvicorn worker processes |
| `CPU_LIMIT` | 8 | CPU cores limit |
| `MEMORY_LIMIT` | 4G | Memory limit |

### Resource Optimization

**For 8-Core Development:**
```bash
OMP_NUM_THREADS=4
UVICORN_WORKERS=2
```

**For 64-Core Production:**
```bash
OMP_NUM_THREADS=8
UVICORN_WORKERS=8
```

## 📚 Documentation

For detailed documentation, see the `docs/` directory:

- **[Deployment Guide](docs/DEPLOYMENT_GUIDE.md)** - Comprehensive deployment instructions
- **[Docker Hub Guide](docs/DEPLOYMENT_DOCKER_HUB.md)** - Docker Hub deployment and usage

## 🧪 Testing

### Single Request Test
```bash
python tests/test_ocr.py
```

### Concurrent Request Test
```bash
python tests/test_concurrent.py
```

## 🚀 Deployment

### Local Development
```bash
# Create virtual environment
uv venv
source .venv/bin/activate

# Install local dependencies
uv pip install -r requirements-local.txt

# Run tests
python tests/test_ocr.py
```

### Production Deployment
```bash
# Build and push to Docker Hub
./build_and_push.sh 1.0.0 latest

# Deploy using Docker Compose
docker compose up -d
```

## 🔒 Security

- Non-root user execution
- Environment variable configuration and validation
- Resource limits and reservations
- Persistent volume mounting for model caching
- Entrypoint script for robust startup control

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Test thoroughly
5. Submit a pull request

## 📄 License

This project is licensed under the MIT License.

## 🆘 Support

For issues and questions:
1. Check the documentation in `docs/`
2. Review the test scripts for usage examples
3. Check container logs: `docker logs docling-api`
