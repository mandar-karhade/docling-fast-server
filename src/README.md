# Docling API Source Code

This directory contains the organized source code for the Docling API application.

## Directory Structure

```
src/
├── __init__.py
├── main.py                 # Main FastAPI application
├── models/                 # Pydantic models for data validation
│   ├── __init__.py
│   └── job.py             # Job-related models
├── routes/                 # API route handlers
│   ├── __init__.py
│   ├── health.py          # Health check endpoints
│   ├── jobs.py            # Job management endpoints
│   ├── ocr.py             # OCR processing endpoints
│   └── placeholder.py     # Placeholder endpoints
├── services/              # Business logic services
│   ├── __init__.py
│   ├── pdf_processor.py   # PDF processing logic
│   ├── queue_manager.py   # Job queue management
│   └── rq_tasks.py        # RQ task definitions
└── utils/                 # Utility functions
    └── __init__.py
```

## Key Components

### Models (`src/models/`)
- **job.py**: Contains Pydantic models for job data structures, including Job, JobCreate, JobUpdate, and related response models.

### Routes (`src/routes/`)
- **health.py**: Health check endpoints
- **jobs.py**: Job management endpoints (status, listing, deletion)
- **ocr.py**: OCR processing endpoints (synchronous and asynchronous)
- **placeholder.py**: Placeholder endpoints for future features

### Services (`src/services/`)
- **pdf_processor.py**: Handles PDF processing logic using Docling
- **queue_manager.py**: Manages job queues and persistence
- **rq_tasks.py**: RQ task definitions for background processing

### Main Application (`src/main.py`)
- FastAPI application setup with middleware and route registration

## Usage

The main application can be run from the root directory:

```bash
python main.py
```

Or directly from the src directory:

```bash
python src/main.py
```

## Architecture

The application follows a clean architecture pattern:
- **Routes**: Handle HTTP requests and responses
- **Services**: Contain business logic and external integrations
- **Models**: Define data structures and validation
- **Utils**: Provide shared utility functions

This structure makes the code more maintainable, testable, and follows separation of concerns principles.
