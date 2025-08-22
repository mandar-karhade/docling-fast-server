# Docker Hub Deployment Guide

This guide explains how to deploy the Docling API using the published Docker Hub image.

## Quick Start

### 1. Pull the Image
```bash
docker pull legendofmk/docling-cpu-api:latest
```

### 2. Run the Container
```bash
docker run -d \
  --name docling-api \
  -p 8001:8000 \
  -e OPENAI_API_KEY=your_openai_api_key_here \
  -e OMP_NUM_THREADS=4 \
  -e UVICORN_WORKERS=2 \
  legendofmk/docling-cpu-api:latest
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_API_KEY` | Required | Your OpenAI API key |
| `OMP_NUM_THREADS` | 4 | Number of threads per worker |
| `UVICORN_WORKERS` | 2 | Number of Uvicorn worker processes |
| `CPU_LIMIT` | 8 | CPU cores limit |
| `MEMORY_LIMIT` | 4G | Memory limit |

## Production Deployment

### Using Docker Compose
```yaml
version: '3.8'
services:
  docling-api:
    image: legendofmk/docling-cpu-api:latest
    ports:
      - "8001:8000"
    environment:
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - OMP_NUM_THREADS=${OMP_NUM_THREADS:-8}
      - UVICORN_WORKERS=${UVICORN_WORKERS:-8}

    restart: unless-stopped
    deploy:
      resources:
        limits:
          cpus: '${CPU_LIMIT:-64}'
          memory: ${MEMORY_LIMIT:-32G}
        reservations:
          cpus: '${CPU_RESERVATION:-8}'
          memory: ${MEMORY_RESERVATION:-4G}
```

### Using Kubernetes
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: docling-api
spec:
  replicas: 1
  selector:
    matchLabels:
      app: docling-api
  template:
    metadata:
      labels:
        app: docling-api
    spec:
      containers:
      - name: docling-api
        image: legendofmk/docling-cpu-api:latest
        ports:
        - containerPort: 8000
        env:
        - name: OPENAI_API_KEY
          valueFrom:
            secretKeyRef:
              name: openai-secret
              key: api-key
        - name: OMP_NUM_THREADS
          value: "8"
        - name: UVICORN_WORKERS
          value: "8"
        resources:
          limits:
            cpu: "64"
            memory: "32Gi"
          requests:
            cpu: "8"
            memory: "4Gi"

```

## API Endpoints

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

## Performance Tuning

### For 64-Core Production Server
```bash
docker run -d \
  --name docling-api \
  -p 8001:8000 \
  -e OPENAI_API_KEY=your_key \
  -e OMP_NUM_THREADS=8 \
  -e UVICORN_WORKERS=8 \
  -e CPU_LIMIT=64 \
  -e MEMORY_LIMIT=32G \
  -v ./models:/home/appuser/.EasyOCR \
  -v ./output:/app/output \
  mandar-karhade/docling-fast-api:latest
```

### For 8-Core Development Server
```bash
docker run -d \
  --name docling-api \
  -p 8001:8000 \
  -e OPENAI_API_KEY=your_key \
  -e OMP_NUM_THREADS=4 \
  -e UVICORN_WORKERS=2 \
  -e CPU_LIMIT=8 \
  -e MEMORY_LIMIT=4G \
  -v ./models:/home/appuser/.EasyOCR \
  -v ./output:/app/output \
  mandar-karhade/docling-fast-api:latest
```

## Troubleshooting

### Check Container Logs
```bash
docker logs docling-api
```

### Check Health Status
```bash
curl http://localhost:8001/health
```

### Restart Container
```bash
docker restart docling-api
```

## Available Tags

- `latest` - Most recent stable version
- `1.0.0` - Specific version tag
- `v1.0.0` - Alternative version format

## Security Notes

1. Always use environment variables for sensitive data
2. Consider using Docker secrets in production
3. Limit container resources to prevent abuse
4. Use persistent volumes for model caching
