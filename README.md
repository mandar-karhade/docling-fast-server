# Docling API Docker Container

A FastAPI service that processes PDF files using Docling and returns results in various formats.

## Endpoints

### 1. Health Check
- **GET** `/health`
- Returns service status and configuration info

### 2. OCR Processing
- **POST** `/ocr`
- Accepts PDF file upload
- Returns ZIP file containing processed outputs (markdown, JSON, HTML, text)

### 3. Serialize (Placeholder)
- **POST** `/serialize`
- Placeholder endpoint - returns 200 OK

### 4. Chunk (Placeholder)
- **POST** `/chunk`
- Placeholder endpoint - returns 200 OK

## Quick Start

### Using Docker Compose (Recommended)

1. Set your OpenAI API key:
```bash
export OPENAI_API_KEY="your-api-key-here"
```

2. Build and run:
```bash
docker compose up --build
```

3. Test the service:
```bash
python test_client.py
```

### Using Docker directly

1. Build the image:
```bash
docker build -t docling-api .
```

2. Run the container:
```bash
docker run -p 8000:8000 -e OPENAI_API_KEY="your-api-key-here" docling-api
```

## API Usage

### Health Check
```bash
curl http://localhost:8000/health
```

### Process PDF
```bash
curl -X POST -F "file=@your-document.pdf" http://localhost:8000/ocr -o results.zip
```

### Test Placeholder Endpoints
```bash
curl -X POST http://localhost:8000/serialize
curl -X POST http://localhost:8000/chunk
```

## Environment Variables

- `OPENAI_API_KEY`: Your OpenAI API key (required for picture description)
- `OMP_NUM_THREADS`: Number of OpenMP threads (default: 4)

## Output Formats

The `/ocr` endpoint returns a ZIP file containing:
- `{filename}.md` - Markdown format
- `{filename}.json` - JSON format
- `{filename}.html` - HTML format
- `{filename}.txt` - Plain text format
