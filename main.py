#!/usr/bin/env python3
"""
Docling API - Main Entry Point
==============================
This file serves as the main entry point for the Docling API application.
The actual application logic has been moved to src/main.py for better organization.
"""

from src.main import app

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
