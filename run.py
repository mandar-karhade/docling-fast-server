#!/usr/bin/env python3
"""
Run Script for SmolDocling RunPod Service
=========================================
Simple script to start the FastAPI service.
"""

import uvicorn
from main import app

if __name__ == "__main__":
    print("🚀 Starting SmolDocling RunPod Service...")
    print("📡 Service will be available at: http://localhost:8000")
    print("🔍 Health check: http://localhost:8000/health")
    print("📄 API docs: http://localhost:8000/docs")
    print("\nPress Ctrl+C to stop the service\n")

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )
