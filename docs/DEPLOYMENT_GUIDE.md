# Docling API Deployment Guide

## Concurrency Management Strategies

### 1. **Single Container with Multiple Workers** (Current Setup)
- **Configuration**: 8 Uvicorn workers, each using 8 cores
- **Capacity**: ~64 cores total usage
- **Pros**: Simple deployment, automatic load balancing
- **Cons**: All workers share same container resources

```bash
# Environment variables in docker-compose.yml
OMP_NUM_THREADS=8      # Cores per process
UVICORN_WORKERS=8      # Number of worker processes
```

### 2. **Multiple Container Instances** (Recommended for 64-core VM)
```yaml
# docker-compose-scaled.yml
services:
  docling-api-1:
    build: .
    ports:
      - "8001:8000"
    environment:
      - OMP_NUM_THREADS=8
      - UVICORN_WORKERS=1  # Single worker per container
    deploy:
      resources:
        limits:
          cpus: '8'
          memory: 4G

  docling-api-2:
    build: .
    ports:
      - "8002:8000"
    environment:
      - OMP_NUM_THREADS=8
      - UVICORN_WORKERS=1
    deploy:
      resources:
        limits:
          cpus: '8'
          memory: 4G

  # Repeat for 8 total instances (8 x 8 = 64 cores)

  nginx-load-balancer:
    image: nginx:alpine
    ports:
      - "80:80"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
    depends_on:
      - docling-api-1
      - docling-api-2
      # ... other instances
```

### 3. **Queue-Based Processing with Redis**
```python
# Add to requirements.txt
celery==5.3.4
redis==5.0.1

# celery_worker.py
from celery import Celery
import os

app = Celery('docling_worker')
app.config_from_object({
    'broker_url': 'redis://localhost:6379',
    'result_backend': 'redis://localhost:6379',
    'worker_concurrency': int(os.getenv('CELERY_WORKERS', 8)),
    'worker_prefetch_multiplier': 1,  # Process one task at a time
})

@app.task
def process_pdf_task(pdf_data, filename):
    # Your existing process_pdf logic here
    pass
```

### 4. **Kubernetes Deployment** (Production Scale)
```yaml
# k8s-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: docling-api
spec:
  replicas: 8  # 8 pods x 8 cores each
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
        image: docling-api:latest
        resources:
          requests:
            cpu: "8"
            memory: "4Gi"
          limits:
            cpu: "8"
            memory: "8Gi"
        env:
        - name: OMP_NUM_THREADS
          value: "8"
        - name: UVICORN_WORKERS
          value: "1"
```

## Performance Optimization Tips

### 1. **Memory Management**
- Monitor memory usage per worker
- Restart workers periodically to prevent memory leaks
- Use memory-mapped files for large PDFs

### 2. **CPU Allocation**
- **8 cores per process**: Good for medium PDFs (1-50 pages)
- **16 cores per process**: Better for large PDFs (50+ pages)
- **4 cores per process**: More concurrent smaller jobs

### 3. **Load Testing**
```bash
# Install Apache Bench
sudo apt-get install apache2-utils

# Test with multiple concurrent requests
ab -n 100 -c 10 -T 'multipart/form-data; boundary=----WebKitFormBoundary7MA4YWxkTrZu0gW' \
   -p test_pdf_post.txt http://localhost:8001/ocr
```

### 4. **Monitoring**
```yaml
# Add to docker-compose.yml
  prometheus:
    image: prom/prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml

  grafana:
    image: grafana/grafana
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
```

## Resource Scaling Recommendations

### For 64-core VM:
1. **High Throughput**: 16 containers × 4 cores each
2. **Balanced**: 8 containers × 8 cores each (Recommended)
3. **Large Files**: 4 containers × 16 cores each

### Configuration Examples:

#### High Throughput (Small PDFs)
```yaml
environment:
  - OMP_NUM_THREADS=4
  - UVICORN_WORKERS=1
deploy:
  replicas: 16
  resources:
    limits:
      cpus: '4'
      memory: 2G
```

#### Balanced (Medium PDFs)
```yaml
environment:
  - OMP_NUM_THREADS=8
  - UVICORN_WORKERS=1
deploy:
  replicas: 8
  resources:
    limits:
      cpus: '8'
      memory: 4G
```

#### Large Files (Complex PDFs)
```yaml
environment:
  - OMP_NUM_THREADS=16
  - UVICORN_WORKERS=1
deploy:
  replicas: 4
  resources:
    limits:
      cpus: '16'
      memory: 8G
```

## Quick Start Commands

```bash
# Current single container setup
docker compose up --build

# Scale to multiple instances (requires load balancer)
docker compose up --scale docling-api=8 --build

# With resource limits
docker compose -f docker-compose-production.yml up --build
```
