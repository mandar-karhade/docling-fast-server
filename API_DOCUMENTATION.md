# Docling API Documentation

## Overview
- **Purpose**: PDF processing API using Docling for OCR and document conversion
- **Framework**: FastAPI with Uvicorn (multi-worker support)
- **Deployment**: Docker containerized, designed for RunPod.io
- **Queue Management**: In-memory ThreadPoolExecutor with file-based persistence for multi-worker environments

## Quick Reference: /ocr/async

### POST /ocr/async
- **Content-Type**: multipart/form-data
- **Fields**:
  - **file**: PDF file (required)
  - **job_id**: string (optional). If provided, used as the canonical identifier; if it already exists, returns 409 with `{ "job_id": <value> }`.
  - **request_id**: string (optional, deprecated alias for `job_id`). Same behavior as `job_id`.

### Responses
- **200 OK** (submit):
```json
{ "job_id": "<id>" }
```

### Examples: /ocr
```bash
# Default pipeline (auto-fallback may switch to limited on specific error)
curl -sS -X POST \
  -F "file=@/path/to/doc.pdf" \
  http://<host>:8000/ocr | jq '{status, filename, conversion_method, files: (.files | keys)}'

# Force limited pipeline only
curl -sS -X POST \
  -F "file=@/path/to/doc.pdf" \
  -F "conversion_method=limited" \
  http://<host>:8000/ocr | jq '{status, filename, conversion_method, files: (.files | keys)}'
```
- **409 Conflict** (duplicate job_id/request_id):
```json
{ "job_id": "<existing_id>" }
```
- **5xx**: Unexpected server error during enqueue

### Poll job status
- **GET /jobs/{job_id}** → returns `status` in [queued, started, finished, failed] and `result` when finished.
- When `status` is `finished`, the `result` mirrors the synchronous `/ocr` output including `conversion_method` and `files`.

Example finished job response (truncated):
```json
{
  "job_id": "<id>",
  "status": "finished",
  "result": {
    "status": "success",
    "filename": "document.pdf",
    "conversion_method": "default",
    "files": {
      "filename": "document",
      "doctags": { },
      "json": { },
      "markdown": "...",
      "html": "...",
      "chunks": { }
    }
  }
}
```

### Example (curl)
```bash
# submit
curl -sS -X POST \
  -F "file=@/path/to/doc.pdf" \
  -F "request_id=REQ-123" \
  http://<host>:8000/ocr/async | jq '.'

# duplicate (returns 409 with existing job_id)
curl -sS -X POST -w "\n%{http_code}\n" \
  -F "file=@/path/to/doc.pdf" \
  -F "request_id=REQ-123" \
  http://<host>:8000/ocr/async | jq '.'

# poll
curl -sS http://<host>:8000/jobs/<job_id> | jq '.'
```

## Core Endpoints

### 1. Health & Status
- **`GET /health`** - Complete system health check
  - Returns: `{"status": "ready|warming_up", "service": "docling-api", "openai_key_available": boolean, "warmup": {...}}`
  - **Behavior**: Only shows "ready" after complete warmup process
  
- **`GET /warmup_status`** - Dedicated warmup status for programmatic management
  - Returns: `{"ready": boolean, "status": "ready|warming_up", "coordination_mode": "container-level", "worker_id": "worker_X"}`
  - **Use Case**: Poll this endpoint before submitting jobs programmatically

### 2. PDF Processing

#### Synchronous Processing
- **`POST /ocr`** - Immediate PDF processing
  - **Input**: `multipart/form-data`
    - `file` (required): PDF file
    - `conversion_method` (optional): `"default"` (default) or `"limited"`
      - `default`: run full pipeline; on a specific transformers image-size error, server auto-retries with limited pipeline
      - `limited`: run limited pipeline only (tables/code/formula/picture disabled; no remote services)
  - **Output**:
    ```json
    {
      "status": "success",
      "filename": "document.pdf",
      "conversion_method": "default" | "limited",
      "files": {
        "filename": "document",
        "doctags": { },
        "json": { },
        "markdown": "...",
        "html": "...",
        "chunks": { }
      }
    }
    ```
  - **Processing Time**: 10-30 seconds depending on PDF complexity
  - **Behavior**: Blocks until complete

#### Asynchronous Processing
- **`POST /ocr/async`** - Queue-based PDF processing
  - **Input**: `multipart/form-data` with `file` field (PDF); optional `job_id` (or deprecated `request_id`)
  - **Output**: `{ "job_id": "<id>" }`
  - **Behavior**: Returns immediately with job ID (echoes provided `job_id`/`request_id` if supplied)

### 3. Job Management
- **`GET /jobs/{job_id}`** - Get specific job status and results
  - **Statuses**: `submitted` → `started` → `finished|failed`
  - **Returns**: Job metadata + results (when finished)
  
- **`GET /jobs`** - List all jobs
  - **Returns**: `{"jobs": [...], "total_jobs": number}`
  - **Includes**: Active, completed, and failed jobs

## Warmup Process

### Container-Level Warmup (Current Implementation)
1. **Timing**: Runs **before** Uvicorn workers start
2. **Location**: Executed in `entrypoint.sh` script
3. **Process**:
   - Downloads EasyOCR models
   - Tests `/ocr` endpoint with 1 PDF
   - Tests `/ocr/async` endpoint with 2 PDFs  
   - Waits for async jobs to complete (2-minute timeout)
   - Validates all results
4. **Coordination**: No external dependencies (Redis optional)
5. **Logging**: Detailed progress messages with result keys

### Warmup Test Files
- Uses PDFs from `warmup_files/` directory
- Processes test documents to verify full pipeline
- Confirms both sync and async endpoints work correctly

## Queue Management

### Worker Pool
- **Concurrency**: Controlled by `RQ_WORKERS` environment variable (default: 2)
- **Implementation**: `ThreadPoolExecutor` with fixed thread pool
- **Behavior**: Only `RQ_WORKERS` jobs process simultaneously, others queue

### Multi-Worker Persistence
- **Storage**: File-based shared storage at `/tmp/docling_jobs.json`
- **Locking**: `fcntl` file locking for atomic operations
- **Persistence**: Jobs persist across worker restarts/crashes
- **Consistency**: All Uvicorn workers see the same job state

## Key Behaviors

### Multi-Worker Environment
- **Workers**: Configurable Uvicorn workers via `UVICORN_WORKERS` environment variable
- **Job Visibility**: All workers can see and update any job
- **No 404 Errors**: Jobs remain accessible after completion
- **Shared State**: File-based synchronization prevents race conditions

### Error Handling
- **Graceful Failures**: Failed jobs marked as `status: "failed"`
- **Persistence**: Error information preserved in job metadata
- **Recovery**: Workers can restart without losing job history
- **Validation**: Input validation with detailed error messages

### Performance Characteristics
- **Startup Time**: 30-60 seconds for complete warmup
- **Processing Speed**: 10-30 seconds per PDF (depends on complexity)
- **Concurrency**: Limited by `RQ_WORKERS` setting
- **Memory**: Efficient with temporary file cleanup

## Environment Configuration

### Required Variables (Set in RunPod Environment)
```bash
OPENAI_API_KEY=xxx         # Optional: for AI features
OMP_NUM_THREADS=4          # OpenMP threads per worker
UVICORN_WORKERS=4          # Number of API workers  
RQ_WORKERS=12              # Number of processing workers (recommended for 32-core)
```

### Optional Redis (Queue Persistence)
```bash
UPSTASH_REDIS_REST_URL=xxx    # For external queue persistence
UPSTASH_REDIS_REST_TOKEN=xxx  # Redis authentication
```

## Deployment Considerations

### RunPod.io Deployment

#### Environment Variables Configuration
Set these required variables in RunPod environment settings:
```bash
OPENAI_API_KEY=your_openai_key
OMP_NUM_THREADS=4              # OpenMP threads
UVICORN_WORKERS=4              # API workers 
RQ_WORKERS=12                  # Processing workers (adjust for your instance)
```

#### Optional Redis Variables
```bash
UPSTASH_REDIS_REST_URL=your_redis_url
UPSTASH_REDIS_REST_TOKEN=your_redis_token
```

#### Deployment Process
1. **Container Warmup**: Wait for `/warmup_status` to show `"ready": true`
2. **Health Checks**: Use `/health` for ongoing monitoring
3. **Job Submission**: Only submit to `/ocr/async` after warmup complete
4. **Scaling**: Each container instance runs independent warmup

### Resource Requirements
- **CPU**: Multi-core recommended for parallel processing
- **Memory**: 4GB+ recommended for model loading
- **Storage**: Temporary files cleaned automatically
- **Network**: Outbound for model downloads during warmup

## API Testing Results
✅ **100% Success Rate** in multi-worker job persistence tests  
✅ **No 404 Errors** for completed jobs  
✅ **JSON Integrity** maintained across all operations  
✅ **Concurrent Processing** working with proper queue limits  
✅ **Warmup Coordination** functioning without external dependencies

## Example Usage

### Check if API is ready
```bash
curl http://your-api-url/warmup_status
```

### Submit synchronous job
```bash
curl -X POST -F "file=@document.pdf" http://your-api-url/ocr
```

### Submit asynchronous job
```bash
# Submit job
response=$(curl -X POST -F "file=@document.pdf" http://your-api-url/ocr/async)
job_id=$(echo $response | jq -r '.job_id')

# Check status
curl http://your-api-url/jobs/$job_id
```

This API is production-ready for RunPod.io deployment with robust error handling, proper multi-worker coordination, and reliable job persistence.
