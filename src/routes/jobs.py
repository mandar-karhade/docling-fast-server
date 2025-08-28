from fastapi import APIRouter, HTTPException, Query
from datetime import datetime
import psutil
import os

from src.services.queue_manager import queue_manager
from src.models.job import JobUpdate

router = APIRouter()


@router.get("/jobs/{job_id}")
async def get_job_status(job_id: str):
    """Get job status and results from simulated queue system"""
    try:
        # Get job from simulated queue system
        job_data = queue_manager.get_job(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # Map simulated job status to RQ-compatible status
        job_status = job_data.get("status", "unknown")
        if job_status == "completed":
            rq_status = "finished"
        elif job_status == "processing":
            rq_status = "started"
        elif job_status == "queued":
            rq_status = "queued"
        elif job_status == "failed":
            rq_status = "failed"
        else:
            rq_status = job_status
        
        # Extract result and error
        result = job_data.get("result")
        error = job_data.get("error")
        
        # Get filename from job data
        filename = job_data.get("filename", "Unknown")
        
        return {
            "job_id": job_id,
            "status": rq_status,
            "created_at": job_data.get("created_at"),
            "started_at": None,  # Not tracked in simulated system
            "ended_at": job_data.get("updated_at") if job_status in ["completed", "failed"] else None,
            "result": result,
            "error": error,
            "filename": filename
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error getting job status: {str(e)}")


@router.get("/jobs")
async def list_jobs():
    """List all RQ jobs"""
    try:
        # Get all jobs from RQ queue
        rq_jobs = queue_manager.pdf_queue.get_jobs()
        
        jobs_list = []
        for rq_job in rq_jobs:
            jobs_list.append({
                "job_id": rq_job.id,
                "status": rq_job.get_status(),
                "created_at": rq_job.created_at.isoformat() if rq_job.created_at else None,
                "started_at": rq_job.started_at.isoformat() if rq_job.started_at else None,
                "ended_at": rq_job.ended_at.isoformat() if rq_job.ended_at else None,
                "filename": rq_job.meta.get('filename', 'Unknown') if rq_job.meta else 'Unknown'
            })
        
        return {"jobs": jobs_list}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error listing jobs: {str(e)}")


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str):
    """Delete a job"""
    if queue_manager.delete_job(job_id):
        return {"status": "deleted", "job_id": job_id}
    else:
        raise HTTPException(status_code=404, detail="Job not found")


@router.get("/get_logs")
async def get_logs():
    """Get the latest log content from in-memory jobs"""
    try:
        # Get jobs from memory
        jobs_data = queue_manager.get_all_jobs()
        
        # Count jobs by status
        status_counts = {'pending': 0, 'processing': 0, 'completed': 0, 'failed': 0}
        for job in jobs_data.values():
            status = job.get('status', 'unknown')
            status_counts[status] = status_counts.get(status, 0) + 1
        
        # Get latest logs from all jobs
        all_logs = []
        for job_id, job in jobs_data.items():
            logs = job.get('logs', [])
            for log in logs:
                log['job_id'] = job_id
                log['filename'] = job.get('filename', 'Unknown')
                all_logs.append(log)
        
        # Sort logs by timestamp
        all_logs.sort(key=lambda x: x.get('timestamp', ''))
        
        return {
            "status": "success",
            "status_summary": status_counts,
            "total_jobs": len(jobs_data),
            "total_logs": len(all_logs),
            "latest_logs": all_logs[-20:] if all_logs else [],  # Last 20 logs
            "jobs_data": jobs_data
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "message": "Failed to retrieve logs"
        }


@router.get("/worker_status")
async def get_worker_status():
    """Get current worker status and queue information"""
    try:
        worker_info = queue_manager.get_worker_info()
        queue_info = queue_manager.get_worker_queue_info()
        
        return {
            "status": "success",
            "worker_info": worker_info,
            "queue_info": queue_info,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "message": "Failed to get worker status"
        }


@router.get("/queue_status")
async def get_queue_status():
    """Get RQ queue status and statistics"""
    print("QUEUE_STATUS_ENDPOINT_CALLED")
    try:
        print("Starting queue_status endpoint")
        
        queue_status = queue_manager.get_queue_status()
        print(f"Returning response with {len(queue_status.get('workers', []))} workers")
        return queue_status
    except Exception as e:
        print(f"Exception in queue_status: {e}")
        return {
            "status": "error",
            "error": str(e),
            "message": "Failed to get queue status"
        }


@router.get("/storage_info")
async def get_storage_info():
    """Get information about job file storage and rotation"""
    try:
        storage_info = queue_manager.get_storage_info()
        return {
            "status": "success",
            "storage_info": storage_info,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "message": "Failed to get storage info"
        }


@router.post("/cleanup_jobs")
async def cleanup_jobs(hours_old: int = None):
    """Manually trigger job cleanup and file rotation"""
    try:
        result = queue_manager.cleanup_jobs(hours_old)
        return {
            "status": "success",
            "cleanup_result": result,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "message": "Failed to cleanup jobs"
        }


@router.get("/processing_activity")
async def get_processing_activity():
    """
    Get current CPU activity for monitoring abandoned jobs.
    Returns overall system CPU usage and process-specific metrics.
    """
    try:
        # Get current process info
        current_process = psutil.Process()
        
        # Get system-wide CPU usage (1 second interval for accuracy)
        system_cpu_percent = psutil.cpu_percent(interval=1)
        
        # Get process-specific CPU usage
        process_cpu_percent = current_process.cpu_percent()
        
        # Get memory usage
        memory_info = current_process.memory_info()
        memory_percent = current_process.memory_percent()
        
        # Get running jobs count
        jobs_data = queue_manager.get_all_jobs()
        processing_jobs = [j for j in jobs_data.values() if j.get('status') == 'processing']
        
        # Get worker info
        worker_info = queue_manager.get_worker_info()
        
        # Check if we're actually processing (high CPU + active jobs)
        is_actively_processing = (
            system_cpu_percent > 10 or 
            process_cpu_percent > 5 or 
            len(processing_jobs) > 0
        )
        
        return {
            "status": "success",
            "timestamp": datetime.utcnow().isoformat(),
            "cpu_activity": {
                "system_cpu_percent": round(system_cpu_percent, 2),
                "process_cpu_percent": round(process_cpu_percent, 2),
                "is_actively_processing": is_actively_processing
            },
            "memory_usage": {
                "memory_mb": round(memory_info.rss / 1024 / 1024, 2),
                "memory_percent": round(memory_percent, 2)
            },
            "job_activity": {
                "total_jobs": len(jobs_data),
                "processing_jobs": len(processing_jobs),
                "processing_job_ids": [j.get('id') for j in processing_jobs]
            },
            "worker_info": {
                "worker_id": worker_info.get("worker_id"),
                "worker_name": worker_info.get("worker_name"),
                "num_threads": worker_info.get("num_threads"),
                "deployment_id": queue_manager.deployment_id
            }
        }
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "message": "Failed to get processing activity",
            "timestamp": datetime.utcnow().isoformat()
        }


@router.post("/jobs/{job_id}/force_close")
async def force_close_job(job_id: str, reason: str = Query(default="Abandoned job - low CPU activity")):
    """
    Force close a job that appears to be abandoned.
    This sets the job status to 'failed' with an abandonment reason.
    """
    try:
        # Get the job first
        job_data = queue_manager.get_job(job_id)
        if not job_data:
            raise HTTPException(status_code=404, detail="Job not found")
        
        current_status = job_data.get("status")
        
        # Only allow force closing jobs that are processing or queued
        if current_status not in ["processing", "queued", "started"]:
            raise HTTPException(
                status_code=400, 
                detail=f"Cannot force close job with status '{current_status}'. Only processing/queued/started jobs can be force closed."
            )
        
        # Update job status to failed with abandonment reason
        error_message = f"Job force closed: {reason}"
        queue_manager.update_job_status(
            job_id=job_id,
            status="failed",
            active=False,
            waiting=False,
            error=error_message
        )
        
        return {
            "status": "success",
            "job_id": job_id,
            "message": f"Job {job_id} has been force closed",
            "reason": reason,
            "previous_status": current_status,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error force closing job: {str(e)}")


@router.get("/deployment_info")
async def get_deployment_info():
    """Get deployment information including container-level deployment ID"""
    try:
        deployment_info = queue_manager.get_deployment_info()
        return {
            "status": "success",
            "deployment_info": deployment_info,
            "timestamp": datetime.utcnow().isoformat()
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "message": "Failed to get deployment info"
        }
