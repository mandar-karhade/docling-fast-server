from fastapi import APIRouter
import os

from src.services.warmup_service import warmup_service

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint with Redis-coordinated warmup status"""
    # Always check Redis for latest status first
    warmup_service._check_redis_warmup_status()
    
    # Start warmup only if not already started or in progress
    if warmup_service.warmup_status == "not_started":
        print("🏥 Health check triggering warmup start")
        warmup_service.start_warmup()
    
    # Check if warmup is complete (this will re-check Redis)
    is_ready = warmup_service.is_ready()
    
    # Get detailed warmup status (including Redis info)
    warmup_status = warmup_service.get_status()
    
    # Determine overall health status
    if is_ready:
        health_status = "ready"
    elif warmup_service.warmup_status == "failed":
        health_status = "failed"
    else:
        health_status = "warming_up"
    
    return {
        "status": health_status,
        "service": "docling-api", 
        "openai_key_available": bool(os.getenv('OPENAI_API_KEY')),
        "warmup": warmup_status
    }
