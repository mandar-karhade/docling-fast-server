from fastapi import APIRouter
import os

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "docling-api",
        "openai_key_available": bool(os.getenv('OPENAI_API_KEY'))
    }
