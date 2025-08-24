from fastapi import APIRouter
import os
from datetime import datetime

from src.services.warmup_service import warmup_service

router = APIRouter()


@router.get("/health")
async def health_check():
    """Health check endpoint with warmup status"""
    # Start warmup if not already started
    if warmup_service.warmup_status == "not_started":
        warmup_service.start_warmup()
    
    # Check if warmup is complete
    is_ready = warmup_service.is_ready()
    
    # Get warmup status
    warmup_status = warmup_service.get_status()
    
    # Get version info
    try:
        with open("/app/version.txt", "r") as f:
            version = f.read().strip()
    except:
        version = "unknown"
    
    return {
        "status": "ready" if is_ready else "warming_up",
        "service": "docling-api",
        "version": version,
        "openai_key_available": bool(os.getenv('OPENAI_API_KEY')),
        "warmup": warmup_status
    }


@router.get("/warmup/status")
async def warmup_status():
    """Get detailed warmup status with progress tracking"""
    # Check for timeout
    if warmup_service.warmup_status == "in_progress" and warmup_service.check_timeout():
        warmup_service.force_complete()
    
    status = warmup_service.get_status()
    
    # Add additional progress info
    current_time = datetime.now()
    if warmup_service.start_time:
        duration = (current_time - warmup_service.start_time).total_seconds()
        status["duration_seconds"] = duration
        
        # Calculate progress percentage
        total_steps = 4  # 2 files + sync test + async test
        completed_steps = len(warmup_service.warmup_results)
        progress_percentage = min(100, int((completed_steps / total_steps) * 100)) if warmup_service.warmup_status == "in_progress" else 100
        status["progress_percentage"] = progress_percentage
        status["completed_steps"] = completed_steps
        status["total_steps"] = total_steps
        
        # Estimate remaining time
        if warmup_service.warmup_status == "in_progress" and completed_steps > 0:
            avg_time_per_step = duration / completed_steps
            remaining_steps = total_steps - completed_steps
            estimated_remaining = avg_time_per_step * remaining_steps
            status["estimated_remaining_seconds"] = estimated_remaining
    
    return status
