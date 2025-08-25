from fastapi import APIRouter
import os

from src.services.warmup_service import warmup_service

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint with warmup status"""
    # Check Redis for global completion status first
    warmup_service._check_global_completion()
    
    # Start warmup only if not already started
    if warmup_service.warmup_status == "not_started":
        warmup_service.start_warmup()
    
    # Check if warmup is complete
    is_ready = warmup_service.is_ready()
    
    # Get warmup status
    warmup_status = warmup_service.get_status()
    
    return {
        "status": "ready" if is_ready else "warming_up",
        "service": "docling-api",
        "openai_key_available": bool(os.getenv('OPENAI_API_KEY')),
        "warmup": warmup_status
    }
