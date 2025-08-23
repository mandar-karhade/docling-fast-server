#!/usr/bin/env python3
"""
Docling API - FastAPI Application
=================================
API for processing PDFs using Docling with comprehensive multi-language OCR support
"""

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

from src.routes import health, ocr, jobs, placeholder

# Create FastAPI application
app = FastAPI(
    title="Docling API",
    description="API for processing PDFs using Docling with comprehensive multi-language OCR support",
    version="1.4.0"
)

# Add compression middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)  # Compress responses > 1KB

# Include routers
app.include_router(health.router, tags=["health"])
app.include_router(ocr.router, tags=["ocr"])
app.include_router(jobs.router, tags=["jobs"])
app.include_router(placeholder.router, tags=["placeholder"])


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
