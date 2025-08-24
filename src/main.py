#!/usr/bin/env python3
"""
Docling API - FastAPI Application
=================================
API for processing PDFs using Docling with comprehensive multi-language OCR support
"""

import threading
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

from src.routes import health, ocr, jobs, placeholder
from src.services.warmup_service import warmup_service

# Create FastAPI application
app = FastAPI(
    title="Docling API",
    description="API for processing PDFs using Docling with comprehensive multi-language OCR support",
    version="1.4.7"
)

# Add compression middleware
app.add_middleware(GZipMiddleware, minimum_size=1000)  # Compress responses > 1KB

# Include routers
app.include_router(health.router, tags=["health"])
app.include_router(ocr.router, tags=["ocr"])
app.include_router(jobs.router, tags=["jobs"])
app.include_router(placeholder.router, tags=["placeholder"])


@app.on_event("startup")
async def startup_event():
    """Start warmup process when API starts"""
    print("🚀 API starting up...")
    
    # Start warmup process in background thread
    def start_warmup():
        warmup_service.start_warmup()
    
    thread = threading.Thread(target=start_warmup, daemon=True)
    thread.start()
    print("🔥 Warmup process started in background")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
